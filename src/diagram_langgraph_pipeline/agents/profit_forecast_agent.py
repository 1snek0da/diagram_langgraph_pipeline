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
    revisions = [
        item["revision_pct"]
        for item in forecasts
        if item.get("revision_pct") is not None
    ]
    average_revision = (
        sum(revisions, Decimal("0")) / Decimal(len(revisions)) if revisions else None
    )
    business = state.get("business_result", {})
    first_revision_range = _first_revision_range(business.get("industry_position"))
    quarterly_analysis = _analyze_quarterly_financials(
        payload.get("quarterly_financials", []), forecasts
    )
    second_revision = _second_revision_range(
        quarterly_analysis,
        payload.get("product_information", {}),
    )
    adjusted_forecasts = _adjust_forecasts(
        forecasts,
        first_revision_range,
        second_revision["range"],
    )
    adjusted_revisions = [
        item["final_revision_mid_pct"]
        for item in adjusted_forecasts
        if item.get("final_revision_mid_pct") is not None
    ]
    if adjusted_revisions:
        average_revision = sum(adjusted_revisions, Decimal("0")) / Decimal(
            len(adjusted_revisions)
        )
    revision_direction = "unchanged"
    if average_revision is not None and average_revision >= Decimal("0.03"):
        revision_direction = "up"
    elif average_revision is not None and average_revision <= Decimal("-0.03"):
        revision_direction = "down"
    missing = []
    if not forecasts:
        missing.append("缺少不晚于as_of_date且带发布日期的盈利预测")
    if len(payload.get("quarterly_financials", [])) < 8:
        missing.append(
            "缺少最近8个季度及当年已披露季度财务数据，无法执行第二次盈利修正"
        )
    if business.get("industry_position") in {None, "unknown"}:
        missing.append("缺少行业地位，无法执行基础盈利修正")
    return {
        "profit_forecast_result": {
            "forecasts": forecasts,
            "adjusted_forecasts": adjusted_forecasts,
            "excluded_forecasts": excluded,
            "revision_direction": payload.get("revision_direction")
            or revision_direction,
            "average_revision_pct": average_revision,
            "first_revision": {
                "industry_position": business.get("industry_position", "unknown"),
                "range": first_revision_range,
                "basis": "leader:+15%~+25%; second_tier:+5%~+10%; lower_tier:-5%~0%",
            },
            "quarterly_analysis": quarterly_analysis,
            "second_revision": second_revision,
            "product_information": payload.get("product_information", {}),
            "consensus_summary": payload.get("consensus_summary", "未提供一致预期"),
            "missing_items": missing,
            "source_coverage": payload.get("source_coverage", {}),
            "source_warnings": payload.get("source_warnings", []),
            "source_errors": payload.get("source_errors", []),
            "evidence": evidence_from(payload, "profit_forecast"),
        }
    }


def _first_revision_range(position: Any) -> dict[str, Decimal] | None:
    ranges = {
        "leader": (Decimal("0.15"), Decimal("0.25")),
        "second_tier": (Decimal("0.05"), Decimal("0.10")),
        "lower_tier": (Decimal("-0.05"), Decimal("0")),
    }
    values = ranges.get(str(position))
    return {"low": values[0], "high": values[1]} if values else None


