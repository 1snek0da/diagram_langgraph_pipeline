"""As-of-safe profit forecast aggregation node."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, topic


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "profit_forecast", state)
    as_of = _date_value(state.get("as_of_date")) or date.today()
    forecasts = []
    excluded = []
    for item in payload.get("forecasts", []):
        published_at = _datetime_value(item.get("published_at"))
        if published_at is None:
            excluded.append({"reason": "missing_published_at", "record": item})
            continue
        if published_at.date() > as_of:
            excluded.append({"reason": "after_as_of_date", "record": item})
            continue
        forecasts.append(
            {
                **item,
                "published_at": published_at,
                "forecast_year": int(item.get("forecast_year")),
                "revenue_forecast": _decimal(item.get("revenue_forecast")),
                "net_profit_forecast": _decimal(item.get("net_profit_forecast")),
                "eps_forecast": _decimal(item.get("eps_forecast")),
                "pe_assumption": _decimal(item.get("pe_assumption")),
                "revision_pct": _decimal(item.get("revision_pct")),
            }
        )
    forecasts.sort(key=lambda item: (item["forecast_year"], item["published_at"]))
    revisions = [item["revision_pct"] for item in forecasts if item.get("revision_pct") is not None]
    average_revision = sum(revisions, Decimal("0")) / Decimal(len(revisions)) if revisions else None
    revision_direction = "unchanged"
    if average_revision is not None and average_revision >= Decimal("0.03"):
        revision_direction = "up"
    elif average_revision is not None and average_revision <= Decimal("-0.03"):
        revision_direction = "down"
    missing = []
    if not forecasts:
        missing.append("缺少不晚于as_of_date且带发布日期的盈利预测")
    return {
        "profit_forecast_result": {
            "forecasts": forecasts,
            "excluded_forecasts": excluded,
            "revision_direction": payload.get("revision_direction") or revision_direction,
            "average_revision_pct": average_revision,
            "consensus_summary": payload.get("consensus_summary", "未提供一致预期"),
            "missing_items": missing,
            "source_coverage": payload.get("source_coverage", {}),
            "source_warnings": payload.get("source_warnings", []),
            "source_errors": payload.get("source_errors", []),
            "evidence": evidence_from(payload, "profit_forecast"),
        }
    }


def _datetime_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _date_value(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except Exception:
        return None
