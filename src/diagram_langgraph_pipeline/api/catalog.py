"""Router-derived metadata used by API clients to render task choices."""

from __future__ import annotations

from ..routing import TaskType, get_execution_plan
from .schemas import TaskTypeResponse


_DISPLAY_COPY = {
    TaskType.FULL: ("完整研究", "汇总行业、公司基本面、技术面与市场环境。"),
    TaskType.INDUSTRY: ("行业研究", "聚焦行业格局、政策、资本开支与估值。"),
    TaskType.FUNDAMENTAL: ("基本面研究", "聚焦公司业务、盈利预测与估值。"),
    TaskType.TECHNICAL: ("技术分析", "聚焦个股行情数据与技术指标。"),
    TaskType.MARKET: ("市场环境", "聚焦指数、板块技术面与市场情绪。"),
}


def task_catalog(*, paid_sources_available: bool) -> list[TaskTypeResponse]:
    records: list[TaskTypeResponse] = []
    for task_type in TaskType:
        plan = get_execution_plan(task_type)
        display_name, description = _DISPLAY_COPY[task_type]
        records.append(
            TaskTypeResponse(
                task_type=task_type,
                display_name=display_name,
                description=description,
                required_nodes=plan.required_nodes,
                support_nodes=plan.support_nodes,
                optional_nodes=plan.optional_nodes,
                skipped_nodes=plan.skipped_nodes,
                required_inputs=plan.required_inputs,
                conclusion_scope=plan.conclusion_scope,
                paid_sources_available=paid_sources_available,
            )
        )
    return records
