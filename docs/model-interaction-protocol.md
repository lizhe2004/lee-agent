# 大模型交互协议

状态：Draft 0.2

本文定义 Harness 与大模型的一次调用。模型只返回自然语言理解候选；它不返回 Workflow Command、节点跳转、可信业务结果或执行权限。

总体架构见[总体设计](./architecture-overview.md)。Harness 如何校验候选并交给 Engine 或 Router，见[Harness Interpretation 协议](./harness-interpretation-protocol.md)。

## 1. 模型职责

模型可以识别：

- 当前消息是否回答了当前问题；
- 用户提到的 Slot 候选值；
- 用户对候选值的关系，例如任选其一、必须选一个或全部接受；
- 用户是否明确选择、修改、拒绝或无法回答；
- 用户表达的业务目标；
- 无法映射的请求和无法安全消解的歧义。

模型不得决定：

- Workflow、Workflow Instance、Case 的 ID 和调度关系；
- 当前节点、下一节点、重算入口和失效范围；
- actor、revision、interaction ID 和 command ID；
- 身份认证、退款资格、权限、Policy 和业务成功状态；
- 工具名称、工具参数、Artifact 值或副作用。

## 2. Model Request

### 2.1 输入信封

```json
{
  "protocol_version": "0.2.0",
  "request_id": "model_req_001",
  "utterance": {
    "id": "msg_101",
    "text": "北京到上海，明天出发",
    "language": "zh-CN",
    "received_at": "2026-09-20T10:00:00+08:00"
  },
  "reference_time": "2026-09-20T10:00:00+08:00",
  "timezone": "Asia/Shanghai",
  "conversation_context": {
    "recent_turns": [
      {"id": "msg_100", "role": "assistant", "text": "请问您的出发城市是？"}
    ],
    "summary": "用户正在填写机票行程"
  },
  "pending_interaction": {
    "kind": "text",
    "prompt": "请问您的出发城市是？",
    "fields": [
      {"ref": "slots.origin", "type": "string", "required": true}
    ],
    "options": [],
    "accepts": ["answer", "cancel", "unable_to_answer"]
  },
  "allowed_slots": [
    {"ref": "slots.origin", "type": "string", "mutable": true},
    {"ref": "slots.destination", "type": "string", "mutable": true},
    {"ref": "slots.departure_date", "type": "date", "mutable": true}
  ],
  "intent_catalog": [
    {"id": "book_flight", "description": "预订机票", "entity_refs": []},
    {"id": "cancel_auto_renewal", "description": "取消自动续费", "entity_refs": []}
  ],
  "allowed_interaction_acts": [
    "answer",
    "slot_change",
    "cancel_interaction",
    "unable_to_answer"
  ]
}
```

### 2.2 输入顶层字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `protocol_version` | exact semver | 是 | 本次调用的协议版本；模型必须原样回显 |
| `request_id` | string | 是 | Harness 为本次调用生成的唯一请求 ID；模型必须原样回显 |
| `utterance` | utterance | 是 | 当前需要理解的用户消息 |
| `reference_time` | datetime | 是 | 解析“明天”等相对时间的基准时间 |
| `timezone` | string | 是 | 解析相对日期和本地时间的时区 |
| `conversation_context` | conversation-context \| null | 是 | Harness 裁剪后的历史上下文；不等于可信事实 |
| `pending_interaction` | pending-interaction \| null | 是 | 当前等待用户处理的问题；无活动 ask 时为 `null` |
| `allowed_slots` | allowed-slot[] | 是 | 本轮模型可以提取的 Slot 投影 |
| `intent_catalog` | intent-definition[] | 是 | 本轮模型可以识别的业务目标目录 |
| `allowed_interaction_acts` | interaction-act-type[] | 是 | 本轮模型允许返回的交互 Act 集合 |

