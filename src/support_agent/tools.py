from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from support_agent.models import ToolResult


class ToolInvocationError(RuntimeError):
    pass


ToolFunction = Callable[[dict[str, Any], str | None], ToolResult]


class Tool(Protocol):
    def call(self, arguments: dict[str, Any], idempotency_key: str | None) -> ToolResult: ...


@dataclass
class ToolRegistration:
    function: ToolFunction
    required: dict[str, type | tuple[type, ...]] = field(default_factory=dict)
    optional: dict[str, type | tuple[type, ...]] = field(default_factory=dict)
    idempotent: bool = False


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, ToolRegistration] = {}
        self._idempotency_results: dict[tuple[str, str], ToolResult] = {}

    @property
    def names(self) -> set[str]:
        return set(self._tools)

    def register(
        self,
        name: str,
        function: ToolFunction,
        *,
        required: dict[str, type | tuple[type, ...]] | None = None,
        optional: dict[str, type | tuple[type, ...]] | None = None,
        idempotent: bool = False,
    ) -> None:
        if name in self._tools:
            raise ToolInvocationError(f"tool already registered: {name}")
        self._tools[name] = ToolRegistration(
            function=function,
            required=required or {},
            optional=optional or {},
            idempotent=idempotent,
        )

    def call(
        self,
        name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> ToolResult:
        registration = self._tools.get(name)
        if registration is None:
            raise ToolInvocationError(f"unknown tool: {name}")
        self._validate_arguments(name, arguments, registration)

        cache_key = (name, idempotency_key) if idempotency_key else None
        if registration.idempotent and not idempotency_key:
            raise ToolInvocationError(f"tool {name} requires an idempotency key")
        if cache_key and cache_key in self._idempotency_results:
            return self._idempotency_results[cache_key]

        try:
            result = registration.function(arguments, idempotency_key)
        except Exception:
            result = ToolResult("error", error="tool execution failed")
        if not isinstance(result, ToolResult):
            raise ToolInvocationError(f"tool {name} returned an invalid result")
        if cache_key:
            self._idempotency_results[cache_key] = result
        return result

    @staticmethod
    def _validate_arguments(
        name: str,
        arguments: dict[str, Any],
        registration: ToolRegistration,
    ) -> None:
        if not isinstance(arguments, dict):
            raise ToolInvocationError(f"arguments for {name} must be an object")
        required = registration.required
        optional = registration.optional
        missing = set(required) - set(arguments)
        if missing:
            raise ToolInvocationError(f"missing required arguments for {name}: {sorted(missing)}")
        unexpected = set(arguments) - set(required) - set(optional)
        if unexpected:
            raise ToolInvocationError(f"unexpected arguments for {name}: {sorted(unexpected)}")
        for key, value in arguments.items():
            allowed_types = required.get(key, optional.get(key))
            if allowed_types is not None and not isinstance(value, allowed_types):
                type_name = getattr(allowed_types, "__name__", str(allowed_types))
                raise ToolInvocationError(f"argument {key} for {name} must be {type_name}")


class DemoBackend:
    """Deterministic local fixtures; these methods do not contact real providers."""

    def __init__(self):
        self.current_account_id = "acct_current"
        self.current_phone = "13800000000"
        self.otp_code = "123456"
        self.verified_account_id: str | None = None
        self.sent_otp_to: list[str] = []
        self.handoffs: list[dict[str, Any]] = []
        self.orders: dict[str, dict[str, Any]] = {
            "ord_first_party": {
                "id": "ord_first_party", "account_id": "acct_current", "date": "2026-09-10",
                "amount": 19.9, "channel": "first_party", "playback_minutes": 0,
                "prior_refunds": 0, "refund_submitted": False,
            },
            "ord_apple": {
                "id": "ord_apple", "account_id": "acct_other", "date": "2026-09-11",
                "amount": 9.9, "channel": "apple", "playback_minutes": 0,
                "prior_refunds": 0, "refund_submitted": False,
            },
        }
        self.subscriptions: dict[str, dict[str, Any]] = {
            "sub_first_party": {
                "id": "sub_first_party", "account_id": "acct_current", "channel": "first_party",
                "status": "active", "auto_renew": True, "hint": "monthly plan",
            },
            "sub_apple": {
                "id": "sub_apple", "account_id": "acct_current", "channel": "apple",
                "status": "active", "auto_renew": True, "hint": "apple plan",
            },
        }

    def bind_current_account(self, arguments: dict[str, Any], key: str | None) -> ToolResult:
        self.verified_account_id = self.current_account_id
        return ToolResult("bound", {"target_account_verified": True, "target_account_id": self.current_account_id})

    def send_otp(self, arguments: dict[str, Any], key: str | None) -> ToolResult:
        phone = arguments["phone"]
        self.sent_otp_to.append(phone)
        return ToolResult("sent", {"otp_sent": True})

    def verify_otp(self, arguments: dict[str, Any], key: str | None) -> ToolResult:
        if arguments["code"] != self.otp_code:
            return ToolResult("failed")
        self.verified_account_id = "acct_other" if arguments["phone"] != self.current_phone else "acct_current"
        return ToolResult("verified", {"target_account_verified": True, "target_account_id": self.verified_account_id})

    def find_order(self, arguments: dict[str, Any], key: str | None) -> ToolResult:
        if self.verified_account_id is None:
            return ToolResult("error", error="account is not verified")
        for order in self.orders.values():
            if order["account_id"] != self.verified_account_id:
                continue
            if order["date"] == arguments["charge_date"] and order["amount"] == arguments["amount"]:
                return ToolResult("found", {"order": {key: order[key] for key in ("id", "channel", "date", "amount")}})
        return ToolResult("not_found")

    def get_refund_facts(self, arguments: dict[str, Any], key: str | None) -> ToolResult:
        order = self.orders.get(arguments["order_id"])
        if order is None or order["account_id"] != self.verified_account_id:
            return ToolResult("error", error="order is unavailable")
        return ToolResult("success", {
            "refund_facts_loaded": True,
            "refund_facts": {"loaded": True, "playback_minutes": order["playback_minutes"], "prior_refunds": order["prior_refunds"]},
        })

    def evaluate_refund_policy(self, arguments: dict[str, Any], key: str | None) -> ToolResult:
        order = self.orders.get(arguments["order_id"])
        facts = arguments.get("refund_facts") or {}
        if order is None or not facts:
            return ToolResult("uncertain", {"refund_eligibility": "uncertain"})
        eligible = facts.get("playback_minutes", 0) < 30 and facts.get("prior_refunds", 0) == 0
        result = "eligible" if eligible else "ineligible"
        reason = "未达到30分钟使用时长且没有历史退款" if eligible else "使用记录或历史退款不符合规则"
        return ToolResult(result, {
            "refund_eligibility": result,
            "refund_reason": reason,
            "refund_reason_facts": facts,
        })

    def submit_refund(self, arguments: dict[str, Any], key: str | None) -> ToolResult:
        order = self.orders.get(arguments["order_id"])
        if order is None or order["account_id"] != self.verified_account_id:
            return ToolResult("error", error="order is unavailable")
        if order["channel"] != "first_party":
            return ToolResult("error", error="third-party orders cannot use first-party refunds")
        if order["refund_submitted"]:
            return ToolResult("already_submitted", {"status": "already_submitted"})
        order["refund_submitted"] = True
        return ToolResult("submitted", {"status": "submitted", "request_id": f"refund_{order['id']}"})

    def find_subscription(self, arguments: dict[str, Any], key: str | None) -> ToolResult:
        if self.verified_account_id is None:
            return ToolResult("error", error="account is not verified")
        hint = (arguments.get("hint") or "").lower()
        channel = arguments.get("channel")
        for subscription in self.subscriptions.values():
            if subscription["account_id"] != self.verified_account_id:
                continue
            if channel and channel != subscription["channel"]:
                continue
            if hint and hint not in subscription["hint"].lower() and hint not in subscription["channel"]:
                continue
            return ToolResult("found", {"subscription": dict(subscription)})
        return ToolResult("not_found")

    def cancel_subscription(self, arguments: dict[str, Any], key: str | None) -> ToolResult:
        subscription = self.subscriptions.get(arguments["subscription_id"])
        if subscription is None or subscription["account_id"] != self.verified_account_id:
            return ToolResult("error", error="subscription is unavailable")
        if subscription["channel"] != "first_party":
            return ToolResult("error", error="third-party subscriptions cannot be cancelled here")
        if not subscription["auto_renew"]:
            return ToolResult("already_disabled", {"auto_renew": False})
        subscription["auto_renew"] = False
        return ToolResult("cancelled", {"auto_renew": False})

    def create_handoff(self, arguments: dict[str, Any], key: str | None) -> ToolResult:
        handoff = {"case_id": arguments["case_id"], "status": "created"}
        self.handoffs.append(handoff)
        return ToolResult("created", handoff)


def build_demo_registry(backend: DemoBackend | None = None) -> ToolRegistry:
    backend = backend or DemoBackend()
    registry = ToolRegistry()
    optional_string = (str, type(None))
    registry.register("bind_current_account", backend.bind_current_account)
    registry.register("send_otp", backend.send_otp, required={"phone": str})
    registry.register("verify_otp", backend.verify_otp, required={"phone": str, "code": str})
    registry.register(
        "find_order", backend.find_order,
        required={"charge_date": str, "amount": (int, float)},
        optional={"phone": optional_string},
    )
    registry.register("get_refund_facts", backend.get_refund_facts, required={"order_id": str})
    registry.register(
        "evaluate_refund_policy", backend.evaluate_refund_policy,
        required={"order_id": str}, optional={"refund_facts": dict},
    )
    registry.register(
        "submit_refund", backend.submit_refund,
        required={"order_id": str}, idempotent=True,
    )
    registry.register(
        "find_subscription", backend.find_subscription,
        required={"hint": optional_string, "channel": optional_string},
    )
    registry.register(
        "cancel_subscription", backend.cancel_subscription,
        required={"subscription_id": str}, idempotent=True,
    )
    registry.register("create_handoff", backend.create_handoff, required={"case_id": str})
    return registry
