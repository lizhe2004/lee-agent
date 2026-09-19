# Harness Interpretation 协议

状态：Draft
协议版本：0.1.0

本文定义 Harness 如何向语言模型提供受约束的理解上下文，语言模型必须返回什么结构，以及 Harness 如何把不可信的 Interpretation Result 校验并编译为可信的 Workflow Engine Command。

本文依赖：

- [Workflow Definition 规范](./workflow-definition-spec.md)
- [Workflow Engine 交互协议](./workflow-engine-protocol.md)

---

## 1. 范围与核心边界

### 1.1 协议目标

本协议定义：

- Harness 提供给模型的 Interpretation Request；
- 模型返回的 Interpretation Result；
- 允许的语义 Act；
- Slot 值提取、规范化、证据和置信度；
- 多 Act 的冲突与优先级；
- Harness 的结构、权限和上下文校验；
- Interpretation Result 到 Engine Command 的编译；
- 模型失败、歧义和不支持请求的处理。

### 1.2 非目标

本文不定义：

- Workflow Definition；
- Engine 的状态迁移和失效算法；
- Prompt 的具体文字；
- 模型供应商和模型版本选择；
- Skill 的组织方式；
- 多意图案件的调度实现；
- 用户界面和渠道协议。

### 1.3 两阶段模型

~~~text
用户自然语言
    ↓
语言模型
    ↓
Interpretation Result
    ↓  不可信候选
Harness 校验与编译
    ↓
Engine Command
    ↓
Workflow Engine
~~~

语言模型不直接生成 Engine Command。Interpretation Result 表示“模型认为用户表达了什么”；Engine Command 表示“系统允许对哪个 Workflow Instance 执行什么操作”。

### 1.4 信任边界

语言模型输出的所有字段都不可信。confidence 等于 1.0 也不能绕过：

- JSON Schema；
- Act 白名单；
- Slot 白名单；
- Slot 类型；
- 当前 ask 的 fields；
- 当前 options；
- Slot source 和 mutable；
- revision 和 wait_token；
- 身份认证和授权。

## 2. 角色与职责

### 2.1 语言模型

语言模型只负责：

- 判断用户本轮表达的语义动作；
- 从原文中提取候选 Slot 值；
- 给出候选规范值；
- 标注原文证据；
- 显式报告歧义和无法判断。

语言模型不得决定：

~~~text
workflow_instance_id
expected_revision
expected_slot_revisions
wait_token
actor
command_id
Artifact 值
active node
next node
tool 名称
tool.result
invalidates
recompute_frontier
Policy 结果
业务成功状态
~~~

### 2.2 Harness

Harness 负责：

- 从 Engine Emission 和可信会话中构造模型上下文；
- 调用模型并解析结构化输出；
- 校验输出是否被当前上下文允许；
- 规范化日期、金额、号码和枚举；
- 处理多 Act 冲突；
- 从认证系统取得 actor；
- 从 Engine State 取得 instance、revision、Slot revision 和 wait_token；
- 生成 command_id；
- 编译 Engine Command；
- 在不产生 Engine Command 时发起澄清或返回不支持说明。

### 2.3 Workflow Engine

Engine 不接收 Interpretation Result，也不信任模型 confidence。Engine 只接收符合 Engine 协议的 Command，并再次验证权限、状态和 revision。

## 3. Interpretation Request

### 3.1 公共结构

Harness 向模型提供最小必要上下文：

~~~json
{
  "interpretation_version": "0.1",
  "utterance": {
    "id": "msg_123",
    "text": "改成明天吧",
    "language": "zh-CN",
    "received_at": "2026-09-19T10:00:00+08:00"
  },
  "locale": "zh-CN",
  "timezone": "Asia/Shanghai",
  "reference_time": "2026-09-19T10:00:00+08:00",
  "current_interaction": {
    "node_id": "confirm_booking",
    "wait_token_alias": "current",
    "kind": "confirmation",
    "prompt": "请确认航班和价格",
    "fields": ["slots.booking_confirmed"],
    "options": []
  },
  "allowed_acts": [
    "answer",
    "slot_change",
    "cancel_interaction",
    "new_intent",
    "clarification_required",
    "unsupported"
  ],
  "allowed_slots": {
    "slots.departure_date": {
      "type": "date",
      "mutable": true,
      "current_value": "2026-09-19"
    },
    "slots.booking_confirmed": {
      "type": "boolean",
      "mutable": true,
      "current_value": null
    }
  },
  "allowed_intents": []
}
~~~

