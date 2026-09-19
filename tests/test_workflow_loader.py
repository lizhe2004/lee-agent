import json

import pytest

from support_agent.workflow_loader import WorkflowDefinitionError, load_workflow, validate_workflow


def save_definition(tmp_path, definition):
    path = tmp_path / "workflow.json"
    path.write_text(json.dumps(definition))
    return path


def valid_workflow():
    return {
        "id": "sample",
        "version": 1,
        "start": "choose",
        "nodes": {
            "choose": {
                "type": "branch",
                "cases": [
                    {
                        "when": "order.channel == 'apple' and session.identity_verified == true",
                        "next": "done",
                    }
                ],
                "default": "done",
            },
            "done": {"type": "end"},
        },
    }


def valid_action_workflow():
    return {
        "id": "sample",
        "version": 1,
        "start": "act",
        "nodes": {
            "act": {
                "type": "action",
                "tool": "find_order",
                "args": {},
                "requires": [],
                "on_guard_failure": "done",
                "result_statuses": ["found", "error"],
                "transitions": {"found": "done", "error": "done"},
            },
            "done": {"type": "end"},
        },
    }


def test_loads_valid_json_workflow_and_rejects_unsafe_branch_expression(tmp_path):
    definition = load_workflow(save_definition(tmp_path, valid_workflow()))
    validate_workflow(definition, set())
    assert definition.workflow_id == "sample"
    assert definition.start == "choose"

    unsafe = valid_workflow()
    unsafe["nodes"]["choose"]["cases"][0]["when"] = "__import__('os').system('true')"
    with pytest.raises(WorkflowDefinitionError, match="expression"):
        validate_workflow(load_workflow(save_definition(tmp_path, unsafe)), set())


def test_json_schema_rejects_unknown_node_type_and_extra_fields(tmp_path):
    invalid_type = valid_workflow()
    invalid_type["nodes"]["done"] = {"type": "teleport"}
    with pytest.raises(WorkflowDefinitionError, match="schema"):
        validate_workflow(load_workflow(save_definition(tmp_path, invalid_type)), set())

    extra_field = valid_workflow()
    extra_field["surprise"] = True
    with pytest.raises(WorkflowDefinitionError, match="schema"):
        validate_workflow(load_workflow(save_definition(tmp_path, extra_field)), set())


def test_semantic_validation_rejects_missing_target_and_unregistered_tool(tmp_path):
    missing_target = valid_workflow()
    missing_target["nodes"]["choose"]["default"] = "missing"
    with pytest.raises(WorkflowDefinitionError, match="unknown target"):
        validate_workflow(load_workflow(save_definition(tmp_path, missing_target)), set())

    with pytest.raises(WorkflowDefinitionError, match="unregistered tool"):
        validate_workflow(
            load_workflow(save_definition(tmp_path, valid_action_workflow())), set()
        )


def test_semantic_validation_requires_complete_tool_status_mapping(tmp_path):
    definition = valid_action_workflow()
    del definition["nodes"]["act"]["transitions"]["error"]

    with pytest.raises(WorkflowDefinitionError, match="transitions"):
        validate_workflow(
            load_workflow(save_definition(tmp_path, definition)), {"find_order"}
        )


def test_json_schema_requires_guard_failure_route_for_actions(tmp_path):
    definition = valid_action_workflow()
    del definition["nodes"]["act"]["on_guard_failure"]

    with pytest.raises(WorkflowDefinitionError, match="schema"):
        validate_workflow(
            load_workflow(save_definition(tmp_path, definition)), {"find_order"}
        )


def test_mutable_inputs_declare_type_restart_node_and_invalidated_facts(tmp_path):
    definition = valid_workflow()
    definition["start"] = "collect"
    definition["nodes"]["collect"] = {
        "type": "ask", "collect": ["travel_date"], "prompt": "Date?", "next": "choose"
    }
    definition["mutable_inputs"] = {
        "travel_date": {
            "type": "string",
            "on_change": "choose",
            "priority": 10,
            "invalidates": ["flight_search", "selected_flight", "quote"],
        }
    }
    validate_workflow(load_workflow(save_definition(tmp_path, definition)), set())

    definition["mutable_inputs"]["travel_date"]["on_change"] = "missing"
    with pytest.raises(WorkflowDefinitionError, match="unknown target"):
        validate_workflow(load_workflow(save_definition(tmp_path, definition)), set())


def test_checked_in_customer_support_workflows_validate():
    from pathlib import Path

    root = Path(__file__).parents[1]
    tool_names = {
        "bind_current_account",
        "send_otp",
        "verify_otp",
        "find_order",
        "get_refund_facts",
        "evaluate_refund_policy",
        "submit_refund",
        "find_subscription",
        "cancel_subscription",
        "create_handoff",
    }

    for name in ("refund_request", "subscription_cancellation"):
        definition = load_workflow(root / "workflows" / f"{name}.json")
        validate_workflow(definition, tool_names)
