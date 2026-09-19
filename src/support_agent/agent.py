from __future__ import annotations

import re
from typing import Any, Protocol


class Agent(Protocol):
    def extract_fields(self, message: str, expected: list[str], skill_text: str) -> dict[str, Any]: ...
    def write_reply(self, node: dict[str, Any], facts: dict[str, Any], skill_text: str) -> str: ...


class DemoAgent:
    def extract_fields(self, message: str, expected: list[str], skill_text: str = "") -> dict[str, Any]:
        result: dict[str, Any] = {}
        date = re.search(r"20\d{2}[-年]\d{1,2}[-月]\d{1,2}日?", message)
        if date and "charge_date" in expected or date and "travel_date" in expected:
            value = date.group(0).replace("年", "-").replace("月", "-").replace("日", "")
            if "charge_date" in expected:
                result["charge_date"] = value
            if "travel_date" in expected:
                result["travel_date"] = value
        amount = re.search(r"(?:扣了|金额|人民币|¥|￥)\s*([0-9]+(?:\.[0-9]+)?)|([0-9]+(?:\.[0-9]+)?)\s*(?:元|块)", message)
        if amount and "amount" in expected:
            result["amount"] = float(amount.group(1) or amount.group(2))
        phone = re.search(r"(?<!\d)(1\d{10})(?!\d)", message)
        if phone and "purchase_account_phone" in expected:
            result["purchase_account_phone"] = phone.group(1)
        otp = re.search(r"(?:验证码|code)\s*[:：]?\s*(\d{4,8})", message, re.I)
        if otp and "otp_code" in expected:
            result["otp_code"] = otp.group(1)
        if "current" in message or "当前账号" in message:
            if "account_relation" in expected:
                result["account_relation"] = "current"
        elif "其他账号" in message or "家人" in message:
            if "account_relation" in expected:
                result["account_relation"] = "other"
        if any(word in message.lower() for word in ("是", "确认", "提交", "可以")) and "confirm_refund" in expected:
            result["confirm_refund"] = True
        if any(word in message.lower() for word in ("是", "确认", "关闭")) and "confirm_cancel" in expected:
            result["confirm_cancel"] = True
        if "apple" in message.lower() or "苹果" in message:
            for field in ("purchase_channel_hint", "purchase_channel"):
                if field in expected:
                    result[field] = "apple"
        if "google" in message.lower() or "谷歌" in message:
            if "purchase_channel_hint" in expected:
                result["purchase_channel_hint"] = "google_play"
        return result

    def write_reply(self, node: dict[str, Any], facts: dict[str, Any], skill_text: str = "") -> str:
        if node["type"] == "ask":
            return node["prompt"]
        if node["type"] == "respond":
            return _render(node.get("template", ""), {**facts, "case_id": facts.get("case_id", "")})
        return ""


def _lookup(facts: dict[str, Any], path: str) -> Any:
    value: Any = facts
    for part in path.split("."):
        if not isinstance(value, dict):
            return ""
        value = value.get(part, "")
    return value


def _render(template: str, facts: dict[str, Any]) -> str:
    return re.sub(r"\{\{\s*([a-zA-Z_][\w.]*)\s*}}", lambda m: str(_lookup(facts, m.group(1))), template)