### 3.2 字段含义

| 字段 | 必填 | 含义 |
|---|---:|---|
| interpretation_version | 是 | Harness Interpretation 协议版本 |
| utterance | 是 | 本轮用户原始消息 |
| locale | 是 | 语言、数字和展示习惯 |
| timezone | 日期时间场景 | 相对时间解释所用时区 |
| reference_time | 日期时间场景 | “今天”“明天”等表达的基准时间 |
| current_interaction | 有活动 ask 时 | 当前 interaction.requested 的裁剪视图 |
| allowed_acts | 是 | 模型本轮允许输出的 Act |
| allowed_slots | 是 | 模型允许提取或修改的 Slot 白名单与类型摘要 |
| allowed_intents | 支持新意图时 | 可识别的新意图白名单 |

### 3.3 utterance

| 字段 | 含义 |
|---|---|
| id | 本轮消息稳定 ID |
| text | 原始文本，不得被预处理改写后替代 |
| language | 已检测语言；未知时允许 null |
| received_at | 渠道接收时间 |

### 3.4 current_interaction

current_interaction 来自 Engine 的 interaction.requested。Harness 可以删除敏感展示信息，但不得改变：

- node_id；
- kind；
- fields；
- options.value；
- 当前允许的交互行为。

wait_token_alias 只表示“当前等待”，不包含真实 wait_token。真实 wait_token 不应提供给模型。

### 3.5 allowed_slots

allowed_slots 只能包括：

- 当前 ask.request.fields；
- 当前实例中 source 允许用户写入且 mutable 允许修改的 Slots；
- 本轮新意图路由明确允许抽取的预路由字段。

Harness 不应向模型提供完整 Artifact、完整 Workflow 图、工具名或控制流迁移。

敏感 Slot 的 current_value 应省略、掩码或只提供“是否存在”，除非理解当前消息确实需要该值。

## 4. Interpretation Result 公共结构

### 4.1 结构

~~~json
{
  "interpretation_version": "0.1",
  "utterance_id": "msg_123",
  "language": "zh-CN",
  "acts": [],
  "ambiguities": []
}
~~~

### 4.2 公共字段

| 字段 | 必填 | 含义 |
|---|---:|---|
| interpretation_version | 是 | 输出协议版本 |
| utterance_id | 是 | 必须等于 Request 中的 utterance.id |
| language | 是 | 模型实际理解使用的语言 |
| acts | 是 | 按语义出现顺序排列的 Act，允许为空 |
| ambiguities | 是 | 无法确定的字段、指代或动作 |

未知顶层字段必须被 Harness 拒绝。

模型名称、调用 ID、延迟和 token 用量由 Harness 从模型客户端取得并附加到观测日志，不属于模型可以自行填写的 Interpretation Result。

### 4.3 Evidence

所有从用户文本提取的 Slot 值和关键 Act SHOULD 包含 evidence：

~~~json
{
  "text": "明天",
  "start": 2,
  "end": 4
}
~~~

start 和 end 使用 Unicode code point 索引，区间为左闭右开。evidence.text 必须与原文切片一致。

### 4.4 Confidence

confidence 为 0 到 1 的模型自评值，只用于路由到确认或澄清策略。它不得：

- 授予写入权限；
- 跳过类型校验；
- 覆盖 options；
- 写入 Artifact；
- 代替 Engine guard。

## 5. answer Act

answer 表示用户正在回答当前 ask。

~~~json
{
  "type": "answer",
  "answers": [
    {
      "ref": "slots.booking_confirmed",
      "raw_value": "确认",
      "candidate_value": true,
      "confidence": 0.99,
      "evidence": {
        "text": "确认",
        "start": 0,
        "end": 2
      }
    }
  ]
}
~~~

