from streamlit_app import PAGE_LABELS, PAGE_RENDERERS, main

from .fakes import FakeGateway, FakeStreamlit, five_task_views


def test_application_registers_all_six_pages():
    assert set(PAGE_RENDERERS) == {
        "workspace", "analysis", "workflow", "market", "report", "history"
    }


def test_application_handles_gateway_configuration_errors_without_crashing():
    st = FakeStreamlit()
    gateway = FakeGateway(task_types=five_task_views())

    main(st_module=st, gateway=gateway)

    assert st.session_state["page"] == "workspace"


def test_application_shows_six_page_navigation_and_opens_selected_page():
    st = FakeStreamlit(values={"页面导航": "新建分析"})
    gateway = FakeGateway(task_types=five_task_views())

    main(st_module=st, gateway=gateway)

    assert st.segmented_controls == [("页面导航", tuple(PAGE_LABELS))]
    assert st.session_state["page"] == "analysis"
    assert "新建分析" in st.rendered_text