### 2.3 `utterance`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `id` | string | 是 | 消息稳定 ID；模型不需要回显 |
| `text` | string | 是 | 用户原文；非空，模型不得改写 |
| `language` | string \| null | 否 | BCP 47 语言标签，仅作理解提示 |
| `received_at` | datetime \| null | 否 | 消息接收时间，不是业务日期 |

### 2.4 `conversation-context`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `recent_turns` | turn[] | 是 | 从旧到新排列的有限历史消息 |
| `relevant_turns` | turn[] | 否 | 最近窗口之外但与当前消息相关的历史消息 |
| `summary` | string \| null | 是 | Harness 生成的摘要；不能当作本轮新输入 |

`turn` 的字段为 `id: string`、`role: user | assistant | system_summary`、`text: string` 和可选 `created_at: datetime`。Harness 不应传递不必要的 OTP、完整支付凭据或未授权 Artifact。

### 2.5 `pending-interaction`

它是当前问题的可回答视图，不是节点定义，也不包含真实 `interaction_id`。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `kind` | interaction-kind | 是 | 用户回答的形式 |
| `prompt` | string | 是 | 已展示给用户的问题或问题摘要 |
| `fields` | interaction-field[] | 是 | 当前问题允许回答的字段 |
| `options` | option[] | 是 | 选择题候选；非选择题必须为空数组 |
| `accepts` | accepted-event-type[] | 是 | 当前 ask 可以结束等待的 Engine 事件 |

`interaction-field` 的字段为：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `ref` | slot-ref | 是 | 当前回答对应的 Slot |
| `type` | type-ref | 是 | Slot Registry 类型或注册 Schema ID |
| `required` | boolean | 是 | 当前问题是否必须提供该字段 |
| `label` | string | 否 | 给模型理解用的字段说明 |

`option` 的字段为 `value: string`、`label: string` 和可选 `description: string`。`value` 是稳定业务值，不是显示文本。

#### `kind` 枚举

| 值 | 用户回答形式 | `fields` | `options` | 例子 |
|---|---|---|---|---|
| `form` | 一次提供一个或多个字段 | 一项或多项 | 空数组 | 日期、金额和账号关系一起填写 |
| `selection` | 从当前候选中选择 | 恰好一项 | 至少一项 | 选择航班 |
| `confirmation` | 同意或拒绝 | 恰好一个 boolean Slot | 空数组 | 确认退款 |
| `text` | 自由输入一个字段 | 通常恰好一项 | 空数组 | 输入手机号或订单号 |

`kind` 只描述输入形式，不代表业务成功。

#### `accepts` 枚举

`accepts` 来自 Workflow Definition 的 ask 合同，表示哪些 Engine 事件可以结束当前等待。它不是模型 Act 列表。

| 值 | 含义 | 模型侧对应 Act |
|---|---|---|
| `answer` | 用户提供当前问题的答案 | `answer` |
| `cancel` | 用户放弃当前问题 | `cancel_interaction` |
| `unable_to_answer` | 用户无法提供当前答案 | `unable_to_answer` |

`slot_change` 不属于 `accepts`。它是案件级输入修改；是否允许产生它取决于 `allowed_slots` 和 Workflow Policy。

### 2.6 `allowed_slots`

`allowed_slots` 是本轮可写字段的投影，不是完整 Runtime State。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `ref` | slot-ref | 是 | 完整 Slot 地址 |
| `type` | type-ref | 是 | Slot 类型或 Schema ID |
| `mutable` | boolean | 是 | 当前阶段能否修改；为 `false` 时不能产生 `slot_change` |
| `current_value` | any \| null | 否 | 选择性提供的旧值；不能当作本轮用户输入 |
| `description` | string | 否 | 字段含义和常见表达 |
| `allowed_values` | allowed-value[] | 否 | enum 字段的稳定值和显示文本 |

### 2.7 `intent_catalog`

