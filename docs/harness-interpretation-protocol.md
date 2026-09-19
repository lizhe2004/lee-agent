# Harness Interpretation 协议

状态：Draft
协议版本：0.3.0

本文定义 Harness 如何向语言模型提供受约束的理解上下文、语言模型必须返回什么结构，以及 Harness 如何把不可信的语义候选校验为 Workflow Engine Command 或 Intent Router Request。

本文依赖：

- [Workflow Definition 规范](./workflow-definition-spec.md)
- [Workflow Engine 交互协议](./workflow-engine-protocol.md)

---

## 0. 本文所需的最小术语

阅读本文不要求先阅读另外两份规范。本文使用以下术语：

| 术语 | 在本文中的含义 |
|---|---|
| Workflow Definition | 一套带版本的静态业务流程模板，例如“机票预订 1.0.0”；它定义步骤、数据和规则，不保存某位用户的处理进度 |
| Workflow Instance | 某个用户或案件按照一个 Definition 运行出来的流程实例；它保存当前进度、用户已经提供的数据和工具结果 |
| ask 节点 | Workflow 中暂停执行并等待用户回答的步骤，例如“请选择航班”或“是否确认购买” |
| Slot | Workflow 中允许用户、调用方或可信事件提供和修改的业务变量，例如出发日期、手机号、订单号 |
| Artifact | Workflow 或工具计算出的结果，例如航班列表、身份验证结果；用户不能通过自然语言直接写入 |
| pending interaction | 当前正在等待用户处理的问题的语义描述，包含问题类型、提示文案、允许回答的字段和选项，不包含 Engine 内部控制 ID |
| Engine Command | Harness 校验完成后提交给 Engine 的结构化操作，例如回答当前问题或修改出发日期 |
| Engine Emission | Engine 产生的结构化输出，例如要求询问用户、调用工具或报告流程完成 |
| Business Intent | 用户希望完成的业务目标，例如退款或关闭自动续费；它不表示应该新建还是继续某个 Workflow |
| Intent Router | 根据业务意图、活动流程和系统能力决定继续、恢复或创建哪个 Workflow 的组件 |
| Field Registry | 可跨 Intent 和 Workflow 复用的业务字段定义目录；它定义字段的类型、规范化和敏感级别，不保存某个实例的当前值 |

另外两份规范用于定义这些对象的完整执行规则；本文会在字段第一次出现时给出足以理解本协议的含义。

### 0.1 字段表中的类型记法

| 记法 | 含义 |
|---|---|
| string、integer、number、boolean、object、array、null | 对应同名 JSON 类型；integer 是没有小数部分的 number |
| enum | 封闭枚举；允许值必须在同一字段行或紧随其后的约束表中逐项列出，未列出的值非法 |
| const string | 只能等于字段行指定的唯一字符串 |
| array<T> | 元素都符合 T 的 JSON 数组；是否允许空数组由字段约束说明 |
| object<K, V> | key 符合 K、value 符合 V 的 JSON 对象 |
| A \| B | 值可以是 A 或 B 两种类型之一 |
| datetime | 带时区偏移的 RFC 3339 日期时间字符串 |
| slot-ref | 形如 `slots.departure_date` 的完整 Slot 引用 |
| field-ref | Field Registry 中的稳定字段 ID，例如 `order_reference`；它不是 Runtime State 地址 |
| any | JSON 值的形状由被引用 Slot、Intent Entity 或其他明确合同决定，不表示跳过校验 |