def _adjust_forecasts(
    forecasts: list[dict[str, Any]],
    first_range: dict[str, Decimal] | None,
    second_range: dict[str, Decimal] | None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in forecasts:
        original = _decimal(item.get("net_profit_forecast"))
        if original is None:
            rows.append({**item, "adjustment_status": "missing_net_profit_forecast"})
            continue
        first_low = first_range["low"] if first_range else Decimal("0")
        first_high = first_range["high"] if first_range else Decimal("0")
        second_low = second_range["low"] if second_range else Decimal("0")
        second_high = second_range["high"] if second_range else Decimal("0")
        first_profit_low = original * (Decimal("1") + first_low)
        first_profit_high = original * (Decimal("1") + first_high)
        final_low = first_profit_low * (Decimal("1") + second_low)
        final_high = first_profit_high * (Decimal("1") + second_high)
        final_mid = (final_low + final_high) / Decimal("2")
        rows.append(
            {
                **item,
                "original_net_profit_forecast": original,
                "first_revision_range": {"low": first_low, "high": first_high},
                "first_revised_profit_range": {
                    "low": first_profit_low,
                    "high": first_profit_high,
                },
                "second_revision_range": {"low": second_low, "high": second_high},
                "adjusted_net_profit_range": {"low": final_low, "high": final_high},
                "adjusted_net_profit_mid": final_mid,
                "final_revision_mid_pct": final_mid / original - Decimal("1"),
                "adjustment_status": (
                    "complete" if first_range and second_range else "partial"
                ),
            }
        )
    return rows


def _analyze_quarterly_financials(
    raw_rows: list[dict[str, Any]], forecasts: list[dict[str, Any]]
) -> dict[str, Any]:
    rows = sorted((dict(item) for item in raw_rows), key=_quarter_sort_key)
    if not rows:
        return {
            "status": "insufficient_data",
            "forecast_completion": None,
            "profit_quality": "unknown",
            "inflection": "unknown",
            "miss_type": "unknown",
            "metrics": {},
        }

    latest = rows[-1]
    latest_year = _integer(latest.get("fiscal_year"))
    current_year_rows = [
        row for row in rows if _integer(row.get("fiscal_year")) == latest_year
    ]
    disclosed = [
        row for row in current_year_rows if _integer(row.get("quarter")) in {1, 2}
    ]
    h1_profit = _sum_metric(disclosed, "net_profit") if len(disclosed) >= 2 else None
    full_year_candidates = [
        _decimal(item.get("net_profit_forecast"))
        for item in forecasts
        if item.get("forecast_year") == latest_year
    ]
    full_year_values = [value for value in full_year_candidates if value is not None]
    full_year_forecast = (
        sum(full_year_values, Decimal("0")) / Decimal(len(full_year_values))
        if full_year_values
        else None
    )
    completion = (
        h1_profit / full_year_forecast
        if h1_profit is not None and full_year_forecast not in {None, Decimal("0")}
        else None
    )
    expectation = (
        "severely_underestimated"
        if completion is not None and completion >= Decimal("0.70")
        else (
            "slightly_underestimated"
            if completion is not None and completion >= Decimal("0.50")
            else "reasonable" if completion is not None else "unknown"
        )
    )

    metrics = _quarter_metrics(rows)
    adjusted_yoy = metrics.get("adjusted_net_profit_yoy")
    nonrec_share = metrics.get("nonrecurring_profit_share")
    margins_stable = (
        metrics.get("gross_margin_change_4q") is not None
        and metrics["gross_margin_change_4q"] >= 0
        and metrics.get("net_margin_change_4q") is not None
        and metrics["net_margin_change_4q"] >= 0
    )
    if (
        adjusted_yoy is not None
        and adjusted_yoy > Decimal("0.50")
        and nonrec_share is not None
        and nonrec_share < Decimal("0.20")
        and margins_stable
    ):
        quality = "high"
    elif (
        (adjusted_yoy is not None and adjusted_yoy < Decimal("0.30"))
        or (nonrec_share is not None and nonrec_share > Decimal("0.30"))
        or (
            metrics.get("gross_margin_change_4q") is not None
            and metrics["gross_margin_change_4q"] < 0
        )
    ):
        quality = "low"
    else:
        quality = "medium"

    inflection_signals = _inflection_signals(rows)
    inflection = (
        "confirmed"
        if inflection_signals["confirmed_quarters"] >= 2
        else "not_confirmed"
    )
    revenue_yoy = metrics.get("revenue_yoy")
    construction_yoy = metrics.get("construction_in_progress_yoy")
    research_yoy = metrics.get("research_expense_yoy")
    overseas_share = _decimal(latest.get("overseas_revenue_share"))
    fx_loss_growth = metrics.get("fx_loss_yoy")
    gross_margin_change = metrics.get("gross_margin_change_4q")
    if (construction_yoy is not None and construction_yoy > Decimal("0.50")) or (
        research_yoy is not None and research_yoy > Decimal("0.50")
    ):
        miss_type = "proactive_investment"
    elif (
        overseas_share is not None
        and overseas_share > Decimal("0.70")
        and fx_loss_growth is not None
        and fx_loss_growth > 0
    ):
        miss_type = "fx_volatility"
    elif (revenue_yoy is not None and revenue_yoy < 0) or (
        gross_margin_change is not None and gross_margin_change <= Decimal("-0.05")
    ):
        miss_type = "passive_downturn"
    else:
        miss_type = "none"
    credibility = (
        "warning"
        if revenue_yoy is not None
        and revenue_yoy < 0
        and metrics.get("net_profit_yoy", Decimal("0")) > 0
        else (
            "credible"
            if adjusted_yoy is not None
            and adjusted_yoy > 0
            and nonrec_share is not None
            and nonrec_share < Decimal("0.20")
            else "uncertain"
        )
    )
    return {
        "status": "ok",
        "forecast_completion": completion,
        "expectation_assessment": expectation,
        "h1_actual_net_profit": h1_profit,
        "institution_full_year_forecast": full_year_forecast,
        "profit_quality": quality,
        "inflection": inflection,
        "inflection_signals": inflection_signals,
        "inflection_credibility": credibility,
        "miss_type": miss_type,
        "metrics": metrics,
    }


def _second_revision_range(
    analysis: dict[str, Any], product_information: dict[str, Any]
) -> dict[str, Any]:
    if analysis.get("status") != "ok":
        return {"range": None, "category": "insufficient_data", "basis": []}
    miss_type = analysis.get("miss_type")
    if miss_type == "passive_downturn":
        values, category = (Decimal("-0.25"), Decimal("-0.15")), "passive_downturn"
    elif miss_type == "fx_volatility":
        values, category = (Decimal("0"), Decimal("0")), "fx_volatility"
    elif miss_type == "proactive_investment":
        values, category = (Decimal("0"), Decimal("0.05")), "proactive_investment"
    else:
        beat = analysis.get("expectation_assessment") in {
            "slightly_underestimated",
            "severely_underestimated",
        }
        inflection = analysis.get("inflection") == "confirmed"
        product_upgrade = bool(
            product_information.get("upgrade_shipment")
            or product_information.get("new_product_support")
        )
        if beat and inflection and product_upgrade:
            values, category = (
                Decimal("0.15"),
                Decimal("0.25"),
            ), "beat_inflection_product_upgrade"
        elif beat and inflection:
            values, category = (
                Decimal("0.10"),
                Decimal("0.15"),
            ), "beat_inflection_non_product"
        elif beat:
            values, category = (
                Decimal("0.05"),
                Decimal("0.10"),
            ), "beat_without_inflection"
        else:
            values, category = (Decimal("0"), Decimal("0")), "unchanged"
    return {
        "range": {"low": values[0], "high": values[1]},
        "category": category,
        "basis": [
            f"expectation={analysis.get('expectation_assessment')}",
            f"profit_quality={analysis.get('profit_quality')}",
            f"inflection={analysis.get('inflection')}",
            f"miss_type={analysis.get('miss_type')}",
        ],
    }


def _quarter_metrics(rows: list[dict[str, Any]]) -> dict[str, Decimal | None]:
    latest = rows[-1]
    previous_year = rows[-5] if len(rows) >= 5 else None
    first_four = rows[-4] if len(rows) >= 4 else None
    net_profit = _decimal(latest.get("net_profit"))
    adjusted_profit = _decimal(latest.get("adjusted_net_profit"))
    return {
        "revenue_yoy": _growth(
            _decimal(latest.get("revenue")),
            _decimal(previous_year.get("revenue")) if previous_year else None,
        ),
        "net_profit_yoy": _growth(
            net_profit,
            _decimal(previous_year.get("net_profit")) if previous_year else None,
        ),
        "adjusted_net_profit_yoy": _growth(
            adjusted_profit,
            (
                _decimal(previous_year.get("adjusted_net_profit"))
                if previous_year
                else None
            ),
        ),
        "nonrecurring_profit_share": (
            (net_profit - adjusted_profit) / net_profit
            if net_profit not in {None, Decimal("0")} and adjusted_profit is not None
            else None
        ),
        "gross_margin_change_4q": _difference(
            _decimal(latest.get("gross_margin")),
            _decimal(first_four.get("gross_margin")) if first_four else None,
        ),
        "net_margin_change_4q": _difference(
            _decimal(latest.get("net_margin")),
            _decimal(first_four.get("net_margin")) if first_four else None,
        ),
        "construction_in_progress_yoy": _growth(
            _decimal(latest.get("construction_in_progress")),
            (
                _decimal(previous_year.get("construction_in_progress"))
                if previous_year
                else None
            ),
        ),
        "research_expense_yoy": _growth(
            _decimal(latest.get("research_expense")),
            _decimal(previous_year.get("research_expense")) if previous_year else None,
        ),
        "fx_loss_yoy": _growth(
            _decimal(latest.get("fx_loss")),
            _decimal(previous_year.get("fx_loss")) if previous_year else None,
        ),
    }


def _inflection_signals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    recent = rows[-4:]
    for previous, current in zip(recent, recent[1:]):
        revenue = _growth(
            _decimal(current.get("revenue")), _decimal(previous.get("revenue"))
        )
        inventory = _growth(
            _decimal(current.get("inventory")), _decimal(previous.get("inventory"))
        )
        prepayments = _growth(
            _decimal(current.get("prepayments")), _decimal(previous.get("prepayments"))
        )
        liabilities = _growth(
            _decimal(current.get("contract_liabilities")),
            _decimal(previous.get("contract_liabilities")),
        )
        signals = []
        if (
            revenue is not None
            and revenue > Decimal("0.30")
            and inventory is not None
            and inventory > 0
        ):
            signals.append("revenue_and_inventory")
        if liabilities is not None and liabilities > Decimal("0.30"):
            signals.append("contract_liabilities")
        if prepayments is not None and prepayments > Decimal("0.30"):
            signals.append("prepayments")
        checks.append({"period": current.get("period"), "signals": signals})
    return {
        "confirmed_quarters": sum(bool(item["signals"]) for item in checks),
        "quarter_checks": checks,
    }


def _quarter_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    return (
        _integer(item.get("fiscal_year")) or 0,
        _integer(item.get("quarter")) or 0,
        str(item.get("period", "")),
    )


def _sum_metric(rows: list[dict[str, Any]], key: str) -> Decimal | None:
    values = [_decimal(row.get(key)) for row in rows]
    return (
        sum((value for value in values if value is not None), Decimal("0"))
        if all(value is not None for value in values)
        else None
    )


def _growth(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    return (
        current / previous - Decimal("1")
        if current is not None and previous not in {None, Decimal("0")}
        else None
    )


def _difference(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    return current - previous if current is not None and previous is not None else None


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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
