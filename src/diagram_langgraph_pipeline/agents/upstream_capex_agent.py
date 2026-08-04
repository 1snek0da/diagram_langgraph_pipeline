"""Demand/supply-separated upstream capital-expenditure analysis."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from statistics import median
from typing import Any

from ..dependencies import AgentDependencies
from ..schemas.research import FactBasis
from .common import evidence_from, topic


DEMAND_COMPANIES = {"alphabet", "amazon", "microsoft", "meta", "oracle"}
SUPPLY_COMPANIES = {"nvidia"}


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "upstream_capex", state)
    records = [_normalized_record(item) for item in payload.get("records", []) if isinstance(item, dict)]
    records = [item for item in records if item["company_name"]]
    _fill_derived_metrics(records)

    demand_records = [item for item in records if item["role"] == "demand"]
    supply_records = [item for item in records if item["role"] == "supply"]
    demand_aggregate = _aggregate_by_year(demand_records)
    demand_changes = [
        item["communication_capex_change_pct"]
        for item in demand_aggregate
        if item.get("communication_capex_change_pct") is not None
    ]
    if not demand_changes:
        demand_changes = [
            item["total_capex_change_pct"]
            for item in demand_aggregate
            if item.get("total_capex_change_pct") is not None
        ]
    direction = payload.get("direction") or _direction(demand_changes)

    covered = {
        item["entity_id"]
        for item in demand_records
        if item.get("total_capex") is not None or item.get("communication_capex") is not None
    }
    coverage_ratio = Decimal(len(covered & DEMAND_COMPANIES)) / Decimal(len(DEMAND_COMPANIES))
    missing_companies = sorted(DEMAND_COMPANIES - covered)
    warnings = list(payload.get("source_warnings", []))
    if not any(item.get("communication_capex") is not None for item in demand_records):
        warnings.append("未获得可核验的通信相关CapEx；不得从总CapEx静默推算")
    missing_items = [f"需求侧CapEx缺少:{company}" for company in missing_companies]
    if not any(item.get("communication_capex") is not None for item in demand_records):
        missing_items.append("缺少可核验的通信相关CapEx")

    return {
        "upstream_capex_result": {
            "direction": direction,
            "demand_signal": payload.get("demand_signal", "证据不足"),
            "demand_side": {
                "companies": sorted(DEMAND_COMPANIES),
                "records": demand_records,
                "annual_aggregate": demand_aggregate,
            },
            "supply_side": {
                "companies": sorted(SUPPLY_COMPANIES),
                "records": supply_records,
                "included_in_demand_total": False,
            },
            "consensus_forecasts": payload.get("consensus_forecasts", []),
            "company_coverage": {
                "requested": sorted(DEMAND_COMPANIES),
                "covered": sorted(covered & DEMAND_COMPANIES),
                "missing": missing_companies,
                "coverage_ratio": coverage_ratio,
            },
            "source_coverage": payload.get("source_coverage", {}),
            "source_documents": payload.get("source_documents", []),
            "metric_facts": payload.get("metric_facts", []),
            "source_warnings": list(dict.fromkeys(warnings)),
            "source_errors": payload.get("source_errors", []),
            "missing_items": missing_items,
            "evidence": evidence_from(payload, "upstream_capex"),
        }
    }


def _normalized_record(item: dict[str, Any]) -> dict[str, Any]:
    company_name = str(item.get("company_name", "")).strip()
    entity_id = str(item.get("entity_id") or company_name).strip().lower().replace(" ", "_")
    role = item.get("role", "other")
    if entity_id in DEMAND_COMPANIES:
        role = "demand"
    elif entity_id in SUPPLY_COMPANIES:
        role = "supply"
    basis = item.get("fact_basis", FactBasis.REPORTED)
    basis_value = basis.value if isinstance(basis, FactBasis) else str(basis)
    total_basis = item.get("total_capex_basis") or basis
    communication_basis = item.get("communication_capex_basis") or basis
    scale = _decimal(item.get("scale")) or Decimal("1")
    total_capex = _decimal(item.get("total_capex"))
    communication_capex = _decimal(item.get("communication_capex"))
    return {
        **item,
        "company_name": company_name,
        "entity_id": entity_id,
        "role": role,
        "fiscal_year": _integer(item.get("fiscal_year")),
        "total_capex": total_capex * scale if total_capex is not None else None,
        "communication_capex": communication_capex * scale if communication_capex is not None else None,
        "currency": str(item.get("currency", "USD")).upper(),
        "unit": "currency",
        "input_unit": str(item.get("unit", "currency")),
        "scale": scale,
        "fact_basis": basis_value,
        "total_capex_basis": total_basis.value if isinstance(total_basis, FactBasis) else str(total_basis),
        "communication_capex_basis": (
            communication_basis.value if isinstance(communication_basis, FactBasis) else str(communication_basis)
        ),
        "capex_change_pct": _decimal(item.get("capex_change_pct")),
    }


def _fill_derived_metrics(records: list[dict[str, Any]]) -> None:
    by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_entity[record["entity_id"]].append(record)
        total = record.get("total_capex")
        communication = record.get("communication_capex")
        record["communication_share"] = communication / total if total and communication is not None else None
    for entity_records in by_entity.values():
        entity_records.sort(key=lambda item: item.get("fiscal_year") or 0)
        for previous, current in zip(entity_records, entity_records[1:]):
            if current.get("capex_change_pct") is None:
                current["capex_change_pct"] = _growth(previous.get("total_capex"), current.get("total_capex"))
            current["communication_capex_change_pct"] = _growth(
                previous.get("communication_capex"),
                current.get("communication_capex"),
            )
            prior_share = previous.get("communication_share")
            current_share = current.get("communication_share")
            current["communication_share_change"] = (
                current_share - prior_share if current_share is not None and prior_share is not None else None
            )


def _aggregate_by_year(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("fiscal_year") is not None:
            grouped[record["fiscal_year"]].append(record)
    result: list[dict[str, Any]] = []
    for year, items in sorted(grouped.items()):
        currencies = {item["currency"] for item in items}
        total_values = [item["total_capex"] for item in items if item.get("total_capex") is not None]
        communication_values = [
            item["communication_capex"]
            for item in items
            if item.get("communication_capex") is not None
        ]
        total = sum(total_values, Decimal("0")) if total_values and len(currencies) == 1 else None
        communication = (
            sum(communication_values, Decimal("0"))
            if communication_values and len(currencies) == 1
            else None
        )
        result.append(
            {
                "fiscal_year": year,
                "currency": next(iter(currencies)) if len(currencies) == 1 else None,
                "total_capex": total,
                "communication_capex": communication,
                "communication_share": communication / total if total and communication is not None else None,
                "company_count": len(items),
                "communication_company_count": len(communication_values),
                "fact_basis": "derived",
            }
        )
    for previous, current in zip(result, result[1:]):
        current["total_capex_change_pct"] = _growth(previous.get("total_capex"), current.get("total_capex"))
        current["communication_capex_change_pct"] = _growth(
            previous.get("communication_capex"),
            current.get("communication_capex"),
        )
        if current.get("communication_share") is not None and previous.get("communication_share") is not None:
            current["communication_share_change"] = current["communication_share"] - previous["communication_share"]
    return result


def _direction(changes: list[Decimal]) -> str:
    if not changes:
        return "unknown"
    central = Decimal(str(median(changes)))
    if central >= Decimal("0.10"):
        return "up"
    if central <= Decimal("-0.10"):
        return "down"
    return "flat"


def _growth(previous: Decimal | None, current: Decimal | None) -> Decimal | None:
    return current / previous - Decimal("1") if previous not in (None, Decimal("0")) and current is not None else None


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