“必填”列描述字段在什么条件下必须出现；“否”表示字段可以省略，不等于可以传入任意值。本文未明确允许的未知字段必须拒绝。

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
- revision 和 interaction_id；
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
expected_instance_revision
expected_slot_revisions
interaction_id
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
- 再次校验权限、状态、revision、interaction_id 和 Policy；
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
| answer | 用户在回答 `pending_interaction` 中正在询问的字段，例如选择某个航班或确认购买 | Harness 校验后生成 `interaction.answer` Engine Command |
| slot_change | 用户主动更正已经提供的业务变量，例如把出发日期从今天改成明天；它可以发生在确认等后续阶段 | Harness 校验后生成 `slot.change` Engine Command |
| cancel_interaction | 用户表示不再回答当前这个问题，例如在选择列表时说“算了”；它只关闭当前问题，不等于取消订单或终止整个业务 | Harness 校验后生成 `interaction.cancel` Engine Command |

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
  "interpretation_version": "0.3",
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
  "pending_interaction": {
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
      "current_value": "2026-09-19",
      "description": "乘客希望出发的日期"
    },
    "slots.booking_confirmed": {
      "type": "boolean",
      "mutable": true,
      "current_value": null,
      "description": "用户是否确认购买当前展示的航班和价格"
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

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| interpretation_version | string | 是 | 本次模型输入使用的结构版本；模型必须在结果中原样返回，Harness 用它选择对应校验规则 |
| utterance | object | 是 | 本轮刚收到的用户消息，包括消息 ID、原文、语言和接收时间；这是模型本轮需要解释的主要内容 |
| locale | string | 是 | BCP 47 地区语言代码，例如 `zh-CN`；用于解释数字、日期写法和生成澄清问题 |
| timezone | string | 出现日期或时间时 | IANA 时区名称，例如 `Asia/Shanghai`；禁止只写容易歧义的缩写 |
| reference_time | datetime | 出现相对日期或时间时 | RFC 3339 基准时刻；“今天”“明天”等表达只能相对它计算 |
| conversation_context | object | 需要历史语境时 | Harness 选择的历史摘要、最近消息和较早相关消息，用于理解省略和指代 |
| pending_interaction | object | 系统正在等待用户回答时 | 当前问题的语义描述；没有待回答问题时省略，且不得包含 Engine 内部 ID、节点 ID 或 revision |
| allowed_interaction_acts | array<enum> | 是 | 本轮允许模型输出的动作类型集合；元素只允许 `answer`、`slot_change`、`cancel_interaction`，不得重复，数组可为空 |
| allowed_slots | object<slot-ref, slot-descriptor> | 是 | Slot 完整引用到字段描述的映射；空对象表示本轮不能回答或修改任何 Slot |
| intent_catalog | array<intent-definition> | 是 | 本轮允许识别的业务目标定义；空数组表示本轮不做业务意图分类 |

### 4.3 utterance

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| id | string | 是 | 渠道为本条消息分配的稳定 ID；结果中的 `utterance_id` 必须与它相同 |
| text | string | 是 | 用户实际发送的非空原文；不得用摘要、翻译或改写文本替代 |
| language | string \| null | 是 | 检测到的 BCP 47 语言代码；无法可靠判断时为 `null` |
| received_at | datetime | 是 | 渠道收到消息的 RFC 3339 时间，用于审计和排序，不代替 `reference_time` |

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

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| summary | object | 否 | 对较早对话的压缩内容；只能帮助理解语境，不能证明身份验证或业务操作已经完成 |
| summary.text | string | summary 出现时 | 非空摘要正文；应描述已经讨论的对象和用户表达，不得伪造 Engine 状态或工具结果 |
| summary.through_message_id | string | summary 出现时 | 摘要覆盖到的最后一条消息 ID；该消息及更早消息不得再放入 `recent_turns` |
| recent_turns | array<turn> | 是 | 紧邻当前消息之前的用户和客服原文，按时间从旧到新排列；没有时为空数组 |
| relevant_turns | array<turn> | 是 | 从 summary 覆盖范围内检索出的少量相关原文；没有时为空数组 |
| recent_turns[].message_id | string | 每个 turn 必填 | 渠道分配的稳定消息 ID，且必须早于当前 `utterance.id` 所代表的消息 |
| recent_turns[].role | enum | 每个 turn 必填 | 只允许 `user` 或 `assistant` |
| recent_turns[].text | string | 每个 turn 必填 | 经过必要脱敏的非空消息原文 |

`relevant_turns` 的元素使用与 `recent_turns` 相同的 turn 结构。一个 `message_id` 不得在两个数组中重复出现。

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

## 6. pending_interaction 与 allowed_slots

### 6.1 pending_interaction

`pending_interaction` 只在系统已经向用户提出问题并正在等待回答时出现。没有待回答问题时整个字段省略。

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| kind | enum | 是 | 回答形式，只允许 `form`、`selection`、`confirmation`、`text`；每个值的组合约束见下表 |
| prompt | string | 是 | 当前向用户提出的非空问题文字，模型用它理解“确认”“第一个”等依赖问题内容的回答 |
| fields | array<slot-ref> | 是 | 本次回答允许填写的 Slot 完整引用；至少一项、不得重复，且每项必须同时存在于 `allowed_slots` |
| options | array<option> | 是 | 当前选择题选项；`selection` 时至少一项，其他 kind 时必须为空数组 |
| options[].value | 与目标 Slot 相同 | 每个 option 必填 | 提交给 Engine 的规范值；必须通过目标 Slot 类型校验，且同一 options 数组中不得重复 |
| options[].label | string | 每个 option 必填 | 展示给用户的非空文本；模型可用它理解“第一个”或用户复述的选项名称 |

`kind` 的允许值和结构约束：

| kind 值 | fields 约束 | options 约束 | 回答语义 |
|---|---|---|---|
| form | 一项或多项 | 必须为空数组 | 用户可以在一轮中填写 `fields` 中的一个或多个字段 |
| selection | 恰好一项 | 至少一项 | 用户从当前有效选项中选择一个值；`answers[].candidate_value` 必须等于某个 `options[].value` |
| confirmation | 恰好一项，且目标 Slot 的 `type` 必须是 `boolean` | 必须为空数组 | 用户确认或拒绝当前问题，候选规范值只能是 `true` 或 `false` |
| text | 恰好一项 | 必须为空数组 | 用户自由表达一个字段值；Harness 仍按目标 Slot 类型做规范化和校验 |

因此 `kind` 既不是任意字符串，也不是给 UI 的展示提示。它是影响 Interpretation Result 校验规则的封闭枚举。未知值必须被 Harness 拒绝。

例如，Engine 正在让用户从当前航班列表中选择一项时，Harness 可以给模型以下视图：

~~~json
{
  "pending_interaction": {
    "kind": "selection",
    "prompt": "请选择航班",
    "fields": ["slots.selected_flight_id"],
    "options": [
      {"value": "CA123", "label": "CA123，10:00 起飞"},
      {"value": "MU5101", "label": "MU5101，11:20 起飞"}
    ]
  }
}
~~~

用户说“第二个”时，模型可以生成目标为 `slots.selected_flight_id`、候选值为 `MU5101` 的 `answer`。如果用户说出不在 options 中的航班号，Harness 必须拒绝该候选或发起澄清，不能把它当成当前选择题的有效答案。

Harness 必须在自己的可信上下文中保存 `workflow_instance_id`、`interaction_id`、`node_id` 和 `expected_instance_revision`。这些控制字段不得放入 `pending_interaction`，模型也不得返回它们。

#### 6.1.1 Engine 事件与模型动作的映射

这里有两个不同层次的字段：

- `request.accepts` 属于静态 Workflow Definition，表示 Engine 允许哪些事件结束当前 ask 等待；
- `allowed_interaction_acts` 属于发给模型的运行时输入，表示模型本轮可以识别并返回哪些 Interaction Act。

Harness 根据可信的 Definition 和 Runtime State 固定生成下面的映射，模型不能自行增加、删除或改名：

| Definition 中的 `request.accepts` | 模型允许的 Interaction Act | 作用 |
|---|---|---|
| 包含 `answer` | `answer` | 用户回答当前 ask；Harness 校验答案只填写 `pending_interaction.fields` |
| 包含 `cancel` | `cancel_interaction` | 用户放弃当前 ask；它不等于取消订单、订阅或整个 Workflow |
| 不适用 | `slot_change` | 用户修改仍可变的 Slot；这是实例级修改事件，不负责结束当前 ask，也不写入 `request.accepts` |

因此，`answer` 和 `cancel_interaction` 是否可用取决于当前 ask 的 `request.accepts`；`slot_change` 是否可用取决于 `allowed_slots` 中是否存在可修改字段以及相关 Policy。这个映射是 Harness 的确定性规则，不是模型需要推断的业务逻辑。

### 6.2 allowed_slots

`allowed_slots` 只能包括：

- 当前 ask 的 `request.fields`；
- 当前实例中 `source` 允许用户写入且 `mutable` 允许修改的 Slots。

预路由阶段的实体不应为了复用这张表而伪装成 Runtime Slot；它们通过 `allowed_entities` 和 Field Registry 传递。只有 Router 已经把实体明确绑定到某个 Workflow 的初始 Slot 后，才会作为 `workflow.start.initial_slots` 或后续 `slot.change` 的候选值进入 Engine 校验。

每个 Slot 描述可包含：

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| type | slot-type | 是 | 目标 Slot 的规范值类型，例如 `string`、`date`、`boolean`、`enum`；候选值必须能通过该类型校验 |
| field_ref | field-ref | 否 | 该 Slot 对应的 Field Registry 字段 ID；存在时，Slot 的 type、schema、sensitive 和规范化规则必须与 Registry 一致，但不会因此自动获得写入权限 |
| schema | schema-ref | type 为 `object`、`array` 或注册扩展类型时 | 目标 Slot 的结构版本；存在时必须与 Field Registry 中同一 field_ref 的 schema 一致 |
| mutable | boolean | 是 | 用户在当前流程阶段是否可以修改该 Slot；为 `false` 时不得输出针对它的 `slot_change` |
| current_value | 与 type 一致 \| null | 否 | Engine 当前保存的规范值；只在理解更正、指代或“保持原值”确实需要时提供，尚无值时可为 `null` |
| values | array<any> | type 为 enum 时 | enum 的完整允许值集合；每项类型必须与 Slot 一致，且不得重复 |
| sensitive | boolean | 否 | 是否包含手机号、证件号等敏感信息；省略等同于 `false` |
| description | string | 是 | Slot 的非空业务含义；不能夹带流程跳转、工具调用或权限指令 |

本协议内置的 `slot-type` 允许 `string`、`integer`、`number`、`boolean`、`date`、`datetime`、`money`、`phone`、`email`、`enum`、`object` 和 `array`。使用注册扩展类型时，Harness 必须把模型候选交给对应的确定性校验器，不能让模型自行定义类型语义。

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

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| id | string | 是 | 程序使用的稳定、非空业务目标 ID，例如 `refund_request`；同一 Catalog 内必须唯一 |
| description | string | 是 | 该业务目标包含和排除范围的直接说明，模型以它作为分类依据 |
| positive_examples | array<string> | 否 | 属于该意图的典型表达；每项必须非空，不代表只有这些说法才能命中 |
| negative_examples | array<string> | 否 | 容易混淆但不属于该意图的表达，用于划清相邻意图边界 |
| allowed_entities | array<field-ref> | 否 | 允许随该意图提前提取的字段 ID 白名单；每个 ID 必须存在于可信 Field Registry，不得重复，省略等同于空数组 |

### 7.3 allowed_entities 的用途

`allowed_entities` 控制的是“识别业务意图时，模型可以顺便从当前消息中提取哪些业务对象”，而不是流程运行时可以写入哪些字段。它主要用于意图已经明确、但 Router 在启动或恢复 Workflow 前还需要少量定位信息的场景。

例如：

| Intent | allowed_entities | 用户表达 | 提取结果的用途 |
|---|---|---|---|
| `refund_request` | `order_reference` | “帮我退订单 A123” | Router 可以用订单引用查找应该处理的订单，或把它作为退款 Workflow 的启动候选值 |
| `book_flight` | `origin`、`destination`、`departure_date` | “明天北京飞上海” | Router 可以据此选择机票能力，并把已提取的出发地、到达地和日期交给后续 Workflow 进行类型校验和补问 |
| `cancel_auto_renewal` | 空数组 | “把自动续费关了” | 该意图不需要预路由实体；Workflow 后续再按账号和身份验证流程确定具体订阅 |

这里的 `order_reference`、`origin` 和 `departure_date` 是 Field Registry 中的字段 ID，不是用户实际填写的值，也不是某个 Workflow 的节点 ID。它们在本协议的输出中被称为“实体”，是因为模型此时承担的是从用户消息中提取实体候选的角色。Registry 至少为每个字段提供稳定名称、规范类型或 Schema、规范化器和敏感级别；模型不能自行发明字段类型或解释规则。

`allowed_entities` 的处理顺序是：

1. 模型先根据 `id` 和 `description` 判断 Business Intent；
2. 仅对该 Intent 的 `allowed_entities` 白名单尝试提取实体；
3. Harness 校验证据、规范化候选值并检查实体名称是否在白名单中；
4. Harness 将通过校验的实体放入 `business_intents[].entities`，交给 Router；
5. Router 决定实体是否用于查找案件、填充新 Workflow 的初始 Slot，或触发补问。

实体缺失不是错误。用户只说“我要退款”时，`refund_request` 可以命中，但 `entities` 为空，Router 再决定是否需要询问订单。实体有多个可能指代时，Harness 应产生 Ambiguity，不能随便选择一个。

`allowed_entities` 不承担以下职责：

- 不代表用户已经通过身份验证或拥有操作权限；
- 不代表订单满足退款条件、航班仍有余票或订阅确实存在；
- 不直接写入 Slot、Artifact 或 Runtime State；
- 不决定使用哪个 Workflow、是否新建流程或是否并行处理；
- 不替代当前活动 Workflow 的 `allowed_slots`。

`allowed_slots` 描述当前 Workflow 在当前运行阶段允许回答或修改的 Slot；`allowed_entities` 描述路由前为了识别业务目标可以提取的实体。两者即使使用相同名称，也不存在自动映射关系，必须由 Router 或 Workflow Definition 的可信映射明确建立。

### 7.4 Field Registry 的最小合同

Field Registry 是受信任的静态配置目录。Intent Catalog 和 Workflow Definition 都可以引用其中的字段 ID，不在自然语言描述里重新定义类型。每个被 `allowed_entities` 或 Workflow Slot 引用的字段至少应有：

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| id | string | 是 | 稳定字段 ID，例如 `order_reference`；在 Registry 内唯一 |
| type | slot-type 或 schema-ref | 是 | 字段候选值的规范类型；Harness 和 Engine 必须使用对应校验器 |
| description | string | 是 | 给模型和维护者看的非空业务含义；不包含权限或流程跳转指令 |
| normalizer | string | 是 | 已注册的确定性规范化器 ID；不能是模型临时生成的函数或代码 |
| sensitive | boolean | 是 | 是否需要脱敏、限制日志和限制上下文传播 |

例如，`order_reference` 可以定义为：

~~~json
{
  "id": "order_reference",
  "type": "string",
  "description": "用户指向的平台订单编号或可唯一定位订单的公开引用",
  "normalizer": "order_reference@1",
  "sensitive": false
}
~~~

Field Registry 只定义字段本身的语义和规范化方式，不定义它要启动哪个 Workflow。实体候选到 Workflow 初始 Slot 的映射属于 Router 或具体 Workflow 的可信配置。

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
  "interpretation_version": "0.3",
  "utterance_id": "msg_123",
  "language": "zh-CN",
  "interaction_acts": [],
  "business_intents": [],
  "unmapped_requests": [],
  "ambiguities": []
}
~~~

