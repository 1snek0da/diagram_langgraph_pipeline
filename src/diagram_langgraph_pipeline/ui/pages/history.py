"""Server-backed paginated run history."""

from __future__ import annotations

from ..components import page_heading, status_label
from ..state import initialize_ui_state, navigate


def render(st, gateway, state) -> None:
    initialize_ui_state(state)
    page_heading(st, "历史记录", "筛选 PostgreSQL 中的运行记录，不依赖本地缓存。")
    ticker = st.text_input("证券代码", value="").strip().upper() or None
    task_type = st.selectbox(
        "任务类型",
        ["全部", "full", "industry", "fundamental", "technical", "market"],
    )
    run_status = st.selectbox(
        "状态",
        ["全部", "pending", "running", "completed", "degraded", "failed", "interrupted"],
    )
    page = gateway.list_runs(
        ticker=ticker,
        task_type=None if task_type == "全部" else task_type,
        status=None if run_status == "全部" else run_status,
        limit=20,
        offset=0,
    )
    runs = list(getattr(page, "items", page))
    if not runs:
        st.info("没有符合条件的历史记录。")
        return
    for run in runs:
        st.markdown(
            f"**{run.ticker}** · {run.task_type.value} · {status_label(run.status)}"
        )
        if st.button(f"查看 {run.run_id}"):
            state["selected_run_id"] = run.run_id
            navigate(state, "workflow")
            st.rerun()

