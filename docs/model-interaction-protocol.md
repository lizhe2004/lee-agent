# 大模型交互协议

状态：Draft
协议版本：0.1.0

本文只定义 Harness 与大模型之间的一次结构化调用：Harness 传给模型什么输入，模型必须返回什么候选结果。本文不定义 Workflow 如何执行，也不定义 Harness 如何把候选结果编译成 Engine Command。

相关协议：

- [Workflow Definition 规范](./workflow-definition-spec.md)：定义 Slot、ask 和业务规则；
- [Harness Interpretation 协议](./harness-interpretation-protocol.md)：校验本协议的模型结果，并交接给 Engine 或 Intent Router。

## 1. 设计边界

模型只做语言理解和候选提取。模型返回的是**语义候选**，不是已经确认的事实，也不是可直接执行的命令。

模型不得决定：

- 当前 Workflow 是否继续、恢复或新建；
- 任何 `workflow_instance_id`、`interaction_id`、revision 或 actor；
- 下一个节点、重算入口、失效范围或 Policy 结果；
- 工具名称、工具参数、退款资格、身份认证结果或业务成功状态；
- 用户不能直接写入的 Artifact 或可信字段。

Harness 负责把候选结果与可信上下文、字段白名单和原文证据进行校验，再生成规范的 Interpretation Result。Engine 只接收 Harness 编译后的 Command。

## 2. 一次调用的输入

### 2.1 输入信封

```json
{
  "protocol_version": "0.1.0",
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
      {"role": "assistant", "text": "请问您的出发城市是？"}
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
    {"id": "book_flight", "description": "预订机票"},
    {"id": "cancel_auto_renewal", "description": "取消自动续费"}
  ],
  "allowed_interaction_acts": [
    "answer",
    "slot_change",
    "cancel_interaction",
    "unable_to_answer"
  ]
}
```

### 2.2 输入字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `protocol_version` | exact semver | 是 | 本次模型调用使用的协议版本；模型原样回显 |
| `request_id` | string | 是 | Harness 为本次调用生成的追踪 ID；模型原样回显 |
| `utterance` | object | 是 | 当前需要理解的用户消息；模型只能把它作为当前消息来源 |
| `utterance.id` | string | 是 | 当前消息稳定 ID；用于结果关联 |
| `utterance.text` | string | 是 | 用户原文；不得修改 |
| `utterance.language` | string | 否 | 语言提示；缺省时由 Harness 选择 |
| `utterance.received_at` | datetime | 否 | 消息接收时间；不等于业务时间 |
| `reference_time` | datetime | 是 | 解析“明天”等相对时间的基准时间 |
| `timezone` | string | 是 | 相对日期和本地时间的解析时区 |
| `conversation_context` | object | 否 | Harness 裁剪后的对话上下文；模型不得把摘要当作新事实 |
| `pending_interaction` | object | null | 是 | 当前等待回答的问题；没有活动 ask 时为 `null` |
| `allowed_slots` | array<allowed-slot> | 是 | 本轮允许模型提取的可写 Slot 投影；不在其中的字段不能作为 Slot 修改候选 |
| `intent_catalog` | array<intent-definition> | 是 | 本轮可识别的业务意图及其说明；不在其中的意图不能被模型声称已命中 |
| `allowed_interaction_acts` | array<enum> | 是 | 本轮允许输出的 Interaction Act 集合；只能使用列出的值 |

`pending_interaction` 中的 `fields`、`options` 和 `accepts` 是当前问题的约束。`allowed_slots` 用于处理用户在同一句话中顺便提供的其他信息，例如当前问出发地时同时说出到达地和日期。

### 2.2.1 `utterance` 的字段

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | string | 在 Harness 可见的消息范围内稳定唯一；模型必须原样回显请求中的 `request_id`，但不需要回显 `utterance.id` |
| `text` | string | 非空；是本次需要解释的唯一当前消息来源；模型不得改写、翻译或补写原文 |
| `language` | string \| null | 否 | BCP 47 语言标签，例如 `zh-CN`；只是理解提示，不改变 Slot 类型和业务规则 |
| `received_at` | datetime \| null | 否 | 消息进入系统的时间；不能当作用户说的业务日期 |