### 8.2 顶层字段

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| interpretation_version | string | 是 | 模型实际采用的结果结构版本，必须与输入版本完全相同 |
| utterance_id | string | 是 | 必须等于输入的 `utterance.id`，防止异步结果绑定到错误消息 |
| language | string \| null | 是 | 模型用于理解本条消息的 BCP 47 语言代码；无法可靠判断时为 `null` |
| interaction_acts | array<interaction-act> | 是 | 对待处理问题或已有 Slot 的动作；没有时为空数组，每项类型必须位于 `allowed_interaction_acts` |
| business_intents | array<business-intent> | 是 | 本轮明确表达且映射到 Intent Catalog 的业务目标；没有时为空数组，同一 intent 不得重复 |
| unmapped_requests | array<unmapped-request> | 是 | 本轮明确表达但无法映射到 Catalog 的请求；没有时为空数组 |
| ambiguities | array<ambiguity> | 是 | 会影响执行且无法唯一解释的歧义；没有时为空数组 |

未知顶层字段必须被 Harness 拒绝。模型名称、调用 ID、延迟和 token 用量由 Harness 从模型客户端取得并记录。

### 8.3 为什么拆成四个数组

同一句话可能同时包含多种语义：

> 改成明天吧，另外把自动续费也关了。

其中：

