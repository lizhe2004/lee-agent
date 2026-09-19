from support_agent.models import Case, ToolResult


def test_tool_result_keeps_structured_data_and_error():
    result = ToolResult(
        status="found",
        data={"order_id": "ord_123", "channel": "apple"},
    )

    assert result.status == "found"
    assert result.data["order_id"] == "ord_123"
    assert result.error is None


def test_case_json_round_trip_preserves_version_and_nested_facts():
    original = Case(
        case_id="case_1",
        workflow_id="refund_request",
        workflow_version=1,
        current_node="find_order",
        status="active",
        facts={"session": {"identity_verified": True}},
        waiting_for_user=False,
        visit_counts={"find_order": 1},
    )

    restored = Case.from_dict(original.to_dict())

    assert restored == original
