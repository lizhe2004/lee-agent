# 取消自动续费 Workflow 示例

这是取消自动续费的设计示例，重点说明身份、渠道和不可逆副作用。

## 1. 业务目标

```text
确认订阅
  → 确认账号和购买渠道
  → 必要时身份认证
  → 查询订阅状态
  → 根据渠道确定处理方式
  → 用户确认取消
  → 提交取消副作用
```

## 2. Slot 和 Artifact

| 名称 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `account_relation` | enum | user | current 或 other |
| `purchase_account_phone` | phone | user | 非当前账号时使用 |
| `otp_code` | string | user | 验证后消费 |
| `purchase_channel_hint` | enum | user | first_party、apple 或 google_play |
| `subscription_hint` | string | user | 订阅线索 |
| `target_account_verified` | boolean Artifact | tool | 可信认证结果 |
| `subscription` | object Artifact | tool | 当前订阅查询结果 |
| `cancel_confirmed` | boolean | user | 用户是否确认取消 |
| `cancellation_result` | object Artifact | tool | 取消工具结果 |

## 3. 账号和渠道规则

- 用户说“当前账号”只产生普通 Slot Proposal，不等同于认证成功；
- 非当前账号必须走手机号、OTP 和目标账号绑定流程；
- 修改手机号会使认证 Artifact 和当前确认失效；
- first-party 订阅可以调用本方取消工具；
- Apple 或 Google Play 订阅进入对应平台说明路径，不调用错误渠道的取消工具。

## 4. 确认和副作用

确认 ask：

```text
kind=confirmation
fields=[slots.cancel_confirmed]
accepts=[answer, cancel]
```

用户回答“是”只产生当前确认 Proposal。Engine 只有在以下条件全部满足时才能调用取消工具：

- 目标账号认证结果仍 valid；
- 订阅 Artifact 仍 valid；
- 渠道 Policy 允许本方取消；
- `cancel_confirmed=true`；
- 当前 revision 和 interaction ID 有效。

取消工具必须携带幂等键。重复提交同一个 Command 只能返回原 Decision，不能产生第二次外部取消。

## 5. 特殊回答

| 用户表达 | Model Candidate | Engine 处理 |
|---|---|---|
| “是” | 当前确认 Proposal，single、explicit、true | 进入取消工具前置检查 |
| “否” | 当前确认 Proposal，single、explicit、false | 进入保留订阅或结束路径 |
| “算了” | `cancel_interaction` | 取消当前 ask，不取消订阅 |
| “不记得了” | `unable_to_answer` | 按 Workflow 的替代路径处理 |

用户说“另外帮我退款”时，Harness 交付 `refund_request` Business Intent。Router 决定是否新建或排队，不由模型决定。

## 6. 终态

| 终态 | 条件 |
|---|---|
| `cancelled` | 本方取消工具成功 |
| `platform_redirect` | 订阅属于 Apple 或 Google Play |
| `kept_active` | 用户拒绝或取消当前确认 |
| `manual_review` | 认证、查询或取消工具要求人工处理 |