- “改成明天”是当前流程内的 `slot_change`；
- “关闭自动续费”是 `cancel_auto_renewal` Business Intent；
- 它是不是新流程，由 Router 结合活动 Workflow 判断；
- 如果“自动续费”不在 Intent Catalog，模型写入 `unmapped_requests`，不能断言系统不支持。

## 9. 结构化候选的证据与置信度

Interpretation Result 中的答案、Slot 修改、实体和业务意图都是模型提出的候选，不是系统已经确认的事实。Harness 需要两类不同的元数据来检查这些候选：

- `evidence` 说明候选来自哪条原始消息、哪一段文字，解决“模型依据了什么”的问题；
- `confidence` 是模型对这次语义映射的自评，解决“模型自己有多确定”的问题。

它们都不能直接授予权限、改变 Runtime State 或跳过 Engine 校验。`evidence` 是可被 Harness 重新计算和验证的来源信息；`confidence` 只是模型意见，不能当成事实证明。

### 9.1 Evidence：候选的原文依据

从用户文本提取的候选应包含 Evidence。它适用于：

- `answer` 中的字段答案；
- `slot_change` 中的字段修改；
- Business Intent 本身；
- Business Intent 的实体；
- 需要说明用户表达依据的取消动作或其他 Interaction Act。

Evidence 只回答“候选来自哪里”，不回答“候选是否有权限执行”或“候选是否符合业务条件”。例如，用户说出订单号可以作为 `order_reference` 的 Evidence，但不能证明用户是该订单的所有者，也不能证明订单符合退款条件。

