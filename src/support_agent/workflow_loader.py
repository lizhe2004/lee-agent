from __future__ import annotations

import ast
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from support_agent.models import WorkflowDefinition


ALLOWED_EXPRESSION_NODES = (
    ast.Expression,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Name,
    ast.Load,
    ast.Attribute,
    ast.Constant,
)


class WorkflowDefinitionError(ValueError):
    pass


def load_workflow(path: Path) -> WorkflowDefinition:
    try:
        raw = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkflowDefinitionError(f"cannot load workflow JSON {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise WorkflowDefinitionError("workflow must be a JSON object")
    try:
        return WorkflowDefinition(
            workflow_id=raw["id"],
            version=raw["version"],
            start=raw["start"],
            nodes=raw["nodes"],
            raw=raw,
        )
    except (KeyError, TypeError) as exc:
        raise WorkflowDefinitionError("workflow requires id, version, start, and nodes") from exc


def validate_workflow(
    definition: WorkflowDefinition,
    tool_names: set[str],
) -> None:
    raw = definition.raw or {
        "id": definition.workflow_id,
        "version": definition.version,
        "start": definition.start,
        "nodes": definition.nodes,
    }
    validator = Draft202012Validator(_schema())
    errors = sorted(validator.iter_errors(raw), key=lambda error: list(error.absolute_path))
    if errors:
        details = "; ".join(
            f"{'.'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in errors
        )
        raise WorkflowDefinitionError(f"workflow schema validation failed: {details}")

    if definition.start not in definition.nodes:
        raise WorkflowDefinitionError("start node is missing")

    targets: list[str] = []
    collected_fields: set[str] = set()
    for node_id, node in definition.nodes.items():
        node_type = node["type"]
        if node_type == "ask":
            collected_fields.update(node["collect"])
            targets.append(node["next"])
            if "on_limit" in node:
                targets.append(node["on_limit"])
        elif node_type == "branch":
            for case in node["cases"]:
                validate_expression(case["when"])
                targets.append(case["next"])
            targets.append(node["default"])
            if "on_limit" in node:
                targets.append(node["on_limit"])
        elif node_type == "action":
            if node["tool"] not in tool_names:
                raise WorkflowDefinitionError(
                    f"unregistered tool at {node_id}: {node['tool']}"
                )
            validate_status_mapping(node_id, node)
            targets.append(node["on_guard_failure"])
            targets.extend(node["transitions"].values())
            if "on_limit" in node:
                targets.append(node["on_limit"])
        elif node_type == "respond":
            if "next" in node:
                targets.append(node["next"])
            if "on_limit" in node:
                targets.append(node["on_limit"])
        elif node_type == "wait" and "next" in node:
            targets.append(node["next"])

    for input_name, config in raw.get("mutable_inputs", {}).items():
        if input_name not in collected_fields:
            raise WorkflowDefinitionError(
                f"mutable input {input_name} is not collected by any ask node"
            )
        targets.append(config["on_change"])

    for target in targets:
        if target not in definition.nodes:
            raise WorkflowDefinitionError(f"unknown target node: {target}")


def validate_status_mapping(node_id: str, node: dict[str, Any]) -> None:
    declared = set(node["result_statuses"])
    configured = set(node["transitions"])
    if declared != configured:
        missing = sorted(declared - configured)
        extra = sorted(configured - declared)
        raise WorkflowDefinitionError(
            f"action {node_id} transitions mismatch; missing={missing}, extra={extra}"
        )


def validate_expression(expression: str) -> None:
    try:
        tree = ast.parse(_normalize_expression(expression), mode="eval")
    except SyntaxError as exc:
        raise WorkflowDefinitionError(f"invalid expression: {expression}") from exc
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED_EXPRESSION_NODES):
            raise WorkflowDefinitionError(
                f"unsafe expression node in {expression}: {type(node).__name__}"
            )
    if not isinstance(tree.body, (ast.Compare, ast.BoolOp)):
        raise WorkflowDefinitionError("expression must be a comparison or boolean expression")


def evaluate_expression(expression: str, facts: dict[str, Any]) -> bool:
    validate_expression(expression)
    tree = ast.parse(_normalize_expression(expression), mode="eval")
    return bool(_evaluate(tree.body, facts))


@lru_cache(maxsize=1)
def _schema() -> dict[str, Any]:
    schema_path = Path(__file__).resolve().parents[2] / "schemas" / "workflow.schema.json"
    try:
        schema = json.loads(schema_path.read_text())
        Draft202012Validator.check_schema(schema)
    except (OSError, json.JSONDecodeError, SchemaError) as exc:
        raise WorkflowDefinitionError(f"cannot load valid workflow schema: {exc}") from exc
    return schema


def _normalize_expression(expression: str) -> str:
    expression = re.sub(r"\btrue\b", "True", expression, flags=re.IGNORECASE)
    expression = re.sub(r"\bfalse\b", "False", expression, flags=re.IGNORECASE)
    return re.sub(r"\bnull\b", "None", expression, flags=re.IGNORECASE)


def _evaluate(node: ast.AST, facts: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return facts.get(node.id)
    if isinstance(node, ast.Attribute):
        parent = _evaluate(node.value, facts)
        return parent.get(node.attr) if isinstance(parent, dict) else None
    if isinstance(node, ast.BoolOp):
        values = [_evaluate(value, facts) for value in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)
    if isinstance(node, ast.Compare):
        left = _evaluate(node.left, facts)
        for operator, comparator in zip(node.ops, node.comparators):
            right = _evaluate(comparator, facts)
            passed = left == right if isinstance(operator, ast.Eq) else left != right
            if not passed:
                return False
            left = right
        return True
    raise WorkflowDefinitionError(f"unsupported expression node: {type(node).__name__}")
