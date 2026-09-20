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
    "accepts": ["answer", "slot_change", "cancel_interaction", "unable_to_answer"]
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
| `allowed_slots` | array | 是 | 本轮允许模型提取的可写 Slot 投影；不在其中的字段不能作为 Slot 修改候选 |
| `intent_catalog` | array | 是 | 本轮可识别的业务意图及其说明；不在其中的意图不能被模型声称已命中 |
| `allowed_interaction_acts` | array<enum> | 是 | 本轮允许输出的 Interaction Act 集合；只能使用列出的值 |

`pending_interaction` 中的 `fields`、`options` 和 `accepts` 是当前问题的约束。`allowed_slots` 用于处理用户在同一句话中顺便提供的其他信息，例如当前问出发地时同时说出到达地和日期。

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
| `interaction_acts` | array | 是 | 对当前 ask 的回答、Slot 修改、取消或无法回答候选；没有时为空数组 |
| `business_intents` | array | 是 | 用户表达的业务目标候选；没有时为空数组 |
| `unmapped_requests` | array | 是 | 无法映射到输入 Intent Catalog 的请求；没有时为空数组 |
| `ambiguities` | array | 是 | 影响解释的歧义；没有时为空数组 |

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

每个 `changes[]` 项：

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| `ref` | slot-ref | 是 | 输入 `pending_interaction.fields` 或 `allowed_slots` 中的 Slot 引用 |
| `raw_value` | string | object | array | 是 | 从用户原文提取的原始候选值；不要求模型完成最终类型转换 |

`slot_change.reason` 只能使用：

- `user_correction`：用户明确修改之前的值；
- `user_provided_additional_info`：用户提前提供后续信息；
- `user_clarification`：用户澄清先前表达。

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
| `entities` | array | 是 | 该意图相关的字段候选；没有实体时为空数组 |
| `entities[].ref` | string | 是 | Intent Catalog 为该意图允许的字段引用 |
| `entities[].raw_value` | string | object | array | 是 | 用户原文中的实体候选 |

模型只报告业务目标，不判断它是当前 Workflow 的继续、恢复还是新建。该判断由 Router 根据可信运行状态完成。

### 3.5 无法映射和歧义

`unmapped_requests` 用于记录模型无法可靠映射到 Intent Catalog 的请求：

```json
{
  "summary": "用户询问能否转让会员给家人",
  "raw_text": "能不能转给我家人"
}
```

`ambiguities` 用于记录不能安全选择的解释：

```json
{
  "kind": "multiple_values",
  "raw_text": "下周一",
  "candidates": ["2026-09-21", "2026-09-28"],
  "question": "您指的是 9 月 21 日还是 9 月 28 日？"
}
```

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