| 字段 | 必填 | 含义 |
|---|---:|---|
| type | 是 | 固定为 answer |
| answers | 是 | 至少一个回答项 |
| answers[].ref | 是 | current_interaction.fields 中的 Slot |
| answers[].raw_value | 是 | 原文表达 |
| answers[].candidate_value | 是 | 与 Slot 类型匹配的候选值 |
| answers[].confidence | 是 | 模型置信度 |
| answers[].evidence | SHOULD | 原文证据 |

answer 只能回答当前 ask，不能顺便写入其他 Slot。选项型回答的 candidate_value 必须等于 current_interaction.options 中某个 value。

## 6. slot_change Act

slot_change 表示用户更正或修改已经提供的 Slot。

~~~json
{
  "type": "slot_change",
  "changes": [
    {
      "ref": "slots.departure_date",
      "raw_value": "明天",
      "candidate_value": "2026-09-20",
      "confidence": 0.99,
      "evidence": {
        "text": "明天",
        "start": 2,
        "end": 4
      }
    }
  ]
}
~~~

| 字段 | 必填 | 含义 |
|---|---:|---|
| type | 是 | 固定为 slot_change |
| changes | 是 | 至少一个修改项 |
| changes[].ref | 是 | allowed_slots 中 mutable 的 Slot |
| changes[].raw_value | 是 | 用户原始表达 |
| changes[].candidate_value | 是 | 候选规范值 |
| changes[].confidence | 是 | 模型置信度 |
| changes[].evidence | SHOULD | 原文证据 |

模型不能输出 invalidates、restart_at、target_node 或 Policy。Harness 将全部合法变化合并为一个原子 slot.change Command。

## 7. cancel_interaction Act

~~~json
{
  "type": "cancel_interaction",
  "confidence": 0.98,
  "evidence": {
    "text": "算了",
    "start": 0,
    "end": 2
  }
}
~~~

cancel_interaction 只表示取消当前 ask。用户明确要求终止整个业务时，应识别为相应 new_intent 或交给受控取消策略，不能由模型直接生成 workflow.cancel。

## 8. new_intent Act

new_intent 表示用户提出当前 Workflow 之外的新业务目标。

~~~json
{
  "type": "new_intent",
  "intent": "cancel_subscription",
  "confidence": 0.96,
  "evidence": {
    "text": "顺便把自动续费也关了",
    "start": 0,
    "end": 10
  },
  "entities": []
}
~~~

| 字段 | 必填 | 含义 |
|---|---:|---|
| intent | 是 | allowed_intents 中的稳定 ID |
| confidence | 是 | 模型置信度 |
| evidence | SHOULD | 支持该意图的原文 |
| entities | 否 | 路由层明确允许的预路由字段 |

new_intent 不直接编译成当前 Workflow Engine Command，而是交给 Workflow 之外的意图路由或案件协调层。该层不属于本文范围。

## 9. clarification_required 与 unsupported

### 9.1 clarification_required

~~~json
{
  "type": "clarification_required",
  "reason": "ambiguous_date",
  "about": ["slots.departure_date"],
  "question": "你说的明天是 9 月 20 日吗？",
  "candidates": [
    "2026-09-20",
    "2026-09-21"
  ]
}
~~~

| 字段 | 必填 | 含义 |
|---|---:|---|
| reason | 是 | 稳定歧义原因 |
| about | 是 | 无法确定的 Slot 或 Act |
| question | 是 | 建议澄清问题 |
| candidates | 否 | 有限候选值 |

Harness 可以重新表述 question，但不得在用户澄清前选择 candidate。clarification_required 不产生 Engine Command，原 wait_token 保持有效。

### 9.2 unsupported

~~~json
{
  "type": "unsupported",
  "reason": "intent_not_in_catalog",
  "summary": "用户希望修改乘机人证件类型。"
}
~~~

unsupported 表示当前 allowed_acts、allowed_slots 和 allowed_intents 无法表达用户目标。它不产生 Engine Command。

## 10. ambiguities

除了 clarification_required Act，模型还可以在 ambiguities 中报告局部不确定性：

~~~json
{
  "kind": "reference",
  "text": "那个航班",
  "candidates": ["CA123", "MU5101"],
  "about": "slots.selected_flight_id"
}
~~~

