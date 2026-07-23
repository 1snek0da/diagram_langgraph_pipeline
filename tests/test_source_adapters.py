import json
from datetime import date
from decimal import Decimal

import httpx

from diagram_langgraph_pipeline.providers import (
    EcbFxAdapter,
    HttpPolicy,
    LicensedReportDirectoryAdapter,
    ResilientHttpTransport,
    SecEdgarAdapter,
)
from diagram_langgraph_pipeline.schemas import DatasetKind, EntityRef, SourceRequest


class StaticClient:
    def __init__(self, callback):
        self.callback = callback

    def get(self, url, **kwargs):
        return self.callback(url, kwargs)


def _response(url, *, json_data=None, text=""):
    request = httpx.Request("GET", url)
    if json_data is not None:
        return httpx.Response(200, json=json_data, request=request)
    return httpx.Response(200, text=text, request=request)


def test_sec_uses_latest_filing_before_as_of_and_keeps_reported_basis():
    payload = {
        "facts": {
            "us-gaap": {
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "units": {
                        "USD": [
                            {
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2024,
                                "filed": "2025-02-01",
                                "end": "2024-12-31",
                                "val": 90,
                                "accn": "old",
                            },
                            {
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2024,
                                "filed": "2025-03-01",
                                "end": "2024-12-31",
                                "val": 100,
                                "accn": "restated",
                            },
                            {
                                "form": "10-K",
                                "fp": "FY",
                                "fy": 2025,
                                "filed": "2027-01-01",
                                "end": "2025-12-31",
                                "val": 150,
                                "accn": "future",
                            },
                        ]
                    }
                }
            }
        }
    }
    adapter = SecEdgarAdapter(
        user_agent="tests test@example.com",
        client=StaticClient(lambda url, _: _response(url, json_data=payload)),
    )
    request = SourceRequest(
        dataset_kind=DatasetKind.CAPEX,
        run_id="r1",
        as_of_date=date(2026, 7, 21),
        entities=[EntityRef(entity_id="alphabet", name="Alphabet", cik="1652044", role="demand")],
    )

    batch = adapter.fetch(request)

    assert [fact.value for fact in batch.facts] == [Decimal("100")]
    assert batch.facts[0].basis.value == "reported"
    assert batch.facts[0].metadata["role"] == "demand"
    assert batch.documents[0].external_id == "restated"


def test_sec_falls_back_to_raw_10k_and_marks_extracted_when_xbrl_tag_is_missing():
    company_facts = {"facts": {"us-gaap": {}}}
    submissions = {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "filingDate": ["2025-02-01"],
                "reportDate": ["2024-12-31"],
                "accessionNumber": ["0001-25-000001"],
                "primaryDocument": ["annual.htm"],
            }
        }
    }
    filing = """
    <html><body><p>Amounts in millions</p><table>
      <tr><td>Purchases of property and equipment</td><td>2024</td><td>(123)</td></tr>
    </table></body></html>
    """

    def callback(url, _):
        if "companyfacts" in url:
            return _response(url, json_data=company_facts)
        if "submissions" in url:
            return _response(url, json_data=submissions)
        return _response(url, text=filing)

    adapter = SecEdgarAdapter(
        user_agent="tests test@example.com",
        client=StaticClient(callback),
    )
    request = SourceRequest(
        dataset_kind=DatasetKind.CAPEX,
        run_id="raw",
        as_of_date=date(2026, 7, 21),
        entities=[EntityRef(entity_id="alphabet", name="Alphabet", cik="1652044", role="demand")],
    )

    batch = adapter.fetch(request)

    assert batch.facts[0].basis.value == "extracted"
    assert batch.facts[0].value == Decimal("123")
    assert batch.facts[0].scale == Decimal("1000000")
    assert any("启发式提取" in warning for warning in batch.warnings)


def test_ecb_cross_rate_uses_latest_common_date_not_after_as_of():
    def callback(url, _):
        currency = "USD" if "D.USD." in url else "CNY"
        value = "1.20" if currency == "USD" else "8.40"
        future = "1.30" if currency == "USD" else "9.10"
        csv_text = f"TIME_PERIOD,OBS_VALUE\n2026-07-20,{value}\n2026-07-22,{future}\n"
        return _response(url, text=csv_text)

    adapter = EcbFxAdapter(client=StaticClient(callback))
    request = SourceRequest(
        dataset_kind=DatasetKind.INDUSTRY_VALUATION,
        run_id="r2",
        as_of_date=date(2026, 7, 21),
    )

    batch = adapter.fetch(request)

    assert batch.data["fx_rate_usd_cny"] == Decimal("7")
    assert batch.data["fx_rate_date"] == date(2026, 7, 20)


def test_authorized_report_sidecar_emits_extracted_fact(tmp_path):
    report = tmp_path / "licensed.txt"
    report.write_text("Authorized report export", encoding="utf-8")
    sidecar = report.with_suffix(".txt.json")
    sidecar.write_text(
        json.dumps(
            {
                "published_at": "2026-07-01T00:00:00+08:00",
                "facts": [
                    {
                        "metric_key": "communication_capex",
                        "entity_id": "alphabet",
                        "fiscal_year": 2025,
                        "value": "12.5",
                        "currency": "USD",
                        "unit": "billion",
                        "scale": "1000000000",
                    }
                ],
                "evidence": [{"claim_text": "通信相关资本开支为12.5"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    request = SourceRequest(
        dataset_kind=DatasetKind.CAPEX,
        run_id="r3",
        as_of_date=date(2026, 7, 21),
        parameters={"licensed_report_paths": [str(report)]},
    )

    batch = LicensedReportDirectoryAdapter().fetch(request)

    assert batch.facts[0].basis.value == "extracted"
    assert batch.facts[0].value == Decimal("12.5")
    assert batch.evidence[0].source_id == batch.documents[0].source_id


def test_http_transport_retries_then_caches_success():
    class FlakyClient:
        calls = 0

        def get(self, url, **kwargs):
            self.calls += 1
            request = httpx.Request("GET", url)
            if self.calls == 1:
                raise httpx.ConnectError("temporary", request=request)
            return httpx.Response(200, text="ok", request=request)

    client = FlakyClient()
    transport = ResilientHttpTransport(
        HttpPolicy(max_attempts=2, minimum_interval_seconds=0, cache_enabled=True),
        client=client,
    )

    assert transport.get("https://example.test/data").text == "ok"
    assert transport.get("https://example.test/data").text == "ok"
    assert client.calls == 2