### 2.2.2 `conversation_context` 的字段

没有历史或 Harness 判断历史与当前解释无关时，可以传 `null`。上下文中的每个事实都只是理解材料，不自动成为 Slot 或可信状态。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `recent_turns` | array<turn> | 是 | 按时间从旧到新排列的有限消息；通常包含最近几轮用户和客服对话 |
| `summary` | string \| null | 是 | Harness 生成的短摘要；用于理解省略和指代，不能作为本轮用户新提供的事实 |
| `relevant_turns` | array<turn> | 否 | 与当前问题相关但不在最近窗口内的历史消息；按时间排列，不能伪造为当前消息 |

`turn` 字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `id` | string | 是 | 历史消息 ID |
| `role` | enum | 是 | `user`、`assistant` 或 `system_summary`；模型必须区分说话方 |
| `text` | string | 是 | 原始消息或系统摘要内容 |
| `created_at` | datetime \| null | 否 | 消息发生时间；缺省时不能据此推断相对日期 |

上下文不应包含 Engine 内部控制字段、未授权 Artifact 原文、完整支付凭据、OTP 或其他不必要的敏感数据。

### 2.2.3 `pending_interaction` 的字段

`pending_interaction` 描述“现在系统正在等用户回答什么”。它不是节点定义，也不包含真实 `interaction_id`。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `kind` | enum | 是 | 用户回答形式：`form`、`selection`、`confirmation`、`text` |
| `prompt` | string | 是 | 已展示给用户的问题或问题摘要；模型用它判断当前回答对象 |
| `fields` | array<interaction-field> | 是 | 当前问题允许回答的 Slot；无字段时为空数组，但 `answer` 不能因此凭空写入字段 |
| `options` | array<option> | 是 | 选择题的候选项；非选择题必须为空数组 |
| `accepts` | array<enum> | 是 | 当前 ask 可以结束等待的 Engine 交互事件：`answer`、`cancel`、`unable_to_answer` |

`interaction-field`：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `ref` | slot-ref | 是 | 当前回答对应的完整 Slot 地址 |
| `type` | string | 是 | Slot Registry 中的类型或已注册 Schema ID；模型据此理解值形状，但不负责最终转换 |
| `required` | boolean | 是 | 本次回答是否必须提供该字段；不表示业务资格已满足 |
| `label` | string | 否 | 给模型的字段说明；不得包含未授权事实 |

`option`：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `value` | string | 是 | Harness 可识别的稳定选项值；模型返回候选时应引用其语义，不自行创造新值 |
| `label` | string | 是 | 面向用户或模型的显示文本 |
| `description` | string | 否 | 选项补充说明 |

约束：`form` 可以包含多个 `fields`；`selection` 必须恰好一个字段且 `options` 非空；`confirmation` 必须恰好一个 boolean Slot 且 `options` 为空；`text` 通常恰好一个字段且 `options` 为空。未知 `kind` 或不符合组合约束的输入必须由 Harness 拒绝。

### 2.2.3.1 `kind` 枚举的实际语义

| 值 | 用户应如何回答 | `fields` 约束 | `options` 约束 | 常见例子 |
|---|---|---|---|---|
| `form` | 一次填写一个或多个字段 | 一个或多个 | 必须为空 | 同时提供扣款日期、金额和账号关系 |
| `selection` | 从系统给出的候选中选择 | 恰好一个 | 至少一个；每项 `value` 必须稳定且唯一 | 选择航班或支付方式 |
| `confirmation` | 表示同意或拒绝 | 恰好一个 boolean Slot | 必须为空 | “确认取消自动续费吗？” |
| `text` | 自由填写一个字段 | 通常恰好一个 | 必须为空 | 输入手机号、订单号或验证码 |