存在影响 Command 正确性的 ambiguity 时，Harness 必须阻止编译并要求澄清。仅影响展示而不影响结构化值的 ambiguity MAY 记录后继续。

## 11. Slot 值规范化

### 11.1 权威关系

candidate_value 是模型候选，不是最终值。Harness 必须通过 Slot 类型对应的规范化器和校验器产生 Engine Command 值。

~~~text
raw_value
  ↓
模型 candidate_value
  ↓
Harness deterministic normalizer
  ↓
Slot schema validator
  ↓
Engine Command value
~~~

### 11.2 日期和时间

相对日期必须使用 Request 中的 reference_time 和 timezone。Harness 必须验证：

- 日期真实存在；
- 时区明确；
- 相对表达与 reference_time 一致；
- 业务允许的日期范围；
- 夏令时导致的不存在或重复时间。

模型不得使用自己的当前时间。

### 11.3 Enum

candidate_value 必须是 Slot values 中的规范值。模型可以把“商务舱”映射为 business，但不能创建新枚举。

### 11.4 Boolean 和确认

“确认”“是”“就这个”只能在当前 confirmation 上下文中映射为 true。脱离当前 ask 的肯定表达不能自动解释为业务确认。

### 11.5 Selection

selection 的值必须来自 current_interaction.options.value。模型提取航班号后，Harness 仍需检查该航班是否属于当前有效列表。

### 11.6 Money、Phone 和 Email

- Money 必须包含货币或从唯一上下文确定货币；
- Phone 应规范化为地区明确的标准格式；
- Email 应做语法规范化但不得自行修复不确定字符；
- 敏感值不得写入模型日志和非必要 evidence。

## 12. 多 Act 处理

### 12.1 一般规则

一个用户消息 MAY 产生多个 Acts。Harness 必须先验证全部 Acts，再决定编译哪些 Engine Command。

### 12.2 多个 slot_change

同一消息中的所有合法 slot_change 必须合并成一个原子 slot.change Command：

~~~json
{
  "changes": {
    "slots.departure_date": "2026-09-20",
    "slots.cabin": "business"
  }
}
~~~

同一个 Slot 出现两个不同候选值时，必须澄清。

### 12.3 slot_change 与 answer

当同一消息同时包含 slot_change 和 answer：

1. 先判断 Slot 修改是否可能使当前 ask 依赖的数据失效；
2. 如果会失效，只编译 slot.change；
3. 丢弃或延迟依赖旧状态的 answer；
4. 等待 Engine 重新计算并发出新的 interaction.requested；
5. 用户必须对新数据重新确认。

Harness 不得把“修改旧条件”和“确认旧结果”一起提交。

### 12.4 cancel 与其他 Act

cancel_interaction 和 answer 同时出现且语义明确冲突时必须澄清。用户明确表达“先取消当前操作，再提出新诉求”时，可以保留 cancel_interaction 和 new_intent，但两个动作必须由上层按顺序处理。

### 12.5 clarification_required

clarification_required 优先阻止所有依赖该歧义的 Engine Command。不受该歧义影响的独立 new_intent MAY 交给路由层。

## 13. Harness 校验流水线

Harness 必须按以下顺序处理模型输出：

### 13.1 结构校验

- 输出是一个完整 JSON 对象；
- 符合 Interpretation Result Schema；
- 不含未知字段；
- interpretation_version 受支持；
- utterance_id 与 Request 一致。

### 13.2 Act 白名单

- 每个 Act 都在 allowed_acts；
- Act 专属字段完整；
- 不包含 Engine 专属字段；
- 不包含工具调用或 Artifact 写入。

### 13.3 引用白名单

- answer.ref 属于 current_interaction.fields；
- slot_change.ref 属于 allowed_slots；
- new_intent.intent 属于 allowed_intents；
- 不允许任意 JSON path、通配符或动态引用。

### 13.4 Grounding

- evidence 与原文切片一致；
- raw_value 可在原文或明确上下文中定位；
- 模型没有使用未提供的事实；
- 代词指代唯一，否则产生 ambiguity。

