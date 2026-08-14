"""Run status, node progress, and explicit refresh behavior."""

from __future__ import annotations

from ..components import page_heading, status_label
from ..models import AnalysisRun
from ..state import initialize_ui_state, save_run


TERMINAL_STATUSES = {"completed", "degraded", "failed", "interrupted"}


def refresh_active_run(gateway, state, run: AnalysisRun) -> AnalysisRun:
    refreshed = gateway.get_run(run.run_id)
    save_run(state, refreshed)
    return refreshed


def render(st, gateway, state) -> None:
    initialize_ui_state(state)
    page_heading(st, "运行任务", "查看 Router 节点进度，按需刷新当前任务。")
    run_id = state.get("selected_run_id")
    if not run_id:
        st.info("请先从工作台或历史记录选择一次运行。")
        return
    run = state.get("run_cache", {}).get(run_id)
    refresh_clicked = False
    if run is None or run.status not in TERMINAL_STATUSES:
        refresh_clicked = st.button("刷新状态")
    if run is None or refresh_clicked:
        run = gateway.get_run(run_id)
        save_run(state, run)
    st.subheader(f"{run.ticker} · {status_label(run.status)}")
    if run.status in {"failed", "interrupted"}:
        st.error(f"{run.error_code or 'RUN_FAILED'}：{run.error_summary or '任务未完成'}")
    elif run.status in {"completed", "degraded"}:
        st.success("任务已结束，可以查看研究报告。")
    nodes = gateway.get_nodes(run_id)
    groups = {
        "必需节点": [node for node in nodes if node.role == "required"],
        "支持节点": [node for node in nodes if node.role == "support"],
        "可选节点": [node for node in nodes if node.role == "optional"],
        "主动跳过": [node for node in nodes if node.role == "skipped"],
    }
    for title, grouped in groups.items():
        if not grouped:
            continue
        st.write(title)
        for node in grouped:
            suffix = f"：{node.error_summary}" if node.error_summary else ""
            st.write(f"{node.name} · {status_label(node.status)}{suffix}")