`kind` 只描述回答格式，不表示业务动作是否成功。比如 `confirmation` 的 `true` 只表示用户同意当前 ask；是否真的取消续费仍由 Engine 调用工具并检查结果。

### 2.2.3.2 `accepts` 枚举的实际语义

`accepts` 与 `kind` 不同：`kind` 描述“答案长什么样”，`accepts` 描述“哪些交互事件可以结束当前等待”。它来自 Workflow Definition 的 `request.accepts`，模型不能自行增加值。

| 值 | 含义 | Harness 对模型暴露的对应 Act | 是否写入当前 fields |
|---|---|---|---:|
| `answer` | 用户提供了当前 ask 所需答案 | `answer` | 是，经过类型和选项校验后写入 |
| `cancel` | 用户放弃回答当前 ask | `cancel_interaction` | 否 |
| `unable_to_answer` | 用户明确表示无法提供当前答案 | `unable_to_answer` | 否 |

`slot_change` 不属于 `accepts`。它是实例级 Slot 修改，可以在当前 ask 之外发生；只有当 `allowed_slots` 中存在可修改字段并通过 Policy 校验时，Harness 才把模型的 `slot_change` 编译为 `slot.change`。如果 Slot 修改使当前 ask 失效，Engine 会重新计算等待状态。

因此，模型输入同时包含两组不同白名单：

1. `pending_interaction.accepts`：当前 ask 可以接受并结束等待的事件；
2. `allowed_interaction_acts`：本轮模型可以输出的 Act，其中的 `cancel_interaction` 是 `accepts=cancel` 的模型侧名称，`slot_change` 则由可修改 Slot 决定。

### 2.2.4 `allowed_slots` 的字段

`allowed_slots` 是本轮给模型的可写字段投影，不是完整 Runtime State。缺少某个 Slot 表示本轮不得把它作为候选输出。

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `ref` | slot-ref | 是 | 完整 Slot 地址；必须对应当前 Workflow 或 Router 允许的字段 |
| `type` | string | 是 | Slot Registry 的类型或 Schema ID |
| `mutable` | boolean | 是 | 当前阶段是否允许用户修改；`false` 时模型不能生成该字段的 `slot_change` |
| `current_value` | any \| null | 否 | Harness 选择性提供的当前值；敏感字段可省略或脱敏，模型不得把它当作用户本轮新输入 |
| `description` | string | 否 | 字段业务含义和常见表达 |
| `allowed_values` | array<allowed-value> | 否 | enum Slot 的允许值或其显示投影；非 enum 字段省略 |

模型只能从用户当前消息和允许的上下文中提取新值。`current_value` 只用于理解“改成另一个”“保持不变”等表达，不足以单独生成 `slot_change`。

`allowed-value`：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `value` | string | number | boolean | 是 | Engine 认可的稳定值 |
| `label` | string | 是 | 给模型理解和展示使用的文字 |

### 2.2.5 `intent_catalog` 的字段

`intent_catalog` 是本次调用允许模型识别的业务目标目录。它不是 Workflow 列表，也不向模型暴露“新建/恢复”策略。

`intent_catalog` 的每个元素就是一个 `intent-definition` 对象：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `id` | identifier | 是 | 稳定业务意图 ID，例如 `refund_request` |
| `description` | string | 是 | 意图的自然语言边界说明 |
| `entity_refs` | array<string> | 否 | 该意图允许抽取的实体字段；省略表示本轮不要求实体 |
| `examples` | array<string> | 否 | 给模型的短示例；不构成额外能力声明 |

模型只能返回目录中的 `id`。如果用户表达了目录之外的目标，应放入 `unmapped_requests`，不能根据相似名称猜测一个意图。

### 2.2.6 `allowed_interaction_acts` 的枚举

这是 Harness 根据当前 `pending_interaction` 和 `allowed_slots` 计算出的模型输出白名单。它不是 Workflow Definition 字段，模型也不能修改它。

