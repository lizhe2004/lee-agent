import json

from support_agent.docgen import render_workflow_docs
from support_agent.workflow_loader import load_workflow


def test_rendered_docs_include_nodes_guards_tools_and_transitions(tmp_path):
    path = tmp_path / "flow.json"
    path.write_text(json.dumps({
        "id": "sample", "version": 1, "start": "ask", "nodes": {
            "ask": {"type": "ask", "collect": ["name"], "prompt": "Name?", "next": "act"},
            "act": {"type": "action", "tool": "lookup", "args": {}, "requires": ["name"], "on_guard_failure": "ask", "result_statuses": ["ok"], "transitions": {"ok": "done"}},
            "done": {"type": "end"},
        },
    }))
    text = render_workflow_docs(load_workflow(path))
    assert "sample v1" in text
    assert "lookup" in text
    assert "name" in text
    assert "ok" in text
