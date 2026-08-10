from pathlib import Path


def test_fastapi_app_factory_imports():
    from diagram_langgraph_pipeline.api.app import create_app

    assert callable(create_app)


def test_streamlit_entrypoint_imports_without_starting_server():
    import streamlit_app

    assert callable(streamlit_app.main)


def test_launch_scripts_target_api_and_streamlit_entrypoints():
    api_script = Path("scripts/start_api.ps1").read_text(encoding="utf-8")
    ui_script = Path("scripts/start_streamlit.ps1").read_text(encoding="utf-8")

    assert "diagram_langgraph_pipeline.api.app:create_app" in api_script
    assert "--factory" in api_script
    assert "streamlit run streamlit_app.py" in ui_script


def test_env_example_lists_web_runtime_settings():
    text = Path(".env.example").read_text(encoding="utf-8")

    assert "DLP_API_BASE_URL=" in text
    assert "DLP_API_MAX_WORKERS=1" in text
    assert "DLP_CORS_ORIGINS=" in text