### 13.5 类型与规范化

- candidate_value 可转换为 Slot 类型；
- enum 和 selection 在允许集合中；
- 日期使用正确 reference_time 和 timezone；
- 敏感字段符合最小暴露规则。

### 13.6 上下文校验

- 当前 wait_token 仍有效；
- 当前 ask 没有被更新的 Engine Emission 替代；
- Slot 仍然 mutable；
- actor 仍然有权写入；
- 当前 instance revision 与 Harness 快照一致。

### 13.7 冲突处理

应用第 12 章规则。存在无法确定解决的冲突时，不生成 Engine Command。

### 13.8 编译

只有全部校验通过后，Harness 才能从可信上下文补充 command_id、workflow_instance_id、expected_revision、Slot revisions、wait_token、actor 和 occurred_at。

## 14. Interpretation 到 Engine Command 的编译

### 14.1 answer

~~~text
Interpretation answer
  + 当前 workflow_instance_id
  + 当前 expected_revision
  + 当前 wait_token
  + 认证 actor
  → interaction.answer
~~~

映射：

| Interpretation | Engine Command |
|---|---|
| answers[].ref | payload.answers 的 key |
| 规范化后的 candidate_value | payload.answers 的 value |
| 无 | command_id，由 Harness 生成 |
| 无 | wait_token，从 Engine Emission 取得 |
| 无 | expected_revision，从 Engine State 取得 |

### 14.2 slot_change

~~~text
Interpretation slot_change
  + 当前 workflow_instance_id
  + 当前 instance revision
  + 每个 Slot revision
  + 认证 actor
  → slot.change
~~~

Harness 必须把多个合法变化编译为一个 Command，不能让模型指定 reason 之外的执行策略。reason 由 Harness 根据 Act 类型映射为稳定代码，例如 user_correction。

### 14.3 cancel_interaction

cancel_interaction 编译为 interaction.cancel，并从当前 Engine Emission 取得 wait_token 和 node_id。

### 14.4 new_intent

new_intent 不编译为当前 Workflow Command，而是输出给意图路由层：

~~~json
{
  "type": "route.intent",
  "utterance_id": "msg_123",
  "intent": "cancel_subscription",
  "actor_id": "user_123",
  "evidence": {
    "text": "把自动续费也关了",
    "start": 0,
    "end": 8
  }
}
~~~

route.intent 不是 Workflow Engine 协议的一部分。

### 14.5 clarification_required 和 unsupported

二者不产生 Engine Command。Harness 可以向用户发送澄清或能力边界说明，但不得改变 Workflow revision 或消费当前 wait_token。

## 15. Harness 输出

Harness 对单轮用户消息的最终处理结果应明确区分三种情况。

### 15.1 commands

~~~json
{
  "status": "commands_ready",
  "utterance_id": "msg_123",
  "commands": [
    {
      "protocol_version": "0.1",
      "command_id": "cmd_456",
      "type": "slot.change",
      "workflow_instance_id": "wfi_789",
      "expected_revision": 18,
      "actor": {
        "type": "user",
        "id": "user_123",
        "tenant_id": "tenant_a"
      },
      "occurred_at": "2026-09-19T10:00:00+08:00",
      "payload": {
        "changes": {
          "slots.departure_date": "2026-09-20"
        },
        "expected_slot_revisions": {
          "slots.departure_date": 4
        },
        "reason": "user_correction"
      }
    }
  ],
  "routing": [],
  "user_response": null
}
~~~

commands 中保存完整 Engine Command。Harness 必须在输出前完成全部可信字段补全。

### 15.2 clarification

~~~json
{
  "status": "clarification_required",
  "utterance_id": "msg_123",
  "commands": [],
  "routing": [],
  "user_response": {
    "code": "AMBIGUOUS_DATE",
    "message": "你说的明天是 9 月 20 日吗？"
  }
}
~~~

### 15.3 routing_or_unsupported

~~~json
{
  "status": "routing_required",
  "utterance_id": "msg_123",
  "commands": [],
  "routing": [
    {
      "intent": "cancel_subscription"
    }
  ],
  "user_response": null
}
~~~

