# Harness Interpretation 协议

状态：Draft
协议版本：0.2.0

本文定义 Harness 如何向语言模型提供受约束的理解上下文、语言模型必须返回什么结构，以及 Harness 如何把不可信的语义候选校验为 Workflow Engine Command 或 Intent Router Request。

本文依赖：

- [Workflow Definition 规范](./workflow-definition-spec.md)
- [Workflow Engine 交互协议](./workflow-engine-protocol.md)

---

## 1. 协议目标与边界

### 1.1 目标

本协议解决自然语言和确定性 Workflow 之间的边界问题：

- 用户消息可能回答当前问题、修改旧信息、提出业务目标，或者同时表达多件事；
- 理解当前消息可能需要最近对话、历史摘要和当前 Engine 交互状态；
- 语言模型负责识别语义，但不能决定 Workflow 如何执行；
- Harness 校验模型输出，并从可信状态补全执行字段；
- Intent Router 根据活动 Workflow 和能力目录判断业务意图应继续、恢复还是新建流程。

### 1.2 非目标

本文不定义：

- Workflow Definition 的节点、依赖和失效算法；
- Workflow Engine 的状态迁移；
- Intent Router 的完整调度协议；
- Prompt 的具体文字；
- 模型供应商和模型版本；
- Skill 的文件组织方式；
- 用户界面和渠道协议。

本文会定义 Intent Router 的最小交接契约，用于明确职责边界。

### 1.3 三阶段处理链路

~~~text
当前消息 + 对话上下文 + 当前交互 + 意图目录
                    ↓
                 语言模型
                    ↓
            Interpretation Result
              不可信语义候选
                    ↓
                  Harness
       结构校验、证据校验、规范化、权限裁剪
              ↙                     ↘
    Engine Command              Router Request
  当前流程内的交互和修改       与流程关系无关的业务意图
              ↓                     ↓
       Workflow Engine           Intent Router
                                  ↓
                    继续 / 恢复 / 新建 / 并行 / 澄清
~~~

### 1.4 “新意图”不属于模型语义

`refund_request`、`cancel_auto_renewal`、`book_flight` 是业务意图。

“新意图”不是业务意图自身的属性，而是业务意图与当前案件状态、活动 Workflow Instance 之间的关系。模型对“我还是要退款”和“我也要退款”都可以识别为 `refund_request`，但 Router 可能分别决定：

- 继续当前退款 Workflow；
- 恢复一个暂停的退款 Workflow；
- 新建退款 Workflow；
- 在当前其他 Workflow 之外增加一个退款 Workflow。

因此 Interpretation Result 不得包含 `new_intent`。模型不负责判断一个意图相对当前 Workflow 是不是“新”的。

### 1.5 信任边界

语言模型输出的所有字段都不可信。`confidence` 等于 `1.0` 也不能绕过：

- JSON Schema；
- Interaction Act 白名单；
- Slot 白名单和类型；
- 当前 ask 的 fields 和 options；
- Intent Catalog；
- Slot source 和 mutable；
- revision 和 wait_token；
- 身份认证、授权和业务 Policy；
- Router 对活动 Workflow 的判断。

## 2. 角色与职责

### 2.1 语言模型

语言模型只负责：

- 判断用户是否在回答当前 ask；
- 识别用户对已知 Slot 的更正或修改；
- 识别用户表达的业务目标；
- 从原文和允许的上下文中提取候选值；
- 给出证据、置信度和歧义；
- 报告无法映射到 Intent Catalog 的请求。

语言模型不得决定或生成：

~~~text
workflow_id
workflow_instance_id
expected_revision
expected_slot_revisions
wait_token
actor
command_id
Artifact 值
active node
next node
tool 名称或调用参数
tool.result
invalidates
recompute_frontier
Policy 结果
业务成功状态
continue_current_workflow
resume_existing_workflow
start_new_workflow
start_additional_workflow
unsupported capability
~~~

### 2.2 Harness

Harness 负责：

- 从可信会话、Engine Emission 和会话记忆构造 Interpretation Request；
- 控制发送给模型的历史范围和敏感信息；
- 调用模型并解析结构化输出；
- 校验 Interaction Act、Slot、Business Intent、证据和上下文；
- 以确定性代码规范化日期、金额、号码和枚举；
- 处理同一消息中的多语义冲突；
- 把当前 Workflow 内的合法动作编译成 Engine Command；
- 把业务意图编译成 Router Request；
- 从认证系统和 Engine State 补全可信字段；
- 在歧义、冲突或失败时阻止执行并请求澄清。

### 2.3 Workflow Engine

Workflow Engine：

- 不接收模型原始输出；
- 不信任模型置信度；
- 只接收符合 Engine 协议的 Command；
- 再次校验权限、状态、revision、wait_token 和 Policy；
- 根据 Workflow 数据依赖处理 Slot 修改后的级联失效和重算。

### 2.4 Intent Router

Intent Router 接收经过 Harness 校验的 Business Intent，而不是模型所谓的“新意图”。Router 结合以下可信信息作出调度决定：

