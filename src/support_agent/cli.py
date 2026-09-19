from __future__ import annotations

import argparse
from pathlib import Path

from support_agent.agent import DemoAgent
from support_agent.harness import Harness
from support_agent.store import SQLiteCaseStore
from support_agent.tools import DemoBackend, build_demo_registry
from support_agent.workflow_loader import load_workflow, validate_workflow


def build_harness(db_path: Path, root: Path) -> Harness:
    backend = DemoBackend()
    tools = build_demo_registry(backend)
    workflows = {}
    for name in ("refund_request", "subscription_cancellation"):
        workflow = load_workflow(root / "workflows" / f"{name}.json")
        validate_workflow(workflow, tools.names)
        workflows[name] = workflow
    return Harness(
        store=SQLiteCaseStore(db_path), workflows=workflows, tools=tools,
        agent=DemoAgent(), skill_dir=root / "skills",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Workflow-guided customer support CLI")
    parser.add_argument("--db", type=Path, default=Path("support-agent.db"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    harness = build_harness(args.db, args.root)
    case_id: str | None = None
    print("客服已就绪。输入 /exit 退出。")
    while True:
        try:
            message = input("你：").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        if message == "/exit":
            break
        case_id, reply = harness.handle_message(case_id, message)
        print(f"客服：{reply}")
        print(f"[case_id: {case_id}]")


if __name__ == "__main__":
    main()
