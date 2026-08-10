"""Research report display and safe Markdown download."""

from __future__ import annotations

from ..components import page_heading
from ..state import initialize_ui_state


def render(st, gateway, state) -> None:
    initialize_ui_state(state)
    page_heading(st, "研究报告", "报告内容来自 API，服务器路径不会进入浏览器状态。")
    run_id = state.get("selected_run_id")
    if not run_id:
        st.info("请先选择一次运行。")
        return
    try:
        report = gateway.get_report(run_id)
    except Exception as exc:
        st.warning(getattr(exc, "message", "报告暂不可用"))
        return
    st.subheader("研究范围")
    st.write("当前运行的 Router 任务范围由节点页展示。")
    st.subheader("Review")
    st.write("报告中的审查结论与限制条件。")
    st.subheader("数据缺失与降级")
    st.write("请结合节点状态判断可选数据源是否降级。")
    st.subheader("Token 使用")
    st.write("仅展示服务端已汇总的安全摘要。")
    st.subheader("Markdown")
    st.markdown(report.markdown)
    st.download_button(
        "下载 Markdown",
        data=report.markdown,
        file_name=f"research_{report.run_id}.md",
        mime="text/markdown",
    )