- 用户或案件的活动 Workflow Instances；
- 已暂停但可恢复的 Workflow Instances；
- Business Intent 到 Workflow Definition 的能力映射；
- 并行、互斥、优先级和中断策略；
- 用户身份、租户、渠道和权限；
- Workflow 当前状态。

Router 才能决定：

~~~text
continue_current_workflow
resume_existing_workflow
start_new_workflow
start_additional_workflow
pause_and_start
clarification_required
unsupported
~~~

模型不需要看到完整 Workflow Definition，也不能替代 Router 作出这些决定。

## 3. 核心数据分类

### 3.1 Interaction Act

Interaction Act 描述用户对当前对话交互做了什么：

| type | 含义 | 可能编译结果 |
|---|---|---|
| answer | 回答当前 ask | `interaction.answer` |
| slot_change | 更正或修改允许用户修改的 Slot | `slot.change` |
| cancel_interaction | 放弃当前 ask 交互 | `interaction.cancel` |

Interaction Act 与当前 Workflow Instance 的交互上下文有关。

### 3.2 Business Intent

Business Intent 描述用户希望完成的业务目标，例如：

~~~text
refund_request
cancel_auto_renewal
book_flight
change_booking
cancel_booking
~~~

Business Intent 与某个 Workflow 的运行关系尚未确定。它可能对应当前流程、已有流程或尚未创建的流程。

### 3.3 Unmapped Request

Unmapped Request 表示模型能够概括用户的请求，但无法将其可靠映射到本次 Request 提供的 Intent Catalog。

它不等于系统不支持该能力。系统是否支持只能由 Router 或能力目录判断，因为模型看到的目录可能经过裁剪。

### 3.4 Ambiguity

Ambiguity 表示某个值、指代、动作或意图存在多个合理解释，并且模型不能可靠选择唯一结果。

影响执行正确性的歧义必须阻止相关 Command 和 Router Request。

## 4. Interpretation Request

### 4.1 公共结构

