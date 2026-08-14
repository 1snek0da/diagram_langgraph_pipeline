"""Streamlit entry point for the six-page research terminal."""

from __future__ import annotations

from typing import Any

from diagram_langgraph_pipeline.ui.api_gateway import GatewayRequestError, create_gateway
from diagram_langgraph_pipeline.ui.pages import history, market, new_analysis, report, workflow, workspace
from diagram_langgraph_pipeline.ui.state import initialize_ui_state
from diagram_langgraph_pipeline.ui.styles import apply_terminal_theme


PAGE_LABELS = {
    "研究工作台": "workspace",
    "新建分析": "analysis",
    "运行任务": "workflow",
    "行情视图": "market",
    "研究报告": "report",
    "历史记录": "history",
}

PAGE_RENDERERS = {
    "workspace": workspace.render,
    "analysis": new_analysis.render,
    "workflow": workflow.render,
    "market": market.render,
    "report": report.render,
    "history": history.render,
}


def render_page_navigation(st: Any, state: Any) -> str:
    current_page = state.get("page", "workspace")
    label_by_page = {page: label for label, page in PAGE_LABELS.items()}
    selected_label = st.segmented_control(
        "页面导航",
        options=tuple(PAGE_LABELS),
        default=label_by_page.get(current_page, "研究工作台"),
        required=True,
        key="page_navigation",
        label_visibility="collapsed",
        width="stretch",
    )
    selected_page = PAGE_LABELS.get(selected_label, current_page)
    state["page"] = selected_page
    return selected_page


def main(st_module: Any = None, gateway: Any = None) -> None:
    if st_module is None:
        import streamlit as st_module
    st = st_module
    st.set_page_config(page_title="研究终端", layout="wide")
    apply_terminal_theme(st)
    state = st.session_state
    initialize_ui_state(state)
    try:
        active_gateway = gateway or create_gateway()
    except GatewayRequestError as exc:
        st.error(exc.message)
        return
    except Exception:
        st.error("无法配置分析服务，请检查 API 地址。")
        return
    page = render_page_navigation(st, state)
    PAGE_RENDERERS.get(page, workspace.render)(st, active_gateway, state)


if __name__ == "__main__":
    main()
