from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from support_agent.models import Case, ToolResult, WorkflowDefinition
from support_agent.workflow_loader import evaluate_expression


class WorkflowExecutionError(RuntimeError):
    pass


class ToolRunner(Protocol):
    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> ToolResult: ...


@dataclass
class EngineOutcome:
    kind: Literal["ask", "wait", "finished"]
    response_nodes: list[dict[str, Any]] = field(default_factory=list)


class WorkflowEngine:
    def __init__(self, max_auto_steps: int = 100):
        self.max_auto_steps = max_auto_steps

    def apply_user_corrections(
        self,
        case: Case,
        workflow: WorkflowDefinition,
        updates: dict[str, Any],
    ) -> list[str]:
        mutable_inputs = workflow.raw.get("mutable_inputs", {})
        unknown = set(updates) - set(mutable_inputs)
        if unknown:
            raise WorkflowExecutionError(f"facts are not declared as mutable inputs: {sorted(unknown)}")

        changed: list[str] = []
        selected_route: tuple[int, str] | None = None
        invalidated: set[str] = set()
        for name, value in updates.items():
            config = mutable_inputs[name]
            _validate_user_value(name, value, config)
            source = case.fact_sources.get(name)
            if source not in (None, "user"):
                raise WorkflowExecutionError(f"cannot overwrite trusted fact: {name}")
            existed = name in case.facts
            previous = case.facts.get(name)
            if existed and previous == value:
                continue

            case.facts[name] = value
            case.fact_sources[name] = "user"
            case.fact_revisions[name] = case.fact_revisions.get(name, 0) + 1
            if not existed:
                continue

            changed.append(name)
            invalidated.update(config["invalidates"])
            route = (config["priority"], config["on_change"])
            if selected_route is None or route[0] < selected_route[0]:
                selected_route = route

        if changed and selected_route:
            for path in invalidated:
                _delete_fact(case.facts, path)
                _delete_fact(case.fact_sources, path)
                _delete_fact(case.fact_revisions, path)
            case.current_node = selected_route[1]
            case.waiting_for_user = False
            case.status = "active"
        return changed

    def advance(
        self,
        case: Case,
        workflow: WorkflowDefinition,
        tools: ToolRunner,
    ) -> EngineOutcome:
        response_nodes: list[dict[str, Any]] = []
        for _ in range(self.max_auto_steps):
            node_id = case.current_node
            node = workflow.nodes.get(node_id)
            if node is None:
                raise WorkflowExecutionError(f"unknown current node: {node_id}")

            case.visit_counts[node_id] = case.visit_counts.get(node_id, 0) + 1
            max_visits = node.get("max_visits")
            if max_visits is not None and case.visit_counts[node_id] > max_visits:
                limit_target = node.get("on_limit")
                if not limit_target:
                    raise WorkflowExecutionError(f"node {node_id} exceeded max visits")
                case.current_node = limit_target
                continue

            node_type = node["type"]
            if node_type == "ask":
                case.waiting_for_user = True
                case.status = "waiting_for_user"
                response_nodes.append(node)
                return EngineOutcome("ask", response_nodes)

            if node_type == "branch":
                next_node = node["default"]
                for branch in node.get("cases", []):
                    if evaluate_expression(branch["when"], case.facts):
                        next_node = branch["next"]
                        break
                case.current_node = next_node
                continue

            if node_type == "action":
                missing = [
                    requirement
                    for requirement in node["requires"]
                    if not _requirement_satisfied(requirement, case.facts)
                ]
                if missing:
                    case.facts["last_guard_failure"] = missing
                    case.current_node = node["on_guard_failure"]
                    continue

                template_facts = {**case.facts, "case_id": case.case_id}
                arguments = _resolve_value(node.get("args", {}), template_facts)
                if not isinstance(arguments, dict):
                    raise WorkflowExecutionError(f"action arguments for {node_id} must be a mapping")
                try:
                    result = tools.call(
                        node["tool"],
                        arguments,
                        _resolve_value(node.get("idempotency_key"), template_facts),
                    )
                finally:
                    for path in node.get("consume_facts", []):
                        _delete_fact(case.facts, path)
                        _delete_fact(case.fact_sources, path)
                        _delete_fact(case.fact_revisions, path)
                if not isinstance(result, ToolResult):
                    raise WorkflowExecutionError(f"tool {node['tool']} returned an invalid result")
                if result.status not in node["result_statuses"]:
                    raise WorkflowExecutionError(
                        f"tool {node['tool']} returned unknown status: {result.status}"
                    )
                save_as = node.get("save_result_as")
                if save_as:
                    _record_fact(case, save_as, {
                        "status": result.status,
                        "data": result.data,
                        "error": result.error,
                    }, f"tool:{node['tool']}")
                    if result.data:
                        for fact_name, fact_value in result.data.items():
                            _record_fact(case, fact_name, fact_value, f"tool:{node['tool']}")
                case.current_node = node["transitions"][result.status]
                continue

            if node_type == "respond":
                response_nodes.append(node)
                if "next" in node:
                    case.current_node = node["next"]
                    continue
                case.status = "completed"
                case.waiting_for_user = False
                return EngineOutcome("finished", response_nodes)

            if node_type == "wait":
                case.status = "waiting_for_event"
                case.waiting_for_user = False
                return EngineOutcome("wait", response_nodes)

            if node_type == "end":
                case.status = "completed"
                case.waiting_for_user = False
                return EngineOutcome("finished", response_nodes)

            raise WorkflowExecutionError(f"unsupported node type: {node_type}")

        raise WorkflowExecutionError("workflow exceeded maximum automatic steps")


def _fact_value(facts: dict[str, Any], path: str) -> Any:
    current: Any = facts
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _requirement_satisfied(requirement: str, facts: dict[str, Any]) -> bool:
    if "==" in requirement or "!=" in requirement or " and " in requirement or " or " in requirement:
        return evaluate_expression(requirement, facts)
    return bool(_fact_value(facts, requirement))


def _delete_fact(facts: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    parent: Any = facts
    for part in parts[:-1]:
        if not isinstance(parent, dict) or part not in parent:
            return
        parent = parent[part]
    if isinstance(parent, dict):
        parent.pop(parts[-1], None)


def _record_fact(case: Case, name: str, value: Any, source: str) -> None:
    case.facts[name] = value
    case.fact_sources[name] = source
    case.fact_revisions[name] = case.fact_revisions.get(name, 0) + 1


def _validate_user_value(name: str, value: Any, config: dict[str, Any]) -> None:
    expected = config["type"]
    valid = {
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "null": value is None,
    }.get(expected, False)
    if not valid:
        raise WorkflowExecutionError(f"user input {name} must have type {expected}")
    if "enum" in config and value not in config["enum"]:
        raise WorkflowExecutionError(f"user input {name} is not an allowed value")


def _resolve_value(value: Any, facts: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_value(item, facts) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, facts) for item in value]
    if isinstance(value, str):
        match = re.fullmatch(r"\{\{\s*([a-zA-Z_][\w.]*)\s*}}", value)
        if match:
            return _fact_value(facts, match.group(1))
        return re.sub(
            r"\{\{\s*([a-zA-Z_][\w.]*)\s*}}",
            lambda found: str(_fact_value(facts, found.group(1)) or ""),
            value,
        )
    return value