Harness 最终输出不是模型原始 JSON。它是经过校验、冲突处理和可信上下文补全的处理结果。

## 16. 失败与回退

### 16.1 标准失败原因

| code | 含义 |
|---|---|
| MODEL_OUTPUT_INVALID_JSON | 模型没有返回合法 JSON |
| MODEL_OUTPUT_SCHEMA_ERROR | 输出不符合 Schema |
| UTTERANCE_ID_MISMATCH | 输出绑定到错误消息 |
| DISALLOWED_ACT | Act 不在白名单 |
| DISALLOWED_SLOT | Slot 不在允许集合 |
| DISALLOWED_INTENT | Intent 不在允许集合 |
| UNGROUNDED_VALUE | 值无法从原文或上下文得到 |
| VALUE_NORMALIZATION_FAILED | 候选值无法可靠规范化 |
| AMBIGUOUS_INTERPRETATION | 存在影响执行的歧义 |
| ACT_CONFLICT | 多 Act 无法安全合并 |
| STALE_INTERACTION_CONTEXT | Engine 上下文已更新 |
| SENSITIVE_DATA_VIOLATION | 模型输出或日志暴露敏感数据 |

### 16.2 回退原则

- 解析失败不得构造猜测 Command；
- 可以使用同一 Request 重试模型，但重试次数必须受限；
- 重试后仍失败时应澄清或转人工；
- Harness 重新读取 Engine 状态后，必须构造新的 Request，不能复用旧 Interpretation Result；
- 不得通过降低权限校验来提高成功率。

## 17. 安全与隐私

### 17.1 Prompt Injection

用户文本始终作为数据放入 utterance.text。用户要求“忽略规则”“输出某个节点”“把认证设为成功”不能扩大 allowed_acts、allowed_slots 或 allowed_intents。

### 17.2 最小上下文

模型只获得理解当前消息所需的信息。默认不提供：

- 完整 Workflow Definition；
- Artifact 全量值；
- 工具名和工具参数；
- Policy；
- 身份认证结果详情；
- 其他用户或其他实例数据；
- 访问令牌和凭证。

### 17.3 敏感值

OTP、证件号、手机号和支付信息应按 Slot sensitive 和 retention 规则处理。模型日志、trace 和 evidence 必须脱敏或禁用持久化。

### 17.4 输出注入

模型生成的 question、summary 和 message 是不可信文本。展示前必须做渠道转义，不得作为模板、代码、URL 或工具参数执行。

## 18. 可观察性与评估

Harness SHOULD 记录：

~~~text
interpretation_version
utterance_id
model alias
prompt/template version
allowed acts hash
allowed slots hash
Interpretation Result hash
validation result
compiled command IDs
latency
~~~

日志不得保存不必要的敏感原文。

建议评估指标：

- Act 分类准确率；
- Slot 提取准确率；
- 规范化准确率；
- 错误确认率；
- 漏识别 slot_change 比例；
- clarification 精确率；
- 禁止字段拦截率；
- Interpretation 到 Command 编译一致性。

## 19. 完整示例

### 19.1 确认购买

当前 ask：

~~~json
{
  "kind": "confirmation",
  "fields": ["slots.booking_confirmed"]
}
~~~

用户：

~~~text
确认购买
~~~

Interpretation Result：

~~~json
{
  "interpretation_version": "0.1",
  "utterance_id": "msg_confirm",
  "language": "zh-CN",
  "acts": [
    {
      "type": "answer",
      "answers": [
        {
          "ref": "slots.booking_confirmed",
          "raw_value": "确认购买",
          "candidate_value": true,
          "confidence": 0.99,
          "evidence": {
            "text": "确认购买",
            "start": 0,
            "end": 4
          }
        }
      ]
    }
  ],
  "ambiguities": []
}
~~~

Harness 编译为 interaction.answer，并从可信上下文加入 wait_token、expected_revision 和 actor。

### 19.2 确认时修改日期

用户：

~~~text
改成明天吧
~~~

Interpretation Result：

