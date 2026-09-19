import pytest

from support_agent.planner import CasePlanner, Goal, IntentPlanner, PlanningError


def test_intent_planner_extracts_supported_multiple_goals():
    goals = IntentPlanner().extract_goals("停掉自动续费，并把今天扣的钱退给我")

    assert [goal.kind for goal in goals] == ["cancel_renewal", "refund_charge"]
    assert all(goal.account_scope == "current" for goal in goals)


def test_case_planner_orders_dependencies_without_accepting_arbitrary_tools():
    tasks = CasePlanner().validate_and_order([
        Goal("refund_charge", "current", {}),
        Goal("cancel_renewal", "current", {}),
    ])

    assert [task.workflow_id for task in tasks] == ["subscription_cancellation", "refund_request"]
    assert all(not hasattr(task, "tool") for task in tasks)


def test_family_account_target_requires_separate_scope_clarification():
    goals = IntentPlanner().extract_goals("查一下我家人的订阅")

    assert goals[0].account_scope == "other"
    with pytest.raises(PlanningError, match="验证"):
        CasePlanner().validate_and_order(goals)


def test_unsupported_intent_is_rejected():
    with pytest.raises(PlanningError, match="不支持"):
        CasePlanner().validate_and_order(IntentPlanner().extract_goals("帮我修改发票抬头"))
