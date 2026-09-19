from pathlib import Path

from support_agent.cli import build_harness


def test_cli_harness_runs_scriptable_first_party_refund(tmp_path):
    harness = build_harness(tmp_path / "cli.db", Path(__file__).parents[1])
    case_id, first = harness.handle_message(None, "我要退款")
    assert "扣款日期" in first
    case_id, second = harness.handle_message(case_id, "2026-09-10，19.9元，当前账号")
    assert "符合退款申请条件" in second
    case_id, third = harness.handle_message(case_id, "确认提交")
    assert "已提交" in third