~~~json
{
  "interpretation_version": "0.2",
  "utterance": {
    "id": "msg_123",
    "text": "改成明天吧，另外把自动续费也关了",
    "language": "zh-CN",
    "received_at": "2026-09-19T10:00:00+08:00"
  },
  "locale": "zh-CN",
  "timezone": "Asia/Shanghai",
  "reference_time": "2026-09-19T10:00:00+08:00",
  "conversation_context": {
    "summary": {
      "text": "用户正在预订北京到上海的商务舱航班，已选择 CA123，等待确认。",
      "through_message_id": "msg_120"
    },
    "recent_turns": [
      {
        "message_id": "msg_121",
        "role": "assistant",
        "text": "CA123 商务舱 2100 元，是否确认购买？"
      }
    ],
    "relevant_turns": []
  },
  "current_interaction": {
    "node_id": "confirm_booking",
    "wait_token_alias": "current",
    "kind": "confirmation",
    "prompt": "请确认航班和价格",
    "fields": ["slots.booking_confirmed"],
    "options": []
  },
  "allowed_interaction_acts": [
    "answer",
    "slot_change",
    "cancel_interaction"
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
  "intent_catalog": [
    {
      "id": "cancel_auto_renewal",
      "description": "用户要求关闭订阅或会员的自动续费",
      "allowed_entities": []
    },
    {
      "id": "book_flight",
      "description": "用户希望查询并预订机票",
      "allowed_entities": ["origin", "destination", "departure_date"]
    }
  ]
}
~~~

### 4.2 顶层字段

| 字段 | 必填 | 含义 |
|---|---:|---|
| interpretation_version | 是 | Harness Interpretation 协议版本 |
| utterance | 是 | 当前用户原始消息 |
| locale | 是 | 语言、数字和展示习惯 |
| timezone | 日期时间场景 | 相对日期时间解释使用的时区 |
| reference_time | 日期时间场景 | “今天”“明天”等表达的唯一基准时间 |
| conversation_context | 否 | 经过裁剪的历史对话和摘要 |
| current_interaction | 有活动 ask 时 | 当前 `interaction.requested` 的裁剪视图 |
| allowed_interaction_acts | 是 | 本轮允许模型输出的 Interaction Act 类型 |
| allowed_slots | 是 | 模型允许回答或修改的 Slot 白名单与类型摘要 |
| intent_catalog | 是 | 模型可识别的稳定 Business Intent 目录，可为空 |

### 4.3 utterance

| 字段 | 含义 |
|---|---|
| id | 当前消息稳定 ID |
| text | 当前用户原文，不得用预处理后的改写文本替代 |
| language | 已检测语言；未知时可为 `null` |
| received_at | 渠道接收时间 |

`utterance` 是本轮理解的主要对象。历史消息用于消解省略、代词和上下文，不能覆盖当前消息中的明确表达。

## 5. conversation_context

### 5.1 为什么需要历史对话

模型仅看到当前一句话时，通常无法正确理解：

~~~text
“就第一个”
“还是原来的手机号”
“不是这个订单，是上个月那个”
“确认”
“也把另一个关了”
~~~

因此 Harness 必须支持历史上下文，但不应把无限完整聊天记录直接传给模型。历史需要按相关性、长度和敏感级别裁剪。

### 5.2 结构和字段

~~~json
{
  "conversation_context": {
    "summary": {
      "text": "用户先询问订单 A 的退款，随后明确改为处理订单 B。",
      "through_message_id": "msg_80"
    },
    "recent_turns": [
      {
        "message_id": "msg_81",
        "role": "assistant",
        "text": "请确认要处理订单 B 吗？"
      }
    ],
    "relevant_turns": [
      {
        "message_id": "msg_42",
        "role": "user",
        "text": "上个月那笔 68 元的订单"
      }
    ]
  }
}
~~~

| 字段 | 含义 |
|---|---|
| summary | 较早对话的有损摘要 |
| summary.text | 不包含执行权限的事实摘要 |
| summary.through_message_id | 摘要覆盖到的最后一条消息 ID |
| recent_turns | 按时间顺序排列的最近原始消息 |
| relevant_turns | 从更早对话中检索出的相关原始片段 |

每个 turn 包含稳定的 `message_id`、`role` 和经过必要脱敏的 `text`。

### 5.3 摘要的限制

摘要不能作为以下事项的唯一证据：

- 用户身份验证成功；
- 用户接受价格或条款；
- 不可逆操作的最终确认；
- OTP、支付授权或安全凭证；
- Engine 已完成某个节点；
- Artifact 当前仍有效。

这些事实必须来自 Engine State、认证系统或其他可信系统。

### 5.4 上下文权威顺序

发生冲突时：

1. Engine State、认证状态和工具结果是运行事实的权威来源；
2. 当前 `utterance` 中用户的明确更正优先于历史用户表达；
3. 较新的原始对话优先于较旧的原始对话；
4. 原始对话优先于自动摘要；
5. 无法确定冲突关系时输出 Ambiguity。

这一顺序不允许用户文本覆盖安全事实。例如用户说“我已经验证过了”不能将 `artifacts.identity_verified` 设置为 `true`。

### 5.5 裁剪规则

Harness 应：

- 为 recent turns、relevant turns 和 summary 分别设置长度上限；
- 只保留理解当前消息需要的字段；
- 确保历史消息早于当前 utterance；
- 对敏感字段脱敏；
- 避免在 summary 和原始 turns 中重复大量相同内容；
- 记录上下文版本或 hash，便于审计和重放。

## 6. current_interaction 与 allowed_slots

### 6.1 current_interaction

`current_interaction` 来自 Engine 的 `interaction.requested`。Harness 可以删除敏感展示信息，但不得改变：

- `node_id`；
- `kind`；
- `fields`；
- `options[].value`；
- 当前允许的交互行为。

`wait_token_alias` 只表示“当前等待”，不包含真实 `wait_token`。真实 token 不应提供给模型。

Workflow Definition 中 `request.accepts` 声明的是 Engine 交互事件。Harness 构造 `allowed_interaction_acts` 时执行固定映射：`answer` 对应模型 Act `answer`，`cancel` 对应模型 Act `cancel_interaction`。该映射由协议代码定义，不能交给模型猜测。

### 6.2 allowed_slots

`allowed_slots` 只能包括：

- 当前 ask 的 `request.fields`；
- 当前实例中 `source` 允许用户写入且 `mutable` 允许修改的 Slots；
- Intent Catalog 明确允许提取的预路由实体对应的临时字段。

每个 Slot 描述可包含：

| 字段 | 含义 |
|---|---|
| type | Slot 数据类型 |
| mutable | 用户当前是否允许修改 |
| current_value | 理解本轮消息所需的当前值 |
| values | enum 的允许值 |
| sensitive | 是否需要掩码或禁止持久化 |
| description | 业务含义，不能包含执行指令 |

敏感 Slot 的 `current_value` 应省略、掩码或只提供“是否存在”，除非理解当前消息确实需要该值。

## 7. Intent Catalog

### 7.1 目的

Intent Catalog 让模型把自然语言映射为稳定的 Business Intent ID。它不告诉模型哪个 Workflow 正在运行，也不允许模型决定流程调度。

### 7.2 条目结构

~~~json
{
  "id": "refund_request",
  "description": "用户要求退回已经支付的订单费用",
  "positive_examples": [
    "我要退款",
    "这笔钱能退吗"
  ],
  "negative_examples": [
    "关闭下个月自动续费"
  ],
  "allowed_entities": [
    "order_reference"
  ]
}
~~~

| 字段 | 必填 | 含义 |
|---|---:|---|
| id | 是 | 跨模型版本稳定的业务意图 ID |
| description | 是 | 业务目标的语义定义 |
| positive_examples | 否 | 典型正例，不能作为穷举规则 |
| negative_examples | 否 | 容易混淆但不属于该意图的例子 |
| allowed_entities | 否 | 允许随意图提取的预路由实体 |

Intent Catalog 不应包含：

~~~text
workflow_id
workflow_instance_id
当前节点
节点跳转
是否属于当前流程
新建或恢复策略
并行和互斥策略
工具调用
权限结论
~~~

Business Intent 到 Workflow Definition 的映射属于 Router 的可信能力目录。

## 8. Interpretation Result

### 8.1 公共结构

~~~json
{
  "interpretation_version": "0.2",
  "utterance_id": "msg_123",
  "language": "zh-CN",
  "interaction_acts": [],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
~~~

### 8.2 顶层字段

| 字段 | 必填 | 含义 |
|---|---:|---|
| interpretation_version | 是 | 输出协议版本 |
| utterance_id | 是 | 必须等于 Request 中的 `utterance.id` |
| language | 是 | 模型实际理解使用的语言 |
| interaction_acts | 是 | 当前交互相关的语义动作，可为空 |
| business_intents | 是 | 从 Intent Catalog 识别出的业务目标，可为空 |
| unmapped_requests | 是 | 无法映射到目录的用户请求，可为空 |
| ambiguities | 是 | 无法确定的字段、指代、动作或意图 |

未知顶层字段必须被 Harness 拒绝。模型名称、调用 ID、延迟和 token 用量由 Harness 从模型客户端取得并记录。

### 8.3 为什么拆成四个数组

同一句话可能同时包含多种语义：

> 改成明天吧，另外把自动续费也关了。

其中：

- “改成明天”是当前流程内的 `slot_change`；
- “关闭自动续费”是 `cancel_auto_renewal` Business Intent；
- 它是不是新流程，由 Router 结合活动 Workflow 判断；
- 如果“自动续费”不在 Intent Catalog，模型写入 `unmapped_requests`，不能断言系统不支持。

## 9. Evidence 与 Confidence

### 9.1 Evidence

从用户文本提取的 Slot、关键 Interaction Act 和 Business Intent 应包含 Evidence：

~~~json
{
  "message_id": "msg_123",
  "text": "明天",
  "start": 2,
  "end": 4
}
~~~

`start` 和 `end` 使用 Unicode code point 索引，区间左闭右开。`evidence.text` 必须与对应消息原文的切片一致。

默认要求 Business Intent 以当前 utterance 为证据。历史消息可以帮助消解指代，但模型不能只根据历史消息重复产生用户本轮没有表达的业务目标。

### 9.2 Confidence

`confidence` 为 0 到 1 的模型自评值，只能用于确认、澄清、观测和评估策略。它不得：

- 授予写入权限；
- 跳过类型校验；
- 覆盖 options；
- 写入 Artifact；
- 代替 Engine guard；
- 代替 Router 的流程关系判断；
- 证明系统支持某项能力。

## 10. Interaction Acts

### 10.1 answer

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
        "message_id": "msg_123",
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
| type | 是 | 固定为 `answer` |
| answers | 是 | 至少一个回答项 |
| answers[].ref | 是 | `current_interaction.fields` 中的 Slot |
| answers[].raw_value | 是 | 用户原始表达 |
| answers[].candidate_value | 是 | 与 Slot 类型匹配的候选值 |
| answers[].confidence | 是 | 模型置信度 |
| answers[].evidence | 应有 | 原文证据 |

`answer` 只能回答当前 ask，不能顺便写入其他 Slot。选项型回答必须匹配 `current_interaction.options[].value`。

### 10.2 slot_change

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
        "message_id": "msg_123",
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
| type | 是 | 固定为 `slot_change` |
| changes | 是 | 至少一个修改项 |
| changes[].ref | 是 | `allowed_slots` 中 mutable 的 Slot |
| changes[].raw_value | 是 | 用户原始表达 |
| changes[].candidate_value | 是 | 候选规范值 |
| changes[].confidence | 是 | 模型置信度 |
| changes[].evidence | 应有 | 原文证据 |

模型不能输出 `invalidates`、`restart_at`、`target_node` 或 Policy。Harness 将全部合法变化合并为一个原子 `slot.change` Command。失效和重算由 Engine 根据 Workflow Definition 的依赖图计算。

### 10.3 cancel_interaction

~~~json
{
  "type": "cancel_interaction",
  "confidence": 0.98,
  "evidence": {
    "message_id": "msg_123",
    "text": "算了",
    "start": 0,
    "end": 2
  }
}
~~~

`cancel_interaction` 只表示用户放弃当前 ask。它不等于取消订单、取消订阅或终止整个案件。

“取消机票订单”属于 `cancel_booking` 一类 Business Intent；“关闭自动续费”属于 `cancel_auto_renewal`。这些目标由 Intent Catalog 识别，再由 Router 调度。

## 11. Business Intent

### 11.1 结构

~~~json
{
  "intent": "cancel_auto_renewal",
  "confidence": 0.96,
  "evidence": {
    "message_id": "msg_123",
    "text": "把自动续费也关了",
    "start": 8,
    "end": 16
  },
  "entities": []
}
~~~

| 字段 | 必填 | 含义 |
|---|---:|---|
| intent | 是 | `intent_catalog` 中的稳定 ID |
| confidence | 是 | 模型对语义映射的置信度 |
| evidence | 应有 | 支持该意图的当前消息证据 |
| entities | 否 | Catalog 明确允许的预路由实体 |

以下字段在 Business Intent 中非法：

~~~text
is_new
new_intent
current_workflow
target_workflow
workflow_id
workflow_instance_id
route_action
start_new
resume_existing
parallel
~~~

用户在多个回合重复表达同一业务目标时，模型仍然输出同一个 Business Intent ID。Router 根据案件状态判断它是强调当前目标、恢复已有目标还是新建另一个目标。

## 12. Unmapped Request 与 Ambiguity

### 12.1 Unmapped Request

~~~json
{
  "summary": "用户希望申请信用卡",
  "evidence": {
    "message_id": "msg_123",
    "text": "帮我申请一张信用卡",
    "start": 0,
    "end": 10
  },
  "confidence": 0.98
}
~~~

Unmapped Request 只说明模型未在本次 Intent Catalog 中找到可靠映射。Harness 将其交给 Router 或能力发现组件。模型和 Harness 不得直接把它改写为 `unsupported`。

### 12.2 Ambiguity

~~~json
{
  "kind": "reference",
  "about": "slots.selected_flight_id",
  "message_id": "msg_123",
  "text": "那个航班",
  "candidates": ["CA123", "MU5101"],
  "suggested_question": "你指的是 CA123 还是 MU5101？"
}
~~~

Harness 可以重新表述 `suggested_question`，但不得在用户澄清前代替用户选择候选。

## 13. Slot 值规范化

`candidate_value` 是模型候选，不是最终值：

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

### 13.1 日期和时间

相对日期必须使用 Request 中的 `reference_time` 和 `timezone`。Harness 验证日期、时区、相对表达、业务日期范围和夏令时边界。模型不得使用自己的当前时间。

### 13.2 Enum、Boolean 和 Selection

- enum 候选必须属于 Slot 的 `values`；
- “确认”“是”“就这个”只能在当前 confirmation 上下文中映射为 `true`；
- selection 必须来自 `current_interaction.options[].value`；
- 脱离当前 ask 的肯定表达不能自动解释为业务确认。

### 13.3 Money、Phone 和 Email

- Money 必须包含货币，或能从唯一上下文确定货币；
- Phone 应规范化为地区明确的标准格式；
- Email 应做语法规范化，但不得自行修复不确定字符；
- 敏感值不得写入不必要的模型日志和 Evidence。

## 14. 多语义处理

### 14.1 多个 slot_change

同一消息中的合法 `slot_change` 合并成一个原子 Command：

~~~json
{
  "changes": {
    "slots.departure_date": "2026-09-20",
    "slots.cabin": "business"
  }
}
~~~

同一个 Slot 出现两个不同候选值时必须澄清。

### 14.2 slot_change 与 answer

当同一消息同时包含 `slot_change` 和 `answer`：

1. 判断 Slot 修改是否可能使当前 ask 依赖的数据失效；
2. 如果会失效，只编译 `slot.change`；
3. 不提交依赖旧状态的 `answer`；
4. 等待 Engine 重算并发出新的 `interaction.requested`；
5. 用户对新数据重新确认。

Harness 不得把“修改旧条件”和“确认旧结果”一起提交。

### 14.3 Interaction Act 与 Business Intent

两者语义独立时可以分别交付。例如“改成明天，另外把自动续费也关了”可以产生：

- 当前机票 Workflow 的 `slot.change`；
- 发给 Router 的 `cancel_auto_renewal`。

如果存在顺序依赖、互斥或歧义，Harness 不自行决定跨 Workflow 调度顺序，而是把约束和原始顺序交给 Router。

### 14.4 Ambiguity 的阻断范围

Ambiguity 只阻断依赖该歧义的输出。与歧义完全独立的 Interaction Act 或 Business Intent 可以继续交付，但 Harness 必须能证明它们不共享目标、实体或确认状态。

## 15. Harness 校验流水线

Harness 必须按以下顺序处理模型输出。

### 15.1 结构校验

- 输出是完整 JSON 对象；
- 符合 Interpretation Result Schema；
- 不含未知字段；
- `interpretation_version` 受支持；
- `utterance_id` 与 Request 一致。

### 15.2 白名单与引用校验

- 每个 Interaction Act 都在 `allowed_interaction_acts`；
- `answer.ref` 属于 `current_interaction.fields`；
- `slot_change.ref` 属于 `allowed_slots`；
- `business_intents[].intent` 属于 `intent_catalog[].id`；
- entities 只包含对应 Intent 的 `allowed_entities`；
- 不允许任意 JSON path、通配符、Artifact 写入、工具调用或节点跳转。

### 15.3 Grounding

- Evidence 与对应消息的原文切片一致；
- Business Intent 可以在当前 utterance 中定位；
- `raw_value` 可在原文或允许的上下文中定位；
- 模型没有使用未提供的事实；
- 代词指代唯一，否则产生 Ambiguity；
- 历史摘要没有被当作安全或执行事实。

### 15.4 类型和运行上下文校验

- 候选值可转换为 Slot 类型；
- enum 和 selection 在允许集合中；
- 日期使用正确的 reference time 和 timezone；
- 当前 wait_token 仍有效；
- 当前 ask 没有被新 Emission 替代；
- Slot 仍然 mutable；
- actor 仍然有权写入；
- instance revision 与 Harness 快照一致。

### 15.5 冲突处理和编译

存在无法可靠解决的冲突时，不生成受影响的 Engine Command 或 Router Request。验证通过后：

- Interaction Act 从可信上下文补充执行字段，编译为 Engine Command；
- Business Intent 和 Unmapped Request 补充 actor、tenant、channel 和 utterance ID，编译为 Router Request；
- Ambiguity 编译为澄清请求，不改变 revision，也不消费 wait_token。

## 16. Interpretation 到 Engine Command

### 16.1 answer

~~~text
Interpretation answer
  + 当前 workflow_instance_id
  + 当前 expected_revision
  + 当前 wait_token
  + 认证 actor
  → interaction.answer
~~~

| Interpretation | Engine Command |
|---|---|
| `answers[].ref` | `payload.answers` 的 key |
| 规范化后的 candidate value | `payload.answers` 的 value |
| 无 | `command_id`，由 Harness 生成 |
| 无 | `wait_token`，从 Engine Emission 取得 |
| 无 | `expected_revision`，从 Engine State 取得 |

### 16.2 slot_change

~~~text
Interpretation slot_change
  + 当前 workflow_instance_id
  + 当前 instance revision
  + 每个 Slot revision
  + 认证 actor
  → slot.change
~~~

多个合法修改编译为一个 Command。`reason` 由 Harness 映射为稳定代码，例如 `user_correction`。

### 16.3 cancel_interaction

`cancel_interaction` 编译为 `interaction.cancel`，并从当前 Engine Emission 取得 `wait_token` 和 `node_id`。

## 17. Harness 到 Intent Router 的交接

### 17.1 Router Request

Business Intent 不编译为当前 Workflow Command。Harness 生成：

~~~json
{
  "router_protocol_version": "0.1",
  "request_id": "route_req_456",
  "utterance_id": "msg_123",
  "actor": {
    "type": "user",
    "id": "user_123",
    "tenant_id": "tenant_a"
  },
  "channel": "cli",
  "business_intents": [
    {
      "intent": "cancel_auto_renewal",
      "confidence": 0.96,
      "evidence": {
        "message_id": "msg_123",
        "text": "把自动续费也关了",
        "start": 8,
        "end": 16
      },
      "entities": []
    }
  ],
  "unmapped_requests": [],
  "source_order": [
    {
      "kind": "business_intent",
      "index": 0
    }
  ]
}
~~~

Router Request 不声明意图是“新”的，也不包含目标 Workflow。

### 17.2 Router 的可信输入

Router 自己读取：

~~~text
active workflow instances
suspended workflow instances
intent-to-workflow capability mapping
workflow compatibility policies
case priority and interruption policies
actor authorization
tenant and channel capability restrictions
~~~

### 17.3 Router Decision 示例

以下结构只说明边界，不是完整 Router 协议：

~~~json
{
  "decision": "start_additional_workflow",
  "intent": "cancel_auto_renewal",
  "workflow_id": "subscription_management",
  "keep_active_instances": ["wfi_refund_001"]
}
~~~

如果已经存在匹配的 Workflow Instance，相同模型输出可能得到：

~~~json
{
  "decision": "resume_existing_workflow",
  "intent": "cancel_auto_renewal",
  "workflow_instance_id": "wfi_subscription_002"
}
~~~

Router Decision 不能反向写入 Interpretation Result，也不能由模型预测。

### 17.4 Unsupported 的产生位置

`unsupported` 是 Router 查询完整能力目录、租户权限和渠道限制后的系统结论：

~~~json
{
  "decision": "unsupported",
  "reason": "capability_not_available",
  "request_summary": "用户希望申请信用卡"
}
~~~

模型只输出 Unmapped Request。Harness 不得因为裁剪后的 Intent Catalog 没有某个意图，就断言系统不支持。

## 18. Harness 最终输出

### 18.1 commands_ready

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
  "router_requests": [],
  "user_response": null
}
~~~

### 18.2 routing_required

~~~json
{
  "status": "routing_required",
  "utterance_id": "msg_123",
  "commands": [],
  "router_requests": [
    {
      "request_id": "route_req_456",
      "business_intents": [
        {
          "intent": "cancel_auto_renewal"
        }
      ],
      "unmapped_requests": []
    }
  ],
  "user_response": null
}
~~~

### 18.3 commands_and_routing_ready

当同一消息包含彼此独立的当前流程动作和业务意图时：

~~~json
{
  "status": "commands_and_routing_ready",
  "utterance_id": "msg_123",
  "commands": [
    {
      "type": "slot.change",
      "workflow_instance_id": "wfi_booking_001"
    }
  ],
  "router_requests": [
    {
      "request_id": "route_req_456",
      "business_intents": [
        {
          "intent": "cancel_auto_renewal"
        }
      ],
      "unmapped_requests": []
    }
  ],
  "user_response": null
}
~~~

这里省略了完整字段，仅展示组合关系。实际输出必须符合各自 Schema。

### 18.4 clarification_required

~~~json
{
  "status": "clarification_required",
  "utterance_id": "msg_123",
  "commands": [],
  "router_requests": [],
  "user_response": {
    "code": "AMBIGUOUS_REFERENCE",
    "message": "你指的是 CA123 还是 MU5101？"
  }
}
~~~

Harness 最终输出不是模型原始 JSON，而是经过校验、冲突处理和可信上下文补全的处理结果。

## 19. 失败与回退

### 19.1 标准失败原因

| code | 含义 |
|---|---|
| MODEL_OUTPUT_INVALID_JSON | 模型没有返回合法 JSON |
| MODEL_OUTPUT_SCHEMA_ERROR | 输出不符合 Schema |
| UTTERANCE_ID_MISMATCH | 输出绑定到错误消息 |
| DISALLOWED_INTERACTION_ACT | Interaction Act 不在白名单 |
| DISALLOWED_SLOT | Slot 不在允许集合 |
| UNKNOWN_BUSINESS_INTENT | Intent 不在 Intent Catalog |
| DISALLOWED_ENTITY | 意图实体不在允许集合 |
| UNGROUNDED_VALUE | 值无法从原文或上下文得到 |
| UNGROUNDED_INTENT | 当前消息没有表达该业务目标 |
| VALUE_NORMALIZATION_FAILED | 候选值无法可靠规范化 |
| AMBIGUOUS_INTERPRETATION | 存在影响执行的歧义 |
| SEMANTIC_CONFLICT | 多语义无法安全合并 |
| STALE_INTERACTION_CONTEXT | Engine 上下文已更新 |
| SENSITIVE_DATA_VIOLATION | 输出或日志暴露敏感数据 |

### 19.2 回退原则

- 解析失败不得构造猜测 Command 或 Router Request；
- 可以用同一 Request 重试模型，但重试次数必须受限；
- 重试后仍失败时应澄清或转人工；
- 重新读取 Engine 状态后必须构造新的 Request；
- 旧 Interpretation Result 不得绑定到新的 wait_token 或 revision；
- 不得通过降低权限或证据校验提高成功率；
- Catalog 未命中必须形成 Unmapped Request，不能静默丢弃。

## 20. 安全、隐私与可观察性

### 20.1 Prompt Injection

用户文本和历史对话始终作为数据传入。用户要求“忽略规则”“输出某个节点”“把认证设为成功”不能扩大：

- `allowed_interaction_acts`；
- `allowed_slots`；
- `intent_catalog`；
- Intent 的 `allowed_entities`；
- Engine 或 Router 权限。

### 20.2 最小上下文

模型默认不获得：

- 完整 Workflow Definition；
- Artifact 全量值；
- 工具名和工具参数；
- Policy；
- 身份认证结果详情；
- 其他用户或无关实例数据；
- Business Intent 到 Workflow 的映射；
- 访问令牌和凭证。

### 20.3 敏感信息

OTP、证件号、手机号和支付信息应按 Slot `sensitive` 和 `retention` 规则处理。模型日志、trace、历史摘要和 Evidence 必须脱敏或禁用持久化。

### 20.4 观测与评估

Harness 应记录协议版本、utterance ID、模型别名、Prompt 版本、conversation context hash、白名单 hash、Intent Catalog hash、结果 hash、校验结果、Command IDs、Router Request IDs 和延迟。

应分别评估 Interaction Act、Slot 提取、Business Intent、Unmapped Request、指代消解、歧义识别和编译一致性。Router 的流程选择准确率应单独评估，不能计入模型 Business Intent 分类准确率。

## 21. 完整示例

### 21.1 历史上下文中的“确认”

最近一轮 assistant 消息是“CA123 商务舱 2100 元，是否确认购买？”，用户说“确认”：

~~~json
{
  "interpretation_version": "0.2",
  "utterance_id": "msg_202",
  "language": "zh-CN",
  "interaction_acts": [
    {
      "type": "answer",
      "answers": [
        {
          "ref": "slots.booking_confirmed",
          "raw_value": "确认",
          "candidate_value": true,
          "confidence": 0.99,
          "evidence": {
            "message_id": "msg_202",
            "text": "确认",
            "start": 0,
            "end": 2
          }
        }
      ]
    }
  ],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
~~~

历史对话确定“确认”回答的对象。真正可确认的字段、选项和 wait_token 仍来自 current interaction 和 Engine State。

### 21.2 确认阶段修改日期

用户说“改成明天吧”：

~~~json
{
  "interpretation_version": "0.2",
  "utterance_id": "msg_change_date",
  "language": "zh-CN",
  "interaction_acts": [
    {
      "type": "slot_change",
      "changes": [
        {
          "ref": "slots.departure_date",
          "raw_value": "明天",
          "candidate_value": "2026-09-20",
          "confidence": 0.99,
          "evidence": {
            "message_id": "msg_change_date",
            "text": "明天",
            "start": 2,
            "end": 4
          }
        }
      ]
    }
  ],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
~~~

Harness 编译一个 `slot.change`。模型不指定跳回 `search_flights`。Engine 根据依赖关系使旧航班、报价、选择和确认失效，并计算重算起点。

### 21.3 当前修改和另一个业务目标

当前 Workflow 正在等待确认机票。用户说“改成明天吧，另外把自动续费也关了”：

~~~json
{
  "interpretation_version": "0.2",
  "utterance_id": "msg_mixed",
  "language": "zh-CN",
  "interaction_acts": [
    {
      "type": "slot_change",
      "changes": [
        {
          "ref": "slots.departure_date",
          "raw_value": "明天",
          "candidate_value": "2026-09-20",
          "confidence": 0.99,
          "evidence": {
            "message_id": "msg_mixed",
            "text": "明天",
            "start": 2,
            "end": 4
          }
        }
      ]
    }
  ],
  "business_intents": [
    {
      "intent": "cancel_auto_renewal",
      "confidence": 0.97,
      "evidence": {
        "message_id": "msg_mixed",
        "text": "把自动续费也关了",
        "start": 8,
        "end": 16
      },
      "entities": []
    }
  ],
  "unmapped_requests": [],
  "ambiguities": []
}
~~~

Harness 分别生成当前机票 Workflow 的 Engine Command 和 `cancel_auto_renewal` 的 Router Request。模型没有声明该意图是新流程。

### 21.4 相同意图的不同路由结果

用户说“我还是要退款”，模型输出：

~~~json
{
  "interpretation_version": "0.2",
  "utterance_id": "msg_refund",
  "language": "zh-CN",
  "interaction_acts": [],
  "business_intents": [
    {
      "intent": "refund_request",
      "confidence": 0.98,
      "evidence": {
        "message_id": "msg_refund",
        "text": "退款",
        "start": 4,
        "end": 6
      },
      "entities": []
    }
  ],
  "unmapped_requests": [],
  "ambiguities": []
}
~~~

Router 根据状态分别可能决定：

| 运行状态 | Router Decision |
|---|---|
| 当前就是退款 Workflow | `continue_current_workflow` |
| 存在暂停的退款 Workflow | `resume_existing_workflow` |
| 没有退款 Workflow | `start_new_workflow` |
| 当前还有其他可并行流程 | `start_additional_workflow` |

模型输出不随这些运行状态改变。

### 21.5 无法映射不等于不支持

Intent Catalog 中没有信用卡申请，用户说“帮我申请一张信用卡”：

~~~json
{
  "interpretation_version": "0.2",
  "utterance_id": "msg_unmapped",
  "language": "zh-CN",
  "interaction_acts": [],
  "business_intents": [],
  "unmapped_requests": [
    {
      "summary": "用户希望申请信用卡",
      "evidence": {
        "message_id": "msg_unmapped",
        "text": "帮我申请一张信用卡",
        "start": 0,
        "end": 9
      },
      "confidence": 0.98
    }
  ],
  "ambiguities": []
}
~~~

Router 或能力发现组件查询完整目录后，才决定启动某项能力、澄清或返回 `unsupported`。

### 21.6 历史指代存在歧义

历史中出现过两个航班，用户说“就那个吧”：

~~~json
{
  "interpretation_version": "0.2",
  "utterance_id": "msg_ambiguous",
  "language": "zh-CN",
  "interaction_acts": [],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": [
    {
      "kind": "reference",
      "about": "slots.selected_flight_id",
      "message_id": "msg_ambiguous",
      "text": "那个",
      "candidates": ["CA123", "MU5101"],
      "suggested_question": "你指的是 CA123 还是 MU5101？"
    }
  ]
}
~~~

Harness 不产生 Engine Command，并保持当前 wait_token 有效。

### 21.7 模型尝试写 Artifact

以下输出非法：

~~~json
{
  "interpretation_version": "0.2",
  "utterance_id": "msg_attack",
  "language": "zh-CN",
  "interaction_acts": [
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
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
~~~

Harness 必须返回 `DISALLOWED_SLOT`，不产生 Engine Command。

---

## 附录 A：语义输出速查

| 输出 | 含义 | 下游 |
|---|---|---|
| `answer` | 回答当前 ask | Workflow Engine |
| `slot_change` | 修改允许的 Slot | Workflow Engine |
| `cancel_interaction` | 取消当前 ask | Workflow Engine |
| `business_intents` | 用户业务目标，不包含流程关系 | Intent Router |
| `unmapped_requests` | 无法映射到当前 Intent Catalog | Intent Router / 能力发现 |
| `ambiguities` | 存在不唯一解释 | Harness 澄清 |

## 附录 B：模型禁止字段

~~~text
command_id
workflow_id
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
new_intent
is_new
route_action
start_new_workflow
resume_existing_workflow
unsupported
~~~

## 附录 C：四份职责的关系

~~~text
Workflow Definition 规范
  定义单个 Workflow 允许读写什么、如何执行和如何失效

Harness Interpretation 协议
  定义自然语言如何转换为当前流程动作和业务意图候选

Intent Router
  判断业务意图与活动 Workflow 的关系，并决定继续、恢复或创建

Workflow Engine 交互协议
  定义可信 Command 如何驱动具体 Workflow Instance
~~~
