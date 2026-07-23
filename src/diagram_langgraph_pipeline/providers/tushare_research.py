"""Optional Tushare Pro adapter for A-share structured research data."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os
from typing import Any

from ..schemas.research import (
    CoverageReport,
    DatasetKind,
    EvidenceItem,
    FactBasis,
    MetricFact,
    SourceBatch,
    SourceDocument,
    SourceRequest,
    SourceTier,
)


class TushareResearchAdapter:
    name = "tushare"
    capabilities = frozenset(
        {
            DatasetKind.COMPANY_PROFILE,
            DatasetKind.PROFIT_FORECASTS,
            DatasetKind.POLICY,
            DatasetKind.MARKET_VALUATION,
            DatasetKind.INDUSTRY_MEMBERS,
            DatasetKind.INDUSTRY_VALUATION,
            DatasetKind.COMPANY_VALUATION,
        }
    )

    def __init__(self, token: str | None = None, pro_client: Any = None):
        self.token = token or os.getenv("TUSHARE_TOKEN")
        self._pro_client = pro_client

    def fetch(self, request: SourceRequest) -> SourceBatch:
        try:
            pro = self._client()
        except Exception as exc:
            return SourceBatch(errors=[f"tushare unavailable: {exc}"])
        handlers = {
            DatasetKind.COMPANY_PROFILE: self._company_profile,
            DatasetKind.PROFIT_FORECASTS: self._profit_forecasts,
            DatasetKind.POLICY: self._policy_news,
            DatasetKind.MARKET_VALUATION: self._market_valuation,
            DatasetKind.INDUSTRY_MEMBERS: self._industry_members,
            DatasetKind.INDUSTRY_VALUATION: self._industry_valuation,
            DatasetKind.COMPANY_VALUATION: self._company_valuation,
        }
        return handlers[request.dataset_kind](pro, request)

    def _client(self):
        if self._pro_client is not None:
            return self._pro_client
        if not self.token:
            raise RuntimeError("TUSHARE_TOKEN is not configured")
        try:
            import tushare as ts
        except ImportError as exc:
            raise RuntimeError("install the optional 'sources' dependency") from exc
        return ts.pro_api(self.token)

    def _company_profile(self, pro, request: SourceRequest) -> SourceBatch:
        ticker = _target_ticker(request)
        company_rows = _rows(pro.stock_company(ts_code=ticker))
        segment_rows = [
            item
            for item in _rows(pro.fina_mainbz(ts_code=ticker, type="P"))
            if _compact_date(item.get("end_date")) is None
            or _compact_date(item.get("end_date")) <= request.as_of_date
        ]
        company = company_rows[0] if company_rows else {}
        data = {
            "business_summary": company.get("main_business") or company.get("introduction") or "未提供公司业务资料",
            "revenue_segments": [
                {
                    "name": item.get("bz_item"),
                    "revenue": item.get("bz_sales"),
                    "profit": item.get("bz_profit"),
                    "cost": item.get("bz_cost"),
                    "currency": item.get("curr_type") or "CNY",
                    "period_end": item.get("end_date"),
                }
                for item in segment_rows
            ],
        }
        document = _document(self.name, "tushare_company_profile", ticker, {"company": company, "segments": segment_rows})
        evidence = [
            EvidenceItem(
                source_id=document.source_id,
                evidence_type="company_business",
                claim_text=str(data["business_summary"]),
                extraction_method="structured_api",
                confidence_score=Decimal("0.9"),
            )
        ] if company else []
        return SourceBatch(
            data=data,
            documents=[document],
            evidence=evidence,
            coverage=CoverageReport.from_items(["company_profile", "revenue_segments"], [key for key, value in data.items() if value]),
        )

    def _profit_forecasts(self, pro, request: SourceRequest) -> SourceBatch:
        ticker = _target_ticker(request)
        rows = _rows(
            pro.forecast(
                ts_code=ticker,
                start_date=(request.start_date or request.as_of_date).strftime("%Y%m%d"),
                end_date=request.as_of_date.strftime("%Y%m%d"),
            )
        )
        forecasts = []
        for item in rows:
            published = _compact_datetime(item.get("ann_date"))
            if published and published.date() > request.as_of_date:
                continue
            forecasts.append(
                {
                    "forecast_year": int(str(item.get("end_date", request.as_of_date.year))[:4]),
                    "institution": "company_guidance",
                    "published_at": published,
                    "forecast_basis": "company_guidance",
                    "currency": "CNY",
                    "net_profit_forecast": _midpoint(item.get("net_profit_min"), item.get("net_profit_max"), scale=Decimal("10000")),
                    "source_id": f"tushare:forecast:{ticker}:{item.get('ann_date')}:{item.get('end_date')}",
                }
            )
        document = _document(self.name, "tushare_performance_forecast", ticker, rows)
        return SourceBatch(
            data={"forecasts": forecasts},
            documents=[document],
            coverage=CoverageReport.from_items(["forecasts"], ["forecasts"] if forecasts else []),
            warnings=["Tushare forecast为公司业绩预告，不等同于券商一致预期"],
        )

    def _policy_news(self, pro, request: SourceRequest) -> SourceBatch:
        rows = _rows(
            pro.major_news(
                src="财联社",
                start_date=f"{(request.start_date or request.as_of_date).isoformat()} 00:00:00",
                end_date=f"{request.as_of_date.isoformat()} 23:59:59",
                fields="title,content,pub_time,src",
            )
        )
        events = []
        documents = []
        for index, item in enumerate(rows):
            published = _iso_datetime(item.get("pub_time"))
            if published and published.date() > request.as_of_date:
                continue
            document = _document(self.name, "secondary_policy_news", str(index), item, published_at=published)
            document.source_tier = SourceTier.SECONDARY_NEWS
            documents.append(document)
            events.append(
                {
                    "title": item.get("title"),
                    "published_at": published,
                    "magnitude": "unknown",
                    "impact_horizon": "unknown",
                    "source_id": document.source_id,
                }
            )
        return SourceBatch(
            data={"events": events},
            documents=documents,
            coverage=CoverageReport.from_items(["policy_news"], ["policy_news"] if events else []),
            warnings=["财联社新闻仅作为政策线索，结论必须回溯到官方政策原文"],
        )

    def _market_valuation(self, pro, request: SourceRequest) -> SourceBatch:
        ticker = _target_ticker(request)
        rows = _rows(
            pro.daily_basic(
                ts_code=ticker,
                start_date=(request.start_date or request.as_of_date).strftime("%Y%m%d"),
                end_date=request.as_of_date.strftime("%Y%m%d"),
            )
        )
        facts = []
        for item in rows:
            trade_date = item.get("trade_date")
            for key, metric in (("total_mv", "market_cap"), ("pe_ttm", "pe_ttm"), ("pb", "pb"), ("ps_ttm", "ps_ttm")):
                if item.get(key) is None:
                    continue
                facts.append(
                    MetricFact(
                        metric_key=metric,
                        entity_id=ticker,
                        period_end=datetime.strptime(str(trade_date), "%Y%m%d").date() if trade_date else None,
                        value=Decimal(str(item[key])) * (Decimal("10000") if key == "total_mv" else Decimal("1")),
                        currency="CNY" if key == "total_mv" else None,
                        unit="currency" if key == "total_mv" else "multiple",
                        basis=FactBasis.REPORTED,
                        provider=self.name,
                    )
                )
        return SourceBatch(
            facts=facts,
            coverage=CoverageReport.from_items(["market_valuation"], ["market_valuation"] if facts else []),
        )

    def _industry_members(self, pro, request: SourceRequest) -> SourceBatch:
        rows = _as_of_members(_rows(pro.index_member_all(l3_code=request.industry_code)), request.as_of_date)
        return SourceBatch(
            data={
                "members": rows,
                "universe_id": _universe_id(request.industry_code, rows),
                "universe_as_of_date": request.as_of_date,
            },
            coverage=CoverageReport.from_items(["industry_members"], ["industry_members"] if rows else []),
        )

    def _industry_valuation(self, pro, request: SourceRequest) -> SourceBatch:
        members = _as_of_members(_rows(pro.index_member_all(l3_code=request.industry_code)), request.as_of_date)
        member_codes = {str(item.get("ts_code") or item.get("con_code")) for item in members}
        valuation_rows = _rows(pro.daily_basic(trade_date=request.as_of_date.strftime("%Y%m%d")))
        selected = [item for item in valuation_rows if str(item.get("ts_code")) in member_codes]
        market_caps = [
            Decimal(str(item["total_mv"])) * Decimal("10000")
            for item in selected
            if item.get("total_mv") is not None
        ]
        data = {
            "current_market_cap": sum(market_caps, Decimal("0")) if market_caps else None,
            "current_market_cap_currency": "CNY",
            "universe_id": _universe_id(request.industry_code, members),
            "universe_as_of_date": request.as_of_date,
        }
        return SourceBatch(
            data=data,
            coverage=CoverageReport.from_items(
                ["current_market_cap"],
                ["current_market_cap"] if data["current_market_cap"] is not None else [],
            ),
            warnings=[] if selected else ["指定日期未获得行业成分股估值快照"],
        )

    def _company_valuation(self, pro, request: SourceRequest) -> SourceBatch:
        ticker = _target_ticker(request)
        rows = _rows(
            pro.daily_basic(
                ts_code=ticker,
                start_date=request.as_of_date.strftime("%Y%m%d"),
                end_date=request.as_of_date.strftime("%Y%m%d"),
            )
        )
        row = rows[0] if rows else {}
        market_cap = (
            Decimal(str(row["total_mv"])) * Decimal("10000")
            if row.get("total_mv") is not None
            else None
        )
        return SourceBatch(
            data={"current_market_cap": market_cap, "current_market_cap_currency": "CNY"},
            coverage=CoverageReport.from_items(
                ["current_market_cap"],
                ["current_market_cap"] if market_cap is not None else [],
            ),
        )


def _target_ticker(request: SourceRequest) -> str:
    ticker = next((entity.ticker for entity in request.entities if entity.role == "target" and entity.ticker), None)
    if ticker is None:
        raise ValueError("target ticker is required")
    return ticker


def _rows(frame: Any) -> list[dict]:
    if frame is None:
        return []
    if hasattr(frame, "to_dict"):
        return frame.to_dict(orient="records")
    if isinstance(frame, list):
        return [dict(item) for item in frame if isinstance(item, dict)]
    return []


def _document(provider: str, source_type: str, external_id: str, payload: Any, *, published_at=None) -> SourceDocument:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    return SourceDocument(
        source_id=f"{provider}:{source_type}:{external_id}",
        provider=provider,
        source_tier=SourceTier.LICENSED_STRUCTURED,
        source_type=source_type,
        external_id=external_id,
        title=f"{source_type} {external_id}",
        publisher="Tushare Pro",
        published_at=published_at,
        content_hash=sha256(raw).hexdigest(),
        language="zh-CN",
        license_scope="licensed_api",
        metadata={"record_count": len(payload) if isinstance(payload, list) else 1},
    )


def _midpoint(low, high, *, scale: Decimal) -> Decimal | None:
    values = [Decimal(str(value)) * scale for value in (low, high) if value is not None]
    return sum(values) / Decimal(len(values)) if values else None


def _compact_datetime(value) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip()
    if not normalized or normalized.lower() in {"nan", "none", "nat"}:
        return None
    try:
        return datetime.strptime(normalized[:8], "%Y%m%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _compact_date(value):
    return _compact_datetime(value).date() if value else None


def _as_of_members(rows: list[dict], cutoff) -> list[dict]:
    result = []
    for item in rows:
        in_date = _compact_date(item.get("in_date"))
        out_date = _compact_date(item.get("out_date"))
        if in_date and in_date > cutoff:
            continue
        if out_date and out_date <= cutoff:
            continue
        result.append(item)
    return result


def _universe_id(industry_code: str | None, rows: list[dict]) -> str:
    codes = sorted(str(item.get("ts_code") or item.get("con_code") or "") for item in rows)
    raw = json.dumps({"industry_code": industry_code, "members": codes}, sort_keys=True).encode()
    return f"tushare:{sha256(raw).hexdigest()[:16]}"


def _iso_datetime(value) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
