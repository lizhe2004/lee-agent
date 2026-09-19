from __future__ import annotations

from pathlib import Path
from typing import Any

from support_agent.agent import Agent
from support_agent.models import Case, WorkflowDefinition
from support_agent.store import SQLiteCaseStore
from support_agent.tools import ToolRegistry, ToolInvocationError
from support_agent.workflow_engine import WorkflowEngine, WorkflowExecutionError


class Harness:
    def __init__(self, *, store: SQLiteCaseStore, workflows: dict[str, WorkflowDefinition], tools: ToolRegistry, agent: Agent, skill_dir: Path):
        self.store = store
        self.workflows = workflows
        self.tools = tools
        self.agent = agent
        self.skill_dir = skill_dir
        self.engine = WorkflowEngine()

    def handle_message(self, case_id: str | None, message: str) -> tuple[str, str]:
        if case_id is None:
            workflow_id = self._route_workflow(message)
            workflow = self.workflows[workflow_id]
            case = self.store.create_case(workflow_id, workflow.version, workflow.start)
            case.facts["session"] = {"authenticated": True}
        else:
            case = self.store.get_case(case_id)
            workflow = self.workflows[case.workflow_id]

        skill = self._load_skill(case.workflow_id)
        if case.waiting_for_user:
            node = workflow.nodes[case.current_node]
            updates = self.agent.extract_fields(message, node.get("collect", []), skill)
            correction = self._extract_correction(case, workflow, message)
            if correction:
                self.engine.apply_user_corrections(case, workflow, correction)
            else:
                self._merge_user_facts(case, updates, node)
                case.current_node = node["next"]
            case.waiting_for_user = False
            case.status = "active"

        try:
            outcome = self.engine.advance(case, workflow, self.tools)
        except (WorkflowExecutionError, ToolInvocationError) as exc:
            case.status = "blocked"
            self.store.append_event(case.case_id, "workflow_error", {"error": str(exc)})
            self.store.save_case(case)
            return case.case_id, "当前流程无法安全继续，已停止自动操作并转人工处理。"

        self.store.save_case(case)
        self.store.append_event(case.case_id, "turn", {"node": case.current_node, "status": case.status})
        if outcome.response_nodes:
            return case.case_id, self.agent.write_reply(outcome.response_nodes[-1], {**case.facts, "case_id": case.case_id}, skill)
        if outcome.kind == "finished":
            return case.case_id, "本次处理已结束。"
        if outcome.kind == "wait":
            return case.case_id, "案件已进入等待处理状态。"
        return case.case_id, "我需要你补充一些信息。"

    @staticmethod
    def _merge_user_facts(case: Case, updates: dict[str, Any], node: dict[str, Any]) -> None:
        sensitive = set(node.get("sensitive_collect", []))
        for key, value in updates.items():
            if key in sensitive:
                case.facts[key] = value
                continue
            case.facts[key] = value
            case.fact_sources[key] = "user"
            case.fact_revisions[key] = case.fact_revisions.get(key, 0) + 1

    @staticmethod
    def _extract_correction(case: Case, workflow: WorkflowDefinition, message: str) -> dict[str, Any]:
        if not any(word in message for word in ("改成", "改为", "换成", "改到")):
            return {}
        # The demo agent supplies date parsing; only declared mutable inputs are accepted.
        from support_agent.agent import DemoAgent
        mutable = workflow.raw.get("mutable_inputs", {})
        expected = list(mutable)
        return {key: value for key, value in DemoAgent().extract_fields(message, expected).items() if key in mutable}

    def _route_workflow(self, message: str) -> str:
        lowered = message.lower()
        if any(word in message for word in ("续费", "订阅", "自动扣款")) and "退款" not in message:
            return "subscription_cancellation"
        return "refund_request"

    def _load_skill(self, workflow_id: str) -> str:
        path = self.skill_dir / workflow_id / "SKILL.md"
        return path.read_text() if path.exists() else ""
