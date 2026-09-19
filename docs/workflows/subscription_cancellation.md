# Workflow `subscription_cancellation v1`

Start node: `collect_subscription_clues`

## Nodes

### `collect_subscription_clues` (ask)
- Prompt: 请说明订阅属于当前账号还是其他账号、购买渠道，以及订阅或扣款的大致信息。
- Collects: `account_relation, purchase_channel_hint, subscription_hint, charge_date`
- Next: `account_scope`

### `account_scope` (branch)
- If `account_relation == 'current'` → `bind_current_account`
- Default → `ask_purchase_phone`

### `bind_current_account` (action)
- Tool: `bind_current_account`
- Requires: `session.authenticated`
- Guard failure: `ask_purchase_phone`
- Transitions:
  - `bound` → `find_subscription`
  - `error` → `escalate`

### `ask_purchase_phone` (ask)
- Prompt: 请提供订阅账号绑定的手机号，我会发送验证码验证账号归属。
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
  - `verified` → `find_subscription`
  - `failed` → `ask_otp`
  - `expired` → `ask_otp`
  - `error` → `escalate`

### `find_subscription` (action)
- Tool: `find_subscription`
- Requires: `target_account_verified`
- Guard failure: `verify_otp`
- Transitions:
  - `found` → `route_by_channel`
  - `not_found` → `ask_subscription_hint`
  - `error` → `escalate`

### `ask_subscription_hint` (ask)
- Prompt: 暂时没有找到匹配的订阅。请核对购买渠道或订阅信息。
- Collects: `subscription_hint, purchase_channel_hint`
- Next: `find_subscription`

### `route_by_channel` (branch)
- If `subscription.channel == 'first_party'` → `confirm_cancel`
- If `subscription.channel == 'apple'` → `guide_apple`
- If `subscription.channel == 'google_play'` → `guide_google_play`
- Default → `guide_other_store`

### `confirm_cancel` (ask)
- Prompt: 我找到一个由本系统管理的订阅。关闭自动续费后，当前有效期仍可使用。确认关闭吗？
- Collects: `confirm_cancel`
- Next: `cancellation_confirmation_gate`

### `cancellation_confirmation_gate` (branch)
- If `confirm_cancel == true` → `cancel_subscription`
- Default → `cancel_declined`

### `cancel_subscription` (action)
- Tool: `cancel_subscription`
- Requires: `target_account_verified, subscription.id, confirm_cancel`
- Guard failure: `escalate`
- Transitions:
  - `cancelled` → `report_cancelled`
  - `already_disabled` → `report_already_disabled`
  - `error` → `escalate`

### `guide_apple` (respond)
- Template: 该订阅由 Apple 管理。请在 Apple 账号的订阅设置中关闭续费；本系统无法代为取消。
- Next: `done`

### `guide_google_play` (respond)
- Template: 该订阅由 Google Play 管理。请在 Google Play 的订阅设置中关闭续费；本系统无法代为取消。
- Next: `done`

### `guide_other_store` (respond)
- Template: 该订阅需要通过购买渠道 {{ subscription.channel }} 管理。本系统无法代为取消。
- Next: `done`

### `cancel_declined` (respond)
- Template: 好的，我没有关闭自动续费。
- Next: `done`

### `report_cancelled` (respond)
- Template: 自动续费已关闭。当前有效期状态：{{ subscription.status }}。这次操作没有提交退款。
- Next: `done`

### `report_already_disabled` (respond)
- Template: 系统显示该订阅的自动续费已经关闭。此操作没有提交退款。
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