每个元素是 `intent-definition`：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `id` | identifier | 是 | 稳定业务意图 ID |
| `description` | string | 是 | 意图边界说明 |
| `entity_refs` | string[] | 否 | 本轮允许抽取的实体字段 |
| `examples` | string[] | 否 | 给模型的短示例 |

模型只能返回目录中的意图；目录之外的请求放入 `unmapped_requests`。

### 2.8 `allowed_interaction_acts`

元素类型 `interaction-act-type` 是封闭枚举：

| 值 | 允许模型识别的行为 | 约束 |
|---|---|---|
| `answer` | 回答当前 ask | 只能引用 `pending_interaction.fields` |
| `slot_change` | 修改旧 Slot 或提前提供后续 Slot | 只能引用 `mutable=true` 的 `allowed_slots` |
| `cancel_interaction` | 放弃当前 ask | 只有 `accepts` 包含 `cancel` 时允许 |
| `unable_to_answer` | 无法回答当前 ask | 只有 `accepts` 包含 `unable_to_answer` 时允许 |

## 3. Model Candidate

### 3.1 输出信封

```json
{
  "protocol_version": "0.2.0",
  "request_id": "model_req_001",
  "proposals": [],
  "interaction_acts": [],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
```

所有数组都必须出现，没有内容时使用空数组。未知字段必须拒绝。模型不得输出控制字段。

### 3.2 顶层输出字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `protocol_version` | exact semver | 是 | 必须等于输入版本 |
| `request_id` | string | 是 | 必须等于输入请求 ID |
| `proposals` | proposal[] | 是 | 用户提出的 Slot 候选值 |
| `interaction_acts` | interaction-act[] | 是 | 当前 ask 的回答、取消或无法回答 |
| `business_intents` | business-intent[] | 是 | 用户表达的业务目标 |
| `unmapped_requests` | unmapped-request[] | 是 | 当前目录无法可靠映射的请求 |
| `ambiguities` | ambiguity[] | 是 | 无法安全消解的歧义 |

### 3.3 `proposal`

```json
{
  "target": "slots.departure_date",
  "candidates": [
    {"raw_value": "明天"},
    {"raw_value": "后天"}
  ],
  "relation": "any_of",
  "commitment": "user_accepts_any"
}
```

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `target` | slot-ref | 是 | 用户提议要影响的 Slot |
| `candidates` | candidate-value[] | 是 | 一个或多个原始候选；不能为空 |
| `relation` | proposal-relation | 是 | 候选之间的关系 |
| `commitment` | proposal-commitment | 是 | 用户是否已经确定一个值 |
| `reason` | proposal-reason | 否 | `new_information`、`correction` 或 `clarification` |

`candidate-value` 至少包含 `raw_value: string | object | any[]`。模型不负责最终类型转换。

`proposal-relation`：

| 值 | 含义 |
|---|---|
| `single` | 只有一个候选值 |
| `any_of` | 候选中任选一个都可以 |
| `all_of` | 所有候选都需要被接受，适用于集合型字段 |
| `exactly_one` | 用户表达了多个可能值，但必须明确选出一个 |

`proposal-commitment`：

| 值 | 含义 |
|---|---|
| `explicit` | 用户明确选择或确认了候选 |
| `user_accepts_any` | 用户明确表示候选中任意一个都可以 |
| `uncertain` | 用户没有能力或记忆确定唯一候选 |
| `unknown` | 无法判断用户是否接受候选 |

Proposal 不是 committed Slot。Harness 只负责规范化和授权，是否提交 Slot 由 Workflow 的值策略决定。

### 3.4 `interaction-act`

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `type` | interaction-act-type | 是 | `answer`、`cancel_interaction` 或 `unable_to_answer` |
| `raw_value` | string | 否 | 取消或无法回答的原文片段 |
| `reason` | string | 否 | 取消或无法回答原因 |

`answer` 不承载未来 Slot；当前问题中的值通过 `proposals` 引用 `pending_interaction.fields`。Harness 可以从中编译当前 ask 的回答。

