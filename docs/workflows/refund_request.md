# Workflow `refund_request v1`

Start node: `collect_order_clues`

## Nodes

### `collect_order_clues` (ask)
- Prompt: 请提供扣款日期、金额、购买渠道（如果知道），以及订单属于当前账号还是其他账号。
- Collects: `charge_date, amount, purchase_channel_hint, account_relation`
- Next: `account_scope`

### `account_scope` (branch)
- If `account_relation == 'current'` → `bind_current_account`
- Default → `ask_purchase_phone`

### `bind_current_account` (action)
- Tool: `bind_current_account`
- Requires: `session.authenticated`
- Guard failure: `ask_purchase_phone`
- Transitions:
  - `bound` → `find_order`
  - `error` → `escalate`

### `ask_purchase_phone` (ask)
- Prompt: 请提供购买账号绑定的手机号，我会发送验证码验证账号归属。
- Collects: `purchase_account_phone`
- Next: `send_otp`

### `send_otp` (action)
- Tool: `send_otp`
- Requires: `purchase_account_phone`
- Guard failure: `ask_purchase_phone`
- Transitions:
  - `sent` → `ask_otp`
  - `rate_limited` → `escalate`
  - `error` → `escalate`

### `ask_otp` (ask)
- Prompt: 验证码已发送，请在安全输入区域输入验证码。
- Collects: `otp_code`
- Next: `verify_otp`

### `verify_otp` (action)
- Tool: `verify_otp`
- Requires: `purchase_account_phone, otp_code`
- Guard failure: `ask_otp`
- Transitions:
  - `verified` → `find_order`
  - `failed` → `ask_otp`
  - `expired` → `ask_otp`
  - `error` → `escalate`

### `find_order` (action)
- Tool: `find_order`
- Requires: `target_account_verified`
- Guard failure: `verify_otp`
- Transitions:
  - `found` → `route_by_channel`
  - `not_found` → `ask_order_clue`
  - `error` → `escalate`

### `ask_order_clue` (ask)
- Prompt: 暂时没有找到匹配订单。请再核对扣款日期、金额或购买渠道。
- Collects: `charge_date, amount, purchase_channel_hint`
- Next: `find_order`

### `route_by_channel` (branch)
- If `order.channel == 'apple'` → `guide_apple`
- If `order.channel == 'first_party'` → `load_refund_facts`
- Default → `guide_other_store`

### `load_refund_facts` (action)
- Tool: `get_refund_facts`
- Requires: `target_account_verified, order.id`
- Guard failure: `find_order`
- Transitions:
  - `success` → `assess_eligibility`
  - `error` → `escalate`

### `assess_eligibility` (action)
- Tool: `evaluate_refund_policy`
- Requires: `refund_facts_loaded`
- Guard failure: `load_refund_facts`
- Transitions:
  - `eligible` → `confirm_refund`
  - `ineligible` → `explain_ineligible`
  - `uncertain` → `escalate`
  - `error` → `escalate`

### `confirm_refund` (ask)
- Prompt: 这笔订单符合退款申请条件。请确认是否提交退款申请。
- Collects: `confirm_refund`
- Next: `refund_confirmation_gate`

### `refund_confirmation_gate` (branch)
- If `confirm_refund == true` → `submit_refund`
- Default → `refund_declined`

### `submit_refund` (action)
- Tool: `submit_refund`
- Requires: `target_account_verified, order.id, refund_eligibility == 'eligible', confirm_refund`
- Guard failure: `escalate`
- Transitions:
  - `submitted` → `report_submitted`
  - `already_submitted` → `report_already_submitted`
  - `error` → `escalate`

### `explain_ineligible` (respond)
- Template: 根据当前退款规则，这笔订单暂不符合退款条件：{{ refund_reason }}。
- Next: `done`

### `guide_apple` (respond)
- Template: 这笔订单通过 Apple 购买，需要通过 Apple 的退款流程申请。本系统没有提交退款。
- Next: `done`

### `guide_other_store` (respond)
- Template: 这笔订单需要通过购买渠道 {{ order.channel }} 申请退款。本系统没有提交退款。
- Next: `done`

### `refund_declined` (respond)
- Template: 好的，我没有提交退款申请。
- Next: `done`

### `report_submitted` (respond)
- Template: 退款申请已提交，当前状态为 {{ refund_submission.status }}。这表示申请已受理，不代表款项已到账。
- Next: `done`

### `report_already_submitted` (respond)
- Template: 系统显示这笔订单已有退款申请，不会重复提交。
- Next: `done`

### `escalate` (action)
- Tool: `create_handoff`
- Requires: `none`
- Guard failure: `handoff_failed`
- Transitions:
  - `created` → `wait_for_human`
  - `error` → `handoff_failed`

### `wait_for_human` (wait)
- Event: `human_case_updated`

### `handoff_failed` (respond)
- Template: 暂时无法连接人工客服，请稍后重试。

### `done` (end)