| 值 | 模型可以识别的用户行为 | 生成的 Harness 规范候选 |
|---|---|---|
| `answer` | 用户回答当前 ask | `interaction_acts[].type="answer"` |
| `slot_change` | 用户更正旧 Slot，或提前提供后续 Slot | `interaction_acts[].type="slot_change"` |
| `cancel_interaction` | 用户放弃当前 ask | `interaction_acts[].type="cancel_interaction"`；仅当 `accepts` 含 `cancel` |
| `unable_to_answer` | 用户无法回答当前 ask | `interaction_acts[].type="unable_to_answer"`；仅当 `accepts` 含 `unable_to_answer` |

如果当前没有活动 ask，`answer`、`cancel_interaction` 和 `unable_to_answer` 不应加入白名单；仍可根据活动案件和权限加入 `slot_change` 或业务意图识别。白名单为空时，模型仍必须返回完整输出信封，只能返回业务意图、未映射请求或歧义。

### 2.3 上下文裁剪规则

Harness 可以传最近消息、相关历史摘要和当前问题，但应：

- 明确区分用户原话、助手话术和系统摘要；
- 删除模型不需要的敏感字段；
- 限制长度并保持消息顺序；
- 不把 Engine 内部节点 ID、revision、工具结果权限或安全判断暴露给模型；
- 为日期解析提供 `reference_time` 和 `timezone`，禁止模型使用自己的当前时间。

## 3. 一次调用的输出

### 3.1 输出信封

模型必须返回一个 JSON 对象，不得返回 Markdown、解释文字或多个候选答案：

```json
{
  "protocol_version": "0.1.0",
  "request_id": "model_req_001",
  "interaction_acts": [
    {
      "type": "answer",
      "changes": [
        {"ref": "slots.origin", "raw_value": "北京"}
      ]
    },
    {
      "type": "slot_change",
      "changes": [
        {"ref": "slots.destination", "raw_value": "上海"},
        {"ref": "slots.departure_date", "raw_value": "明天"}
      ],
      "reason": "user_provided_additional_info"
    }
  ],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
```

### 3.2 输出顶层字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `protocol_version` | exact semver | 是 | 必须等于输入版本 |
| `request_id` | string | 是 | 必须等于输入 `request_id` |
| `interaction_acts` | array<interaction-act> | 是 | 对当前 ask 的回答、Slot 修改、取消或无法回答候选；没有时为空数组 |
| `business_intents` | array<business-intent> | 是 | 用户表达的业务目标候选；没有时为空数组 |
| `unmapped_requests` | array<unmapped-request> | 是 | 无法映射到输入 Intent Catalog 的请求；没有时为空数组 |
| `ambiguities` | array<ambiguity> | 是 | 影响解释的歧义；没有时为空数组 |

模型不得输出控制字段，例如 `workflow_id`、`interaction_id`、`expected_instance_revision`、`command_id`、`target_node`、`invalidates` 或 `policy_result`。

### 3.3 Interaction Act

`interaction_acts[].type` 是封闭枚举：

| 值 | 使用场景 | 必须包含 |
|---|---|---|
| `answer` | 回答当前 `pending_interaction` | `changes` |
| `slot_change` | 同一句话中主动修改或提前提供其他允许 Slot | `changes`、`reason` |
| `cancel_interaction` | 不再回答当前问题，例如“算了” | 可选 `reason` |
| `unable_to_answer` | 无法提供当前问题所需信息，例如“不记得了” | `reason`，可选 `raw_value` |

`answer` 的 `changes` 只能引用当前 `pending_interaction.fields`。如果用户同时提供了未来 Slot，必须另建 `slot_change`，不能把未来 Slot 塞入 `answer`。

各 Act 的完整字段：

