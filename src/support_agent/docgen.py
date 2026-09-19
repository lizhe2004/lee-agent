from __future__ import annotations

from pathlib import Path

from support_agent.models import WorkflowDefinition
from support_agent.workflow_loader import load_workflow


def render_workflow_docs(definition: WorkflowDefinition) -> str:
    lines = [f"# Workflow `{definition.workflow_id} v{definition.version}`", "", f"Start node: `{definition.start}`", "", "## Nodes", ""]
    for node_id, node in definition.nodes.items():
        lines.append(f"### `{node_id}` ({node['type']})")
        if node["type"] == "ask":
            lines.append(f"- Prompt: {node['prompt']}")
            lines.append(f"- Collects: `{', '.join(node['collect'])}`")
            lines.append(f"- Next: `{node['next']}`")
        elif node["type"] == "action":
            lines.append(f"- Tool: `{node['tool']}`")
            lines.append(f"- Requires: `{', '.join(node['requires']) or 'none'}`")
            lines.append(f"- Guard failure: `{node['on_guard_failure']}`")
            lines.append("- Transitions:")
            for status, target in node["transitions"].items():
                lines.append(f"  - `{status}` → `{target}`")
        elif node["type"] == "branch":
            for case in node["cases"]:
                lines.append(f"- If `{case['when']}` → `{case['next']}`")
            lines.append(f"- Default → `{node['default']}`")
        elif node["type"] == "respond":
            lines.append(f"- Template: {node['template']}")
            if "next" in node:
                lines.append(f"- Next: `{node['next']}`")
        elif node["type"] == "wait":
            lines.append(f"- Event: `{node['event']}`")
        lines.append("")
    return "\n".join(lines)


def generate_docs(workflow_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in sorted(workflow_dir.glob("*.json")):
        definition = load_workflow(path)
        (output_dir / f"{definition.workflow_id}.md").write_text(render_workflow_docs(definition))
