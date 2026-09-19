from support_agent.store import SQLiteCaseStore


def test_case_store_round_trips_case_and_appends_events(tmp_path):
    store = SQLiteCaseStore(tmp_path / "cases.db")
    case = store.create_case("refund_request", 2, "collect_order_clues")
    case.facts["session"] = {"identity_verified": True}
    store.save_case(case)
    store.append_event(case.case_id, "tool_result", {"status": "verified"})

    restored = store.get_case(case.case_id)

    assert restored.workflow_version == 2
    assert restored.facts == {"session": {"identity_verified": True}}
    assert store.list_events(case.case_id) == [
        {"event_type": "tool_result", "payload": {"status": "verified"}}
    ]