### 3.5 业务目标、未映射请求和歧义

`business-intent`：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `intent` | identifier | 是 | 必须来自 `intent_catalog` |
| `entities` | entity[] | 是 | 该意图的实体候选；没有时为空数组 |

`entity` 包含 `ref: string` 和 `raw_value: string | object | any[]`。实体不能直接写入 Slot，也不能代表认证或资格结果。

`unmapped-request` 包含 `summary: string` 和 `raw_text: string`。它表示本轮目录没有可靠映射，不表示系统不支持该能力。

`ambiguity`：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `kind` | ambiguity-kind | 是 | `multiple_values`、`unclear_reference`、`unclear_intent`、`conflict` 或 `other` |
| `raw_text` | string | 是 | 产生歧义的原文片段 |
| `candidates` | candidate-value[] | 是 | 两个或更多候选 |
| `question` | string | 是 | 建议澄清问题 |

`明天后天都行` 应优先表达为 `proposal(relation=any_of, commitment=user_accepts_any)`，而不是强行选择明天。若当前 Workflow 只接受一个日期且没有代选 Policy，Harness 应根据歧义发起澄清。

## 4. 例子

### 4.1 一次提供 A、B、C

用户回答出发地时说“北京到上海，明天出发”：

```json
{
  "protocol_version": "0.2.0",
  "request_id": "model_req_001",
  "proposals": [
    {"target": "slots.origin", "candidates": [{"raw_value": "北京"}], "relation": "single", "commitment": "explicit"},
    {"target": "slots.destination", "candidates": [{"raw_value": "上海"}], "relation": "single", "commitment": "explicit", "reason": "new_information"},
    {"target": "slots.departure_date", "candidates": [{"raw_value": "明天"}], "relation": "single", "commitment": "explicit", "reason": "new_information"}
  ],
  "interaction_acts": [{"type": "answer"}],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
```

### 4.2 多个可接受候选

用户说“明天后天都行”：

```json
{
  "proposals": [
    {
      "target": "slots.departure_date",
      "candidates": [{"raw_value": "明天"}, {"raw_value": "后天"}],
      "relation": "any_of",
      "commitment": "user_accepts_any"
    }
  ],
  "interaction_acts": [],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
```

### 4.3 候选加无法确定

用户说“小米粥或者米饭吧，我记不得了”：

```json
{
  "proposals": [
    {
      "target": "slots.breakfast",
      "candidates": [{"raw_value": "小米粥"}, {"raw_value": "米饭"}],
      "relation": "any_of",
      "commitment": "uncertain"
    }
  ],
  "interaction_acts": [{"type": "unable_to_answer", "reason": "does_not_know", "raw_value": "我记不得了"}],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
```

Harness 和 Workflow 决定：如果任一候选都可以，则交给明确 Policy 或后端选择；如果必须精确选择，则继续澄清。模型不选择第一个候选。

### 4.4 修改已确认值

用户说“日期改成明天”：

```json
{
  "proposals": [
    {"target": "slots.departure_date", "candidates": [{"raw_value": "明天"}], "relation": "single", "commitment": "explicit", "reason": "correction"}
  ],
  "interaction_acts": [],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
```

模型不输出清空哪些 Artifact 或跳转哪个节点。

## 5. Harness 校验失败

Harness 必须拒绝或重新请求以下结果：

- 非法 JSON、版本或 request ID 不匹配；
- 缺少顶层数组、出现未知字段；
- Proposal target 不在允许 Slot；
- 当前不可修改的 Slot 被提议修改；
- interaction Act 不在白名单；
- Intent 不在目录；
- 控制字段、工具调用、Artifact 或可信结果出现在模型输出；
- 同一目标出现无法解释的冲突候选。

Harness 可以补充证据、规范化值、可信 Actor、revision 和 interaction ID，但这些字段不属于模型输出。
