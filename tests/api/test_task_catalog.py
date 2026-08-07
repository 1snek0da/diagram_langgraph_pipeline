from diagram_langgraph_pipeline.api.catalog import task_catalog
from diagram_langgraph_pipeline.routing import TaskType, get_execution_plan


def test_catalog_is_derived_from_every_router_plan():
    records = task_catalog(paid_sources_available=False)

    assert [record.task_type for record in records] == list(TaskType)
    for record in records:
        plan = get_execution_plan(record.task_type)
        assert record.required_nodes == plan.required_nodes
        assert record.support_nodes == plan.support_nodes
        assert record.optional_nodes == plan.optional_nodes
        assert record.skipped_nodes == plan.skipped_nodes
        assert record.required_inputs == plan.required_inputs
        assert record.conclusion_scope == plan.conclusion_scope
        assert record.paid_sources_available is False


def test_catalog_display_copy_is_readable_chinese():
    records = task_catalog(paid_sources_available=True)

    assert all(record.display_name.strip() for record in records)
    assert all(record.description.strip() for record in records)
    assert all(record.paid_sources_available is True for record in records)
