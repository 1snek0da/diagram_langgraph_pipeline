"""Company business classification and industry-position node."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from ..dependencies import AgentDependencies
from .common import evidence_from, topic


BASE_PE_RANGES = {
    "optical_chip": (Decimal("60"), Decimal("80")),
    "optical_module": (Decimal("25"), Decimal("35")),
    "optical_component": (Decimal("30"), Decimal("40")),
    "communication_equipment": (Decimal("15"), Decimal("25")),
    "pcb_connector": (Decimal("20"), Decimal("30")),
}

CLASSIFICATION_KEYWORDS = {
    "optical_chip": ("光芯片", "激光器芯片"),
    "optical_module": ("光模块", "光收发模块"),
    "optical_component": ("光器件", "光无源器件"),
    "communication_equipment": ("通信设备", "基站", "交换机", "路由器"),
    "pcb_connector": ("pcb", "印制电路板", "电路板", "连接器"),
}


def run(state: dict[str, Any], deps: AgentDependencies) -> dict[str, Any]:
    payload = topic(deps, "business", state)
    company_type = payload.get("company_type", "unknown")
    if company_type == "unknown":
        company_type = _infer_company_type(payload)
    rank = payload.get("market_share_rank")
    base_range = BASE_PE_RANGES.get(company_type)
    position, multiplier_range = _position_adjustment(rank)
    final_range = (
        (
            base_range[0] * multiplier_range[0],
            base_range[1] * multiplier_range[1],
        )
        if base_range
        else None
    )
    classification_evidence = [
        *payload.get("classification_evidence", []),
        *evidence_from(payload, "company_business"),
    ]
    return {
        "business_result": {
            "business_summary": payload.get("business_summary", "未提供公司业务资料"),
            "revenue_segments": payload.get("revenue_segments", []),
            "industry_linkage": payload.get("industry_linkage", "unknown"),
            "growth_drivers": payload.get("growth_drivers", []),
            "risks": payload.get("risks", []),
            "company_type": company_type,
            "classification_evidence": classification_evidence,
            "market_share_rank": rank,
            "industry_position": position,
            "base_pe_range": (
                {
                    "low": base_range[0],
                    "high": base_range[1],
                    "source_reference": "行业分析.docx:公司类型PE区间",
                }
                if base_range
                else None
            ),
            "position_adjustment_range": {
                "low": multiplier_range[0],
                "high": multiplier_range[1],
            },
            "final_pe_range": (
                {"low": final_range[0], "high": final_range[1]} if final_range else None
            ),
            "source_coverage": payload.get("source_coverage", {}),
            "source_warnings": payload.get("source_warnings", []),
            "source_errors": payload.get("source_errors", []),
            "evidence": evidence_from(payload, "company_business"),
        }
    }


def _infer_company_type(payload: dict[str, Any]) -> str:
    text_parts = [str(payload.get("business_summary", ""))]
    for item in payload.get("revenue_segments", []):
        if isinstance(item, dict):
            text_parts.extend(str(value) for value in item.values() if value is not None)
    normalized = " ".join(text_parts).lower()
    for company_type, keywords in CLASSIFICATION_KEYWORDS.items():
        if any(keyword.lower() in normalized for keyword in keywords):
            return company_type
    return "unknown"


def _position_adjustment(rank: int | None) -> tuple[str, tuple[Decimal, Decimal]]:
    if rank is None:
        return "unknown", (Decimal("1"), Decimal("1"))
    if rank <= 2:
        return "leader", (Decimal("1.10"), Decimal("1.20"))
    if rank <= 5:
        return "second_tier", (Decimal("1"), Decimal("1"))
    return "lower_tier", (Decimal("0.80"), Decimal("0.90"))