~~~json
{
  "message_id": "msg_123",
  "text": "明天",
  "start": 2,
  "end": 4
}
~~~

`start` 和 `end` 使用 Unicode code point 索引，区间左闭右开。`evidence.text` 必须与对应消息原文的切片一致。

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| message_id | string | 是 | Evidence 所引用的原始消息 ID；必须来自 Request 中可见的 utterance 或 turn |
| text | string | 是 | 对应原始消息中的连续非空片段 |
| start | integer | 是 | `text` 在原消息中的 Unicode code point 起始索引，必须大于等于 0 |
| end | integer | 是 | 片段结束后的索引，必须大于 `start`，且不得超过原消息长度 |

必须满足：`original_message[start:end] == text`。同一字段需要多段证据时，应使用多个结构化结果，而不能把不连续文本拼成一个 Evidence。

默认要求 Business Intent 以当前 utterance 为证据。历史消息可以帮助消解指代，但模型不能只根据历史消息重复产生用户本轮没有表达的业务目标。

### 9.2 Confidence：模型对映射的自评

`confidence` 是 0 到 1 的模型自评值，表示模型对“这段用户表达对应这个结构化候选”的把握程度。它不是经过校准的概率，也不是 Engine 对业务结果的判断。它只能用于确认、澄清、观测和评估策略。

