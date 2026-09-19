from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class PlanningError(ValueError):
    pass


@dataclass(frozen=True)
class Goal:
    kind: str
    account_scope: str
    target_hint: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkflowTask:
    workflow_id: str
    account_scope: str
    goal: Goal


class IntentPlanner:
    def extract_goals(self, message: str) -> list[Goal]:
        candidates: list[tuple[int, Goal]] = []
        scope = "other" if any(word in message for word in ("家人", "老公", "老婆", "另一个账号")) else "current"
        for kind, phrases in (
            ("refund_charge", ("退款", "退费", "退钱", "扣的钱")),
            ("cancel_renewal", ("续费", "订阅", "自动扣款")),
            ("lookup_subscription", ("查订阅", "有哪些订阅", "看看订阅")),
        ):
            positions = [message.find(phrase) for phrase in phrases if message.find(phrase) >= 0]
            if positions:
                candidates.append((min(positions), Goal(kind, scope)))
        goals = [goal for _, goal in sorted(candidates, key=lambda item: item[0])]
        if any(goal.kind == "cancel_renewal" for goal in goals):
            goals = [goal for goal in goals if goal.kind != "lookup_subscription"]
        return goals


class CasePlanner:
    WORKFLOWS = {
        "refund_charge": "refund_request",
        "cancel_renewal": "subscription_cancellation",
        "lookup_subscription": "subscription_cancellation",
    }
    ORDER = {"cancel_renewal": 0, "lookup_subscription": 0, "refund_charge": 1}

    def validate_and_order(self, goals: list[Goal]) -> list[WorkflowTask]:
        if not goals:
            raise PlanningError("不支持或无法识别的客诉意图")
        unique: dict[tuple[str, str], Goal] = {(goal.kind, goal.account_scope): goal for goal in goals}
        for goal in unique.values():
            if goal.kind not in self.WORKFLOWS:
                raise PlanningError(f"不支持的目标: {goal.kind}")
            if goal.account_scope == "other":
                raise PlanningError("处理其他账号前需要先完成该账号的身份验证")
        ordered = sorted(unique.values(), key=lambda goal: self.ORDER[goal.kind])
        return [WorkflowTask(self.WORKFLOWS[goal.kind], goal.account_scope, goal) for goal in ordered]
