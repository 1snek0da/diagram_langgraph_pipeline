from diagram_langgraph_pipeline.ui.models import ReportView
from diagram_langgraph_pipeline.ui.pages.report import render

from .fakes import FakeGateway, FakeStreamlit


def test_report_download_uses_markdown_content_not_server_path():
    gateway = FakeGateway(
        report=ReportView(run_id="run-1", markdown="# 报告")
    )
    st = FakeStreamlit()

    render(st, gateway, {"selected_run_id": "run-1"})

    assert st.downloads[0].data == "# 报告"
    assert st.downloads[0].file_name == "research_run-1.md"
    assert "report_path" not in st.downloads[0].data