Harness 可以结合 Confidence 制定澄清策略，但阈值和动作属于 Harness Policy，而不是模型自行决定。例如：

| Evidence | Confidence | 处理含义 |
|---|---|---|
| 能定位到原文 | 高 | 候选仍需经过类型、白名单和权限校验；可以进入正常校验流程 |
| 能定位到原文 | 低 | 可能需要澄清，不能仅凭候选直接提交 Command |
| 不能定位到原文 | 任意 | 属于未扎根候选，Harness 必须拒绝或要求重新解释 |
| 原文存在多个合理指代 | 任意 | 产生 Ambiguity，不能用高 Confidence 代替用户选择 |

Confidence 不得：

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

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| type | const string | 是 | 固定为 `answer` |
| answers | array<answer-item> | 是 | 本轮对当前问题填写的字段；至少一项，同一个 ref 不得重复 |
| answers[].ref | slot-ref | 是 | 必须出现在 `pending_interaction.fields` 中 |
| answers[].raw_value | string | 是 | 用户表达该答案时使用的非空原文片段，例如“明天”或“第一个” |
| answers[].candidate_value | any | 是 | 按目标 Slot 类型转换后的候选规范值；Harness 仍会重新规范化和校验 |
| answers[].confidence | number | 是 | 模型自评置信度，范围为闭区间 `[0, 1]`，不提供写入权限 |
| answers[].evidence | evidence | 是 | 支持该答案的消息与原文区间；必须通过第 9.1 节校验 |