| Act | 字段 | 类型 | 必填 | 含义 |
|---|---|---|---:|---|
| `answer` | `type` | const string | 是 | 固定为 `answer` |
| `answer` | `changes` | array<change> | 是 | 当前问题的回答；至少一项，不能包含当前 fields 之外的 Slot |
| `slot_change` | `type` | const string | 是 | 固定为 `slot_change` |
| `slot_change` | `changes` | array<change> | 是 | 用户主动提供或修改的其他 Slot；至少一项 |
| `slot_change` | `reason` | enum | 是 | 说明是更正、提前提供还是澄清 |
| `cancel_interaction` | `type` | const string | 是 | 固定为 `cancel_interaction` |
| `cancel_interaction` | `reason` | enum \| null | 否 | `user_gave_up`、`user_declined` 或 `other` |
| `cancel_interaction` | `raw_value` | string | 否 | 用户表示取消当前回答的原文片段 |
| `unable_to_answer` | `type` | const string | 是 | 固定为 `unable_to_answer` |
| `unable_to_answer` | `reason` | enum | 是 | `does_not_know`、`cannot_provide`、`not_understood` 或 `other` |
| `unable_to_answer` | `raw_value` | string | 否 | 用户表达无法回答的原文片段 |

同一 `interaction_acts` 数组中：

- 同一个 `ref` 不得在两个 Act 中给出冲突值；
- `answer` 最多一个；
- `cancel_interaction` 和 `unable_to_answer` 不能同时出现；
- 没有活动 `pending_interaction` 时，不能生成 `answer`、`cancel_interaction` 或 `unable_to_answer`；
- `slot_change` 可以在没有活动 ask 时出现，但仍必须引用 `allowed_slots` 且 `mutable=true` 的 Slot。

每个 `changes[]` 项：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `ref` | slot-ref | 是 | 输入 `pending_interaction.fields` 或 `allowed_slots` 中的 Slot 引用 |
| `raw_value` | string \| object \| array<any> | 是 | 从用户原文提取的原始候选值；不要求模型完成最终类型转换 |

因此，`pending_interaction.fields` 的元素类型就是这里定义的 `interaction-field`，而模型输出中 `answer.changes` 和 `slot_change.changes` 的元素类型是 `change`。二者不是同一个对象：前者描述“允许回答哪些字段”，后者描述“用户这次提供了什么值”。

`change` 只有两个字段：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `ref` | slot-ref | 是 | 本次候选值对应的 Slot；必须能在相应白名单中找到 |
| `raw_value` | string \| object \| array<any> | 是 | 当前消息中提取的原始值 |

`slot_change.reason` 只能使用：

- `user_correction`：用户明确修改之前的值；
- `user_provided_additional_info`：用户提前提供后续信息；
- `user_clarification`：用户澄清先前表达。

模型不需要返回最终类型值。例如日期可以先返回 `"明天"`，金额可以先返回 `"19.9 元"`；Harness 再根据 `type`、`reference_time`、`timezone` 和 Registry 规则进行规范化。模型不能把规范化失败的值改写成另一个日期或金额。

### 3.4 Business Intent

```json
{
  "intent": "cancel_auto_renewal",
  "entities": [
    {"ref": "subscription_reference", "raw_value": "当前订阅"}
  ]
}
```

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `intent` | string | 是 | 必须来自输入的 `intent_catalog[].id` |
| `entities` | array<entity> | 是 | 该意图相关的字段候选；没有实体时为空数组 |
| `entities[].ref` | string | 是 | Intent Catalog 为该意图允许的字段引用 |
| `entities[].raw_value` | string \| object \| array<any> | 是 | 用户原文中的实体候选 |

模型只报告业务目标，不判断它是当前 Workflow 的继续、恢复还是新建。该判断由 Router 根据可信运行状态完成。

同一个 Intent 下的实体 `ref` 必须出现在该 Intent 的 `entity_refs` 中；实体候选不能直接写入 Workflow Slot，也不能代表身份、资格或授权结果。

`entity` 的元素结构为：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `ref` | string | 是 | 当前 Intent 的实体字段引用 |
| `raw_value` | string \| object \| array<any> | 是 | 当前消息中的实体原文候选 |

