import pytest

from support_agent.tools import (
    DemoBackend,
    ToolInvocationError,
    ToolRegistry,
    build_demo_registry,
)
from support_agent.models import ToolResult


def test_registry_rejects_unknown_tool_and_invalid_arguments():
    registry = ToolRegistry()
    registry.register("lookup", lambda args, key: ToolResult("ok"), required={"order_id": str})

    with pytest.raises(ToolInvocationError, match="unknown tool"):
        registry.call("missing", {})
    with pytest.raises(ToolInvocationError, match="missing required"):
        registry.call("lookup", {})
    with pytest.raises(ToolInvocationError, match="unexpected arguments"):
        registry.call("lookup", {"order_id": "ord_1", "password": "secret"})
    with pytest.raises(ToolInvocationError, match="must be str"):
        registry.call("lookup", {"order_id": 1})


def test_registry_reuses_idempotent_result_for_same_key():
    registry = ToolRegistry()
    calls = []

    def submit(args, key):
        calls.append(key)
        return ToolResult("submitted", {"request_id": "req_1"})

    registry.register("submit", submit, required={"order_id": str}, idempotent=True)
    first = registry.call("submit", {"order_id": "ord_1"}, "case_1:refund:ord_1")
    second = registry.call("submit", {"order_id": "ord_1"}, "case_1:refund:ord_1")

    assert first == second
    assert calls == ["case_1:refund:ord_1"]


def test_demo_policy_and_provider_guard_keep_apple_refunds_out_of_first_party_tool():
    backend = DemoBackend()
    registry = build_demo_registry(backend)
    apple = backend.orders["ord_apple"]
    registry.call("verify_otp", {"phone": "15500000001", "code": "123456"})

    result = registry.call(
        "submit_refund",
        {"order_id": apple["id"]},
        "case_1:refund:ord_apple",
    )

    assert result.status == "error"
    assert "third-party" in result.error
    assert apple["refund_submitted"] is False


def test_policy_result_is_structured_and_not_inferred_by_registry():
    registry = build_demo_registry(DemoBackend())
    registry.call("bind_current_account", {})
    facts = registry.call("get_refund_facts", {"order_id": "ord_first_party"})

    result = registry.call(
        "evaluate_refund_policy",
        {"order_id": "ord_first_party", "refund_facts": facts.data["refund_facts"]},
    )

    assert result.status == "eligible"
    assert result.data["refund_eligibility"] == "eligible"
    assert "playback_minutes" in result.data["refund_reason_facts"]