`answer` 只能回答当前 ask，不能顺便写入其他 Slot。选项型回答必须匹配 `pending_interaction.options[].value`。

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

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| type | const string | 是 | 固定为 `slot_change` |
| changes | array<slot-change-item> | 是 | 用户本轮要求修改的字段；至少一项，同一个 ref 不得重复 |
| changes[].ref | slot-ref | 是 | 必须存在于 `allowed_slots`，且其 `mutable` 为 `true` |
| changes[].raw_value | string | 是 | 用户表达新值时使用的非空原文片段 |
| changes[].candidate_value | any | 是 | 按目标 Slot 类型转换出的候选规范值；Harness 校验通过后才可进入 Engine Command |
| changes[].confidence | number | 是 | 模型对修改语义和值映射的自评置信度，范围为闭区间 `[0, 1]` |
| changes[].evidence | evidence | 是 | 支持本次修改的消息与原文区间；必须通过第 9.1 节校验 |

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

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| type | const string | 是 | 固定为 `cancel_interaction` |
| confidence | number | 是 | 模型对“用户正在放弃当前问题”的自评置信度，范围为闭区间 `[0, 1]` |
| evidence | evidence | 是 | 当前消息中表达放弃的原文区间 |

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

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| intent | string | 是 | 必须等于某个 `intent_catalog[].id`；同一结果数组中不得重复 |
| confidence | number | 是 | 匹配程度的模型自评值，范围为闭区间 `[0, 1]` |
| evidence | evidence | 是 | 当前 utterance 中明确表达该业务目标的原文区间；不能只引用历史摘要 |
| entities | array<entity> | 是 | 随该意图提取的实体；没有时为空数组，名称必须位于该 Catalog 条目的 `allowed_entities` |
| entities[].name | field-ref | 每个 entity 必填 | Intent Catalog `allowed_entities` 中允许的字段 ID |
| entities[].raw_value | string | 每个 entity 必填 | 用户表达该实体时使用的非空原文片段 |
| entities[].candidate_value | any | 每个 entity 必填 | 模型转换出的候选值；Router 或 Workflow 仍需按目标字段重新校验 |
| entities[].confidence | number | 每个 entity 必填 | 模型自评置信度，范围为闭区间 `[0, 1]` |
| entities[].evidence | evidence | 每个 entity 必填 | 支持该实体的消息和原文区间 |

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

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| summary | string | 是 | 用户请求的简短、非空语义摘要；不得添加用户没有表达的目标 |
| evidence | evidence | 是 | 当前 utterance 中支持该请求的原文区间 |
| confidence | number | 是 | 模型对摘要是否准确表达该请求的自评值，范围为闭区间 `[0, 1]` |

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

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| kind | enum | 是 | 歧义类别，只允许 `reference`、`value`、`date`、`action`、`intent` 或 `conflict` |
| about | string | 是 | 受阻的 Slot 引用、Interaction Act 类型、Intent ID 或稳定语义标签 |
| message_id | string | 是 | 引发歧义的原文消息 ID，必须来自 Request 中可见的消息 |
| text | string | 是 | 无法唯一解释的非空原文片段，必须能在该消息中定位 |
| candidates | array<any> | 是 | 当前上下文中的有限候选；无法可靠列举时为空数组，不得杜撰候选 |
| suggested_question | string | 是 | 建议向用户提出的非空问题；Harness 必须校验、转义后才能展示 |

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
- selection 必须来自 `pending_interaction.options[].value`；
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
- `answer.ref` 属于 `pending_interaction.fields`；
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
- 当前 interaction_id 仍有效；
- 当前 ask 没有被新 Emission 替代；
- Slot 仍然 mutable；
- actor 仍然有权写入；
- instance revision 与 Harness 快照一致。

### 15.5 冲突处理和编译

存在无法可靠解决的冲突时，不生成受影响的 Engine Command 或 Router Request。验证通过后：

- Interaction Act 从可信上下文补充执行字段，编译为 Engine Command；
- Business Intent 和 Unmapped Request 补充 actor、tenant、channel 和 utterance ID，编译为 Router Request；
- Ambiguity 编译为澄清请求，不改变 revision，也不关闭当前 pending interaction。

## 16. Interpretation 到 Engine Command

### 16.1 answer

~~~text
Interpretation answer
  + 当前 workflow_instance_id
  + 当前 expected_instance_revision
  + 当前 interaction_id
  + 认证 actor
  → interaction.answer
~~~

| Interpretation | Engine Command |
|---|---|
| `answers[].ref` | `payload.answers` 的 key |
| 规范化后的 candidate value | `payload.answers` 的 value |
| 无 | `command_id`，由 Harness 生成 |
| 无 | `interaction_id`，由 Harness 从当前待回答问题的可信记录中取得；模型输入和输出都不包含它 |
| 无 | `expected_instance_revision`，由 Harness 在提交前读取当前 Workflow Instance 的版本；模型不能提供它 |

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