~~~json
{
  "interpretation_version": "0.1",
  "utterance_id": "msg_change_date",
  "language": "zh-CN",
  "acts": [
    {
      "type": "slot_change",
      "changes": [
        {
          "ref": "slots.departure_date",
          "raw_value": "明天",
          "candidate_value": "2026-09-20",
          "confidence": 0.99,
          "evidence": {
            "text": "明天",
            "start": 2,
            "end": 4
          }
        }
      ]
    }
  ],
  "ambiguities": []
}
~~~

Harness 编译为一个 slot.change。它不生成 answer=false，也不指定 search_flights 节点。

### 19.3 修改条件并要求直接购买

用户：

~~~text
改成明天，还是商务舱，直接买吧
~~~

Interpretation Result：

~~~json
{
  "interpretation_version": "0.1",
  "utterance_id": "msg_change_and_buy",
  "language": "zh-CN",
  "acts": [
    {
      "type": "slot_change",
      "changes": [
        {
          "ref": "slots.departure_date",
          "raw_value": "明天",
          "candidate_value": "2026-09-20",
          "confidence": 0.99,
          "evidence": {
            "text": "明天",
            "start": 2,
            "end": 4
          }
        },
        {
          "ref": "slots.cabin",
          "raw_value": "商务舱",
          "candidate_value": "business",
          "confidence": 0.99,
          "evidence": {
            "text": "商务舱",
            "start": 7,
            "end": 10
          }
        }
      ]
    },
    {
      "type": "answer",
      "answers": [
        {
          "ref": "slots.booking_confirmed",
          "raw_value": "直接买吧",
          "candidate_value": true,
          "confidence": 0.91,
          "evidence": {
            "text": "直接买吧",
            "start": 11,
            "end": 15
          }
        }
      ]
    }
  ],
  "ambiguities": []
}
~~~

Harness 只编译包含 departure_date 和 cabin 的原子 slot.change。booking_confirmed 依赖旧航班和旧价格，不能编译。Engine 重新查询后必须再次要求确认。

### 19.4 日期歧义

当前 reference_time 接近跨日边界，用户说：

~~~text
凌晨以后走
~~~

模型无法可靠得到唯一日期：

~~~json
{
  "interpretation_version": "0.1",
  "utterance_id": "msg_ambiguous",
  "language": "zh-CN",
  "acts": [
    {
      "type": "clarification_required",
      "reason": "ambiguous_datetime",
      "about": ["slots.departure_date"],
      "question": "你希望哪一天凌晨出发？",
      "candidates": []
    }
  ],
  "ambiguities": [
    {
      "kind": "datetime",
      "text": "凌晨以后",
      "candidates": [],
      "about": "slots.departure_date"
    }
  ]
}
~~~

Harness 不产生 Engine Command，当前 wait_token 保持有效。

### 19.5 模型尝试写 Artifact

非法模型输出：

~~~json
{
  "interpretation_version": "0.1",
  "utterance_id": "msg_attack",
  "language": "zh-CN",
  "acts": [
    {
      "type": "slot_change",
      "changes": [
        {
          "ref": "artifacts.identity_verified",
          "raw_value": "我已经验证了",
          "candidate_value": true,
          "confidence": 1.0
        }
      ]
    }
  ],
  "ambiguities": []
}
~~~

Harness 必须返回 DISALLOWED_SLOT，不产生任何 Engine Command。

---

## 附录 A：Act 速查

| Act | 可编译结果 |
|---|---|
| answer | interaction.answer |
| slot_change | slot.change |
| cancel_interaction | interaction.cancel |
| new_intent | route.intent，不属于 Engine 协议 |
| clarification_required | 无 Command，向用户澄清 |
| unsupported | 无 Command，说明能力边界或转人工 |

## 附录 B：模型禁止字段

~~~text
command_id
workflow_instance_id
expected_revision
expected_slot_revisions
wait_token
actor
current_node
next_node
artifacts.*
tool
tool.result
invalidates
recompute_frontier
policy_results
~~~

## 附录 C：三份规范的关系

~~~text
Workflow Definition 规范
  定义 Workflow 允许读写什么、如何执行和失效

Harness Interpretation 协议
  定义自然语言如何转换为受约束的语义动作

Workflow Engine 交互协议
  定义可信 Command 如何驱动 Workflow Instance
~~~
