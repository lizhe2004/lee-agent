from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    status: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass(frozen=True)
class WorkflowDefinition:
    workflow_id: str
    version: int
    start: str
    nodes: dict[str, dict[str, Any]]
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass
class Case:
    case_id: str
    workflow_id: str
    workflow_version: int
    current_node: str
    status: str
    facts: dict[str, Any] = field(default_factory=dict)
    waiting_for_user: bool = False
    visit_counts: dict[str, int] = field(default_factory=dict)
    fact_revisions: dict[str, int] = field(default_factory=dict)
    fact_sources: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Case:
        return cls(
            case_id=value["case_id"],
            workflow_id=value["workflow_id"],
            workflow_version=int(value["workflow_version"]),
            current_node=value["current_node"],
            status=value["status"],
            facts=value.get("facts", {}),
            waiting_for_user=bool(value.get("waiting_for_user", False)),
            visit_counts=value.get("visit_counts", {}),
            fact_revisions=value.get("fact_revisions", {}),
            fact_sources=value.get("fact_sources", {}),
        )
