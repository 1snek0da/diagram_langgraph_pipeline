from streamlit_app import PAGE_RENDERERS, main

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

