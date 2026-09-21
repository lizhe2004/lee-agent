# 退款 Workflow 示例

这是退款 SOP 的设计示例，说明如何把客服话术转换为 Proposal，再由 Engine 按安全规则执行。

## 1. 业务目标

```text
收集订单线索
  → 确认目标账号
  → 必要时 OTP 身份认证
  → 查询订单
  → 查询播放记录和历史退款
  → 判断资格
  → 用户确认
  → 执行退款或转 Apple/人工
```

## 2. 核心 Slot 和 Artifact

| 名称 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `charge_date` | date | user | 扣款日期 |
| `amount` | money | user | 扣款金额 |
| `account_relation` | enum | user | current 或 other |
| `purchase_account_phone` | phone | user | 非当前账号时使用 |
| `otp_code` | string | user | 敏感输入，验证后消费 |
| `target_account_verified` | boolean Artifact | tool | 只能由认证工具产生 |
| `order` | object Artifact | tool | 订单查询结果 |
| `refund_facts` | object Artifact | tool | 播放记录和历史退款结果 |
| `refund_eligibility` | enum Artifact | system | eligible、ineligible 或 manual_review |
| `refund_confirmed` | boolean | user | 用户确认是否执行退款 |

## 3. 关键安全规则

### 当前账号

用户说“当前账号”只能产生 `account_relation=current` Proposal。Engine 仍需绑定当前认证主体，不能把用户文本当作 `target_account_verified=true`。

### 非当前账号

用户说“不是当前账号”后，Engine 必须：

1. 询问手机号；
2. 发送验证码；
3. 等待验证码；
4. 调用验证工具；
5. 认证成功后才查询目标账号订单。

OTP 不属于普通可回显 Slot，验证后应消费原文和临时值。

### 修改手机号

已认证后用户修改手机号时：

```text
purchase_account_phone 变化
  → target_account_verified 失效
  → 当前退款确认失效
  → 重新发送 OTP
```

这是安全 Policy；普通数据依赖和 Policy 都由 Engine 计算，模型不能声明清理列表。

### iOS 购买

如果 `order.channel=ios`，进入 Apple 申请说明路径，不调用本方退款副作用。

### 退款资格

播放记录、历史退款和订单状态都是可信 Artifact。模型或用户不能直接写入 `refund_eligibility`。

## 4. Proposal 示例

用户说：

```text
不是当前账号，是以前的手机号，验证码我不记得了。
```

Model Candidate 可以包含：

```json
{
  "proposals": [
    {"target": "slots.account_relation", "candidates": [{"raw_value": "不是当前账号"}], "relation": "single", "commitment": "explicit"},
    {"target": "slots.purchase_account_phone", "candidates": [{"raw_value": "以前的手机号"}], "relation": "single", "commitment": "explicit"}
  ],
  "interaction_acts": [{"type": "unable_to_answer", "reason": "does_not_know", "raw_value": "验证码我不记得了"}]
}
```

Harness 不能把“不记得验证码”写入 `otp_code`。Engine 应根据当前 ask 的 `on.unable_to_answer` 走重新发送、替代验证或人工路径。

## 5. 修改订单线索

用户在确认前说“日期改成 9 月 11 日”：

1. Harness 生成 `charge_date` correction Proposal；
2. Engine 使订单查询、播放记录、历史退款和资格结果失效；
3. 重新查询并重新判断资格；
4. 旧退款确认不能复用；
5. 退款工具不能在旧确认上执行。

## 6. 允许的终态

| 终态 | 条件 |
|---|---|
| `refund_submitted` | 身份、订单、资格和用户确认全部有效，退款工具成功 |
| `apple_redirect` | 订单来源为 iOS |
| `ineligible` | 可信资格判断不满足退款条件 |
| `manual_review` | 工具或 Policy 要求人工处理 |
| `cancelled` | 用户取消当前交互或案件 |
