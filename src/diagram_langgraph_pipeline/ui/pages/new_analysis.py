"""Metadata-driven five-mode analysis form."""

from __future__ import annotations

from datetime import date

from ..components import page_heading
from ..models import AnalysisRequest, TaskTypeView
from ..state import initialize_ui_state, navigate


def _scope_preview(st, task: TaskTypeView) -> None:
    st.subheader("执行范围")
    st.write("必需节点")
    for name in task.required_nodes:
        st.write(name)
    st.write("支持节点")
    for name in task.support_nodes:
        st.write(name)
    if task.optional_nodes:
        st.write("可选节点")
        for name in task.optional_nodes:
            st.write(name)
    st.write("跳过节点")
    for name in task.skipped_nodes:
        st.write(name)
    st.caption(task.conclusion_scope)


def render(st, gateway, state) -> None:
    initialize_ui_state(state)
    page_heading(st, "新建分析", "选择一个 Router 任务模式，提交后异步运行。")
    tasks = gateway.task_types()
    if not tasks:
        st.warning("当前没有可用的分析任务。")
        return

    task = st.selectbox(
        "任务类型",
        tasks,
        format_func=lambda item: f"{item.display_name}（{item.task_type.value}）",
    )
    _scope_preview(st, task)

    with st.form("analysis-form"):
        ticker = st.text_input("证券代码", value="")
        as_of_date = st.date_input("分析日期", value=date.today())
        horizon = "medium"
        industry_name = None
        if task.task_type.value in {"full", "industry", "fundamental"}:
            horizon = st.selectbox(
                "投资期限", ["short", "medium", "long"], index=1
            )
        if task.task_type.value == "full":
            industry_name = st.text_input("行业名称", value="") or None
        with st.expander("高级选项"):
            report_days = st.number_input("报告交易日", value=70, min_value=5)
            technical_days = st.number_input(
                "技术交易日", value=251, min_value=5
            )
            offline = st.checkbox("离线模式", value=False)
            refresh = st.checkbox("刷新缓存", value=False)
            llm = st.checkbox("启用大模型", value=False)
            allow_paid = st.checkbox("允许付费数据源", value=False)
        submitted = st.form_submit_button("提交分析")

    if not submitted:
        return
    try:
        request = AnalysisRequest(
            ticker=ticker,
            task_type=task.task_type,
            industry_name=industry_name,
            as_of_date=as_of_date,
            investment_horizon=horizon,
            report_days=int(report_days),
            technical_days=int(technical_days),
            llm=bool(llm),
            offline=bool(offline),
            refresh=bool(refresh),
            allow_paid=bool(allow_paid),
        )
        run_id = gateway.create_run(request)
    except Exception as exc:
        st.error(getattr(exc, "message", "提交分析失败"))
        return
    state["selected_run_id"] = run_id
    navigate(state, "run")
    st.success(f"分析已提交：{run_id}")
    st.rerun()