### 3.5 无法映射和歧义

`unmapped_requests` 用于记录模型无法可靠映射到 Intent Catalog 的请求：

```json
{
  "summary": "用户询问能否转让会员给家人",
  "raw_text": "能不能转给我家人"
}
```

字段约束：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `summary` | string | 是 | 对用户请求的简短描述，不得声称系统不支持 |
| `raw_text` | string | 是 | 用户原文中的连续片段 |

`unmapped_requests` 只表示“本轮目录中没有可靠映射”。Harness 或 Router 可以继续做能力发现；模型不能把它改成 `unsupported`、`new_workflow` 或任意 Workflow ID。

`ambiguities` 用于记录不能安全选择的解释：

```json
{
  "kind": "multiple_values",
  "raw_text": "下周一",
  "candidates": ["2026-09-21", "2026-09-28"],
  "question": "您指的是 9 月 21 日还是 9 月 28 日？"
}
```

字段约束：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `kind` | enum | 是 | `multiple_values`、`unclear_reference`、`unclear_intent`、`conflict` 或 `other` |
| `raw_text` | string | 是 | 产生歧义的原文片段 |
| `candidates` | array<string \| object> | 是 | 两个或更多可行候选；没有候选时应改用 `unable_to_answer` |
| `question` | string | 是 | Harness 可据此生成澄清问题，但仍需校验其没有引入新事实 |

歧义只阻断依赖它的 Act。完全独立且已经通过其他校验的业务意图可以继续交给 Router。

模型不能用歧义对象自行选择一个值。Harness 会根据受影响的 Slot 和 Act 决定是澄清、部分提交还是交给 Router。

## 4. 典型输出

### 4.1 是、否、不记得了、算了

| 用户原话 | 模型输出的 Act | 说明 |
|---|---|---|
| 是 | `answer`，`raw_value=true` | 只回答当前确认问题 |
| 否 | `answer`，`raw_value=false` | 进入当前 ask 的否定分支 |
| 不记得了 | `unable_to_answer` | 不写入 Slot，由 Workflow 选择替代路径 |
| 算了 | `cancel_interaction` | 取消当前问题，不等于取消整个业务 |

### 4.2 当前问题和后续字段一起回答

当前问 `origin`，用户说“北京到上海，明天出发”时，模型应分别输出：

```json
{
  "interaction_acts": [
    {"type": "answer", "changes": [{"ref": "slots.origin", "raw_value": "北京"}]},
    {"type": "slot_change", "reason": "user_provided_additional_info", "changes": [
      {"ref": "slots.destination", "raw_value": "上海"},
      {"ref": "slots.departure_date", "raw_value": "明天"}
    ]}
  ],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
```

### 4.3 修改已确认的信息

用户说“改成明天”时：

```json
{
  "interaction_acts": [
    {
      "type": "slot_change",
      "reason": "user_correction",
      "changes": [{"ref": "slots.departure_date", "raw_value": "明天"}]
    }
  ],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
```

模型不输出“跳回查询节点”或“清空旧航班”；这些由 Engine 根据 Definition 的依赖图计算。

## 5. 校验失败和重试

Harness 应拒绝或重新请求模型输出的情况：

- 不是合法 JSON；
- 缺少必填顶层字段或出现未知字段；
- `request_id` 或协议版本不匹配；
- 输出了不在 `allowed_interaction_acts` 的 Act；
- `ref` 不在当前允许字段中；
- `intent` 不在输入的 Intent Catalog；
- 把控制字段、Artifact、工具调用或 Policy 结果写入输出；
- 同一字段给出互相冲突的值且没有 `ambiguities`；
- 试图用模型自报的置信度绕过校验。

模型输出不要求生成 Harness 的 `utterance_id`、`actor`、`revision`、Evidence 字符区间或规范化值。若产品需要置信度或证据，Harness 可以在后续规范结果中记录，但这些字段不属于本协议的最小模型输出。