`cancel_interaction` 编译为 `interaction.cancel`。Harness 使用自己为当前待回答问题保存的真实 `interaction_id`；Engine 根据该 ID 找到对应节点和等待状态。

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

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| router_protocol_version | string | 是 | Router Request 的结构版本 |
| request_id | string | 是 | Harness 生成的全局唯一请求 ID，用于幂等处理和关联 Router Decision |
| utterance_id | string | 是 | 产生本请求的当前用户消息 ID |
| actor | object | 是 | 已认证业务主体；由 Harness 的可信会话上下文构造，不能来自模型输出 |
| actor.type | enum | 是 | 只允许 `user`、`system` 或 `operator`；普通自然语言用户使用 `user` |
| actor.id | string | 是 | 认证系统确认的稳定主体 ID |
| actor.tenant_id | string | 多租户时 | 主体所属租户；必须与 Router 查询能力目录时使用的租户一致 |
| actor.roles | array<string> | 否 | 认证系统确认的角色；不得重复，不得从用户自述中提取 |
| channel | string | 是 | 已认证或配置得到的渠道 ID，例如 `cli`；不能由用户文本决定 |
| business_intents | array<business-intent> | 是 | 已通过 Catalog、Evidence 和白名单校验的业务意图；没有时为空数组 |
| unmapped_requests | array<unmapped-request> | 是 | 已通过 Evidence 校验但未映射的请求；没有时为空数组 |
| source_order | array<source-item> | 是 | 记录两类请求在原消息中的语义顺序；每个业务意图或未映射请求必须恰好出现一次 |
| source_order[].kind | enum | 每个 source-item 必填 | 只允许 `business_intent` 或 `unmapped_request` |
| source_order[].index | integer | 每个 source-item 必填 | 对应数组中的零起始索引，不能越界或重复引用同一项 |

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

Harness 最终只返回以下四种状态：

| status | 何时使用 | 调用方接下来做什么 |
|---|---|---|
| commands_ready | 本轮只产生当前 Workflow 可以执行的 Command | 按顺序向 Workflow Engine 提交 `commands` |
| routing_required | 本轮只提出业务目标或无法映射的请求 | 把 `router_requests` 交给 Intent Router，由 Router 决定使用哪个 Workflow |
| commands_and_routing_ready | 同一句话同时包含当前流程修改和独立业务目标 | 分别提交 `commands` 和 `router_requests`，并保留原消息中的语义顺序 |
| clarification_required | 存在会影响执行正确性的歧义或冲突 | 不提交受影响的 Command，向用户展示 `user_response` 中的澄清问题 |

所有状态使用同一个输出信封：

| 字段 | 类型 | 必填 | 含义与约束 |
|---|---|---:|---|
| status | enum | 是 | 只允许 `commands_ready`、`routing_required`、`commands_and_routing_ready` 或 `clarification_required` |
| utterance_id | string | 是 | 必须等于本轮 Interpretation Request 的 `utterance.id` |
| commands | array<engine-command> | 是 | 已通过校验并补齐可信控制字段的 Engine Command；没有时为空数组 |
| router_requests | array<router-request> | 是 | 要交给 Router 的请求；没有时为空数组 |
| user_response | object \| null | 是 | 需要向用户澄清时包含 `code` 和 `message`，其他状态为 `null` |
| user_response.code | string | user_response 非 null 时 | 稳定、机器可读的澄清原因 |
| user_response.message | string | user_response 非 null 时 | 可以直接展示或由渠道安全改写的非空澄清问题 |

状态与内容必须一致：`commands_ready` 的 commands 非空；`routing_required` 的 router_requests 非空；`commands_and_routing_ready` 两个数组都非空；`clarification_required` 的 `user_response` 非 null。按照第 14.4 节，`clarification_required` 仍可携带与歧义完全独立的 commands 或 router_requests；调用方只提交这些已通过独立性校验的结果，并继续向用户澄清其余部分。

### 18.1 commands_ready

~~~json
{
  "status": "commands_ready",
  "utterance_id": "msg_123",
  "commands": [
    {
      "protocol_version": "0.2",
      "command_id": "cmd_456",
      "type": "slot.change",
      "workflow_instance_id": "wfi_789",
      "expected_instance_revision": 18,
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
- 旧 Interpretation Result 不得绑定到新的 `interaction_id` 或实例 revision；
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
  "interpretation_version": "0.3",
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

历史对话确定“确认”回答的对象。可回答的字段和选项来自 `pending_interaction`；真实 `interaction_id` 只保存在 Harness 的可信上下文和 Engine State 中。

### 21.2 确认阶段修改日期

用户说“改成明天吧”：

~~~json
{
  "interpretation_version": "0.3",
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
  "interpretation_version": "0.3",
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
  "interpretation_version": "0.3",
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
  "interpretation_version": "0.3",
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
  "interpretation_version": "0.3",
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

Harness 不产生 Engine Command，Engine 中当前 pending interaction 保持有效。

### 21.7 模型尝试写 Artifact

以下输出非法：

~~~json
{
  "interpretation_version": "0.3",
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
expected_instance_revision
expected_slot_revisions
interaction_id
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
