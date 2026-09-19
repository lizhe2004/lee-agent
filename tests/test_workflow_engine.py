import pytest

from support_agent.models import Case, ToolResult, WorkflowDefinition
from support_agent.workflow_engine import WorkflowEngine, WorkflowExecutionError


class RecordingTools:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def call(self, name, arguments, idempotency_key=None):
        self.calls.append((name, arguments, idempotency_key))
        return self.result


def make_case(node, facts=None):
    return Case("case_1", "demo", 1, node, "active", facts or {})


def test_ask_node_pauses_and_marks_case_waiting_for_user():
    workflow = WorkflowDefinition(
        "demo", 1, "question", {
            "question": {"type": "ask", "collect": ["amount"], "prompt": "Amount?", "next": "done"},
            "done": {"type": "end"},
        }
    )

    outcome = WorkflowEngine().advance(make_case("question"), workflow, RecordingTools(ToolResult("ok")))

    assert outcome.kind == "ask"
    assert outcome.response_nodes[0]["prompt"] == "Amount?"
    assert outcome.response_nodes[0]["collect"] == ["amount"]


def test_action_guard_failure_routes_without_calling_tool():
    workflow = WorkflowDefinition(
        "demo", 1, "lookup", {
            "lookup": {
                "type": "action", "tool": "lookup", "requires": ["session.identity_verified"],
                "on_guard_failure": "verify", "result_statuses": ["success"],
                "transitions": {"success": "done"},
            },
            "verify": {"type": "ask", "collect": [], "prompt": "Verify?", "next": "lookup"},
            "done": {"type": "end"},
        }
    )
    tools = RecordingTools(ToolResult("success"))
    case = make_case("lookup", {"session": {"identity_verified": False}})

    outcome = WorkflowEngine().advance(case, workflow, tools)

    assert outcome.kind == "ask"
    assert case.current_node == "verify"
    assert case.facts["last_guard_failure"] == ["session.identity_verified"]
    assert tools.calls == []


def test_action_success_uses_exact_status_transition_and_persists_result():
    workflow = WorkflowDefinition(
        "demo", 1, "lookup", {
            "lookup": {
                "type": "action", "tool": "lookup", "requires": [],
                "on_guard_failure": "done", "result_statuses": ["found"],
                "transitions": {"found": "done"}, "save_result_as": "lookup_result",
            },
            "done": {"type": "end"},
        }
    )
    tools = RecordingTools(ToolResult("found", {"id": "ord_1"}))
    case = make_case("lookup")

    outcome = WorkflowEngine().advance(case, workflow, tools)

    assert outcome.kind == "finished"
    assert case.facts["lookup_result"] == {"status": "found", "data": {"id": "ord_1"}, "error": None}
    assert case.fact_sources["lookup_result"] == "tool:lookup"
    assert case.fact_sources["id"] == "tool:lookup"
    assert tools.calls == [("lookup", {}, None)]


def test_unknown_tool_status_fails_closed():
    workflow = WorkflowDefinition(
        "demo", 1, "lookup", {
            "lookup": {
                "type": "action", "tool": "lookup", "requires": [],
                "on_guard_failure": "done", "result_statuses": ["found"],
                "transitions": {"found": "done"},
            },
            "done": {"type": "end"},
        }
    )

    with pytest.raises(WorkflowExecutionError, match="unknown status"):
        WorkflowEngine().advance(make_case("lookup"), workflow, RecordingTools(ToolResult("maybe")))


def test_action_consumes_sensitive_fact_after_tool_call():
    workflow = WorkflowDefinition(
        "demo", 1, "verify", {
            "verify": {
                "type": "action", "tool": "verify_otp",
                "args": {"code": "{{ otp_code }}"}, "requires": ["otp_code"],
                "on_guard_failure": "ask", "result_statuses": ["verified"],
                "transitions": {"verified": "done"}, "consume_facts": ["otp_code"],
            },
            "ask": {"type": "ask", "collect": ["otp_code"], "prompt": "Code?", "next": "verify"},
            "done": {"type": "end"},
        }
    )
    tools = RecordingTools(ToolResult("verified", {"target_account_verified": True}))
    case = make_case("verify", {"otp_code": "123456"})

    WorkflowEngine().advance(case, workflow, tools)

    assert tools.calls[0][1] == {"code": "123456"}
    assert "otp_code" not in case.facts
    assert "otp_code" not in case.fact_sources


def test_requirement_can_be_a_boolean_expression_and_templates_interpolate_values():
    workflow = WorkflowDefinition(
        "demo", 1, "run", {
            "run": {
                "type": "action", "tool": "refund", "args": {
                    "key": "{{ case_id }}:refund:{{ order.id }}"
                }, "requires": ["refund_eligibility == 'eligible'"],
                "on_guard_failure": "blocked", "result_statuses": ["submitted"],
                "transitions": {"submitted": "done"},
            },
            "blocked": {"type": "end"},
            "done": {"type": "end"},
        }
    )
    tools = RecordingTools(ToolResult("submitted"))
    case = make_case("run", {"refund_eligibility": "eligible", "order": {"id": "ord_5"}})

    WorkflowEngine().advance(case, workflow, tools)

    assert tools.calls[0][1] == {"key": "case_1:refund:ord_5"}


def test_user_correction_invalidates_stale_derived_facts_and_rewinds_to_recompute_node():
    workflow = WorkflowDefinition(
        "air_booking", 1, "collect_trip", {
            "collect_trip": {"type": "ask", "collect": ["travel_date"], "prompt": "Date?", "next": "search_flights"},
            "search_flights": {"type": "action", "tool": "search", "args": {}, "requires": [], "on_guard_failure": "done", "result_statuses": ["success"], "transitions": {"success": "confirm_booking"}},
            "confirm_booking": {"type": "ask", "collect": ["confirm"], "prompt": "Confirm?", "next": "done"},
            "done": {"type": "end"},
        },
        raw={"mutable_inputs": {
            "travel_date": {
                "type": "string", "on_change": "search_flights", "priority": 10,
                "invalidates": ["flight_search", "selected_flight", "cabin_quote", "booking_confirmation"],
            }
        }},
    )
    case = make_case("confirm_booking", {
        "travel_date": "2026-09-19",
        "flight_search": {"date": "2026-09-19", "options": ["F1"]},
        "selected_flight": "F1",
        "cabin_quote": {"class": "business", "price": 500},
        "booking_confirmation": True,
    })
    case.waiting_for_user = True
    case.fact_revisions["travel_date"] = 1
    case.fact_sources["travel_date"] = "user"

    changed = WorkflowEngine().apply_user_corrections(
        case, workflow, {"travel_date": "2026-09-20"}
    )

    assert changed == ["travel_date"]
    assert case.current_node == "search_flights"
    assert case.facts["travel_date"] == "2026-09-20"
    assert case.fact_revisions["travel_date"] == 2
    assert not any(key in case.facts for key in (
        "flight_search", "selected_flight", "cabin_quote", "booking_confirmation"
    ))
    assert case.waiting_for_user is False
