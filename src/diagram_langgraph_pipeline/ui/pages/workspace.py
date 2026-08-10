"""Research workspace overview and run metrics."""

from __future__ import annotations

from ..components import page_heading, status_label
from ..state import initialize_ui_state


def render(st, gateway, state) -> None:
    initialize_ui_state(state)
    page_heading(st, "研究工作台", "查看近期分析并从这里开始新的研究任务。")
    page = gateway.list_runs(limit=20)
    runs = list(getattr(page, "items", page))
    counts = {
        "总运行": len(runs),
        "运行中": sum(run.status == "running" for run in runs),
        "失败/中断": sum(run.status in {"failed", "interrupted"} for run in runs),
        "已完成": sum(run.status in {"completed", "degraded"} for run in runs),
    }
    columns = st.columns(4)
    for column, (label, value) in zip(columns, counts.items()):
        column.metric(label, value)
    st.subheader("最近运行")
    if not runs:
        st.info("还没有分析记录，先创建一次研究任务。")
        return
    for run in runs:
        st.markdown(
            f"**{run.ticker}** · {run.task_type.value} · {status_label(run.status)}"
        )

