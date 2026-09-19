# Workflow JSON 定义规范

本文说明 workflow JSON 每个字段的**运行时含义**。它和 [`schemas/workflow.schema.json`](../schemas/workflow.schema.json) 的关系是：Schema 负责判断 JSON 结构是否合法；本文说明字段在流程引擎中如何解释、什么时候生效、由谁写入，以及失败时发生什么。

## 1. Workflow 是什么

一个 workflow 是一个有向图：

- `nodes` 是图中的节点。
- 节点之间通过节点 ID 连接。
- `current_node` 是某个案件当前所在节点。
- 引擎从 `start` 开始运行，自动执行不需要用户输入的节点。
- 遇到 `ask`、`wait` 或 `end` 时暂停本轮运行。

Workflow 定义的是程序必须遵守的执行规则，不是给模型阅读的长篇 SOP。Skill 可以解释同一流程应该如何和用户沟通，但不能替代 workflow 的门槛。

## 2. 顶层字段

示例：

```json
{
  "$schema": "../schemas/workflow.schema.json",
  "id": "refund_request",
  "version": 1,
  "description": "处理退款请求",
  "mutable_inputs": {},
  "start": "collect_order_clues",
  "nodes": {}
}
```

| 字段 | 类型 | 必填 | 实际含义 |
|---|---|---:|---|
| `$schema` | string | 否 | 编辑器或校验器使用的 Schema 地址。引擎不把它当作流程逻辑。 |
| `id` | string | 是 | workflow 的稳定标识，例如 `refund_request`。案件启动后会保存这个值。只能使用小写字母、数字和下划线，且以字母开头。 |
| `version` | integer | 是 | 这份定义的不可变版本号。案件启动时保存版本；恢复旧案件时继续使用旧版本，避免流程更新改变处理中案件的语义。 |
| `description` | string | 否 | 给维护者看的说明，不影响迁移。 |
| `start` | node ID | 是 | 新案件第一次执行的节点。必须存在于 `nodes`。 |
| `nodes` | object | 是 | 节点 ID 到节点定义的映射。每个节点 ID 必须唯一。 |
| `mutable_inputs` | object | 否 | 声明用户后续可以修改的输入，以及修改后哪些事实失效、从哪里重新计算。见第 5 节。 |

Schema 的 `additionalProperties: false` 表示顶层不能随便增加字段。需要增加运行语义时，先更新规范、Schema、loader 和引擎，不要静默接受未知字段。

## 3. 通用节点字段

每个节点必须有 `type`。节点 ID 只用于图内跳转，不是数据库 ID，也不应暴露给用户。

| 字段 | 适用节点 | 实际含义 |
|---|---|---|
| `type` | 所有节点 | 节点行为类型：`ask`、`branch`、`action`、`respond`、`wait`、`end`。 |
| `max_visits` | 可循环节点 | 同一案件最多进入该节点多少次。用于限制验证码重试、查单补充信息等循环。 |
| `on_limit` | 设置 `max_visits` 时 | 达到访问次数上限后跳转的节点，通常是 `escalate`。设置 `max_visits` 却没有它属于 Schema 错误。 |

`max_visits` 统计的是进入节点的次数，不是工具重试次数。工具的网络重试应由工具层处理；业务失败状态应通过 `transitions` 处理。

## 4. 节点类型

### 4.1 `ask`：等待用户输入

```json
{
  "type": "ask",
  "collect": ["charge_date", "amount"],
  "sensitive_collect": [],
  "prompt": "请提供扣款日期和金额。",
  "next": "find_order"
}
```

| 字段 | 类型 | 实际含义 |
|---|---|---|
| `collect` | string[] | Agent 本轮只能从用户回复中提取的字段白名单。提取结果要经过类型和来源校验后才能写入 `facts`。 |
| `sensitive_collect` | string[] | `collect` 中需要特殊处理的字段，例如 OTP。它表示字段敏感，不表示可以绕过工具验证。敏感值应在工具调用后消费、脱敏或从持久化存储中删除。 |
| `prompt` | string | 给 Agent 的提问内容。Agent 可以调整语气，但问题必须围绕这些字段。 |
| `next` | node ID | 用户回答被接受后进入的节点。它不表示工具成功；只是表示本次提问结束。 |

`ask` 到达后，引擎将案件标为 `waiting_for_user` 并停止。下一条消息恢复案件，Harness 依据当前节点的 `collect` 提取字段。

### 4.2 `branch`：确定性分支

```json
{
  "type": "branch",
  "cases": [
    {"when": "order.channel == 'apple'", "next": "guide_apple"}
  ],
  "default": "guide_other_store"
}
```

| 字段 | 类型 | 实际含义 |
|---|---|---|
| `cases` | object[] | 按数组顺序检查的条件分支。第一个为真的条件获胜。 |
| `cases[].when` | restricted expression | 只读 `facts` 的受限表达式，支持 dotted path、字符串/数字/布尔/null 字面量、`==`、`!=`、`and`、`or`。不是 Python 代码，不能调用函数。 |
| `cases[].next` | node ID | 条件为真时的目标节点。 |
| `default` | node ID | 没有条件为真时的目标节点，必须明确配置，不能让模型猜。 |

条件只能使用已经写入 `facts` 的值。工具没有返回 `order.channel` 时，`order.channel == 'apple'` 为假，流程会继续检查其他 case 或 `default`。

### 4.3 `action`：受控工具操作

```json
{
  "type": "action",
  "tool": "submit_refund",
  "args": {"order_id": "{{ order.id }}"},
  "requires": [
    "target_account_verified",
    "order.id",
    "refund_eligibility == 'eligible'",
    "confirm_refund"
  ],
  "on_guard_failure": "escalate",
  "result_statuses": ["submitted", "already_submitted", "error"],
  "transitions": {
    "submitted": "report_submitted",
    "already_submitted": "report_already_submitted",
    "error": "escalate"
  },
  "save_result_as": "refund_submission",
  "consume_facts": [],
  "idempotency_key": "{{ case_id }}:refund:{{ order.id }}"
}
```

| 字段 | 类型 | 实际含义 |
|---|---|---|
| `tool` | string | 工具注册表中的稳定名称。loader 要求它已注册；Agent 不能临时发明工具名。 |
| `args` | object | 调用工具时使用的参数模板。完整的 `{{ path }}` 替换为该 fact 的原值；字符串中的内嵌模板替换为文本。缺失值不会被模型补造，工具参数校验应拒绝不合法输入。 |
| `requires` | string[] | 调用前的守卫。单独的 dotted path 要求值为真；包含比较或布尔运算时按受限表达式求值。任何一项不满足，都不调用工具。 |
| `on_guard_failure` | node ID | 守卫失败的确定性去向，例如先验证身份或补充信息。它不是工具报错路径。当前规范要求每个 `action` 都配置它。 |
| `result_statuses` | string[] | 该工具在此节点允许返回的完整状态枚举。未知状态会安全停止，不能让模型选择下一步。 |
| `transitions` | object | `状态 → 节点 ID` 映射。必须为每个 `result_statuses` 配置一个目标。 |
| `save_result_as` | string | 将结构化工具结果保存到 `facts` 的名称。引擎保存状态、数据和错误，并给事实标记工具来源。 |
| `consume_facts` | string[] | 工具调用完成后删除的临时事实路径，适合 `otp_code` 等敏感输入。 |
| `idempotency_key` | string | 写操作的幂等键模板。退款、取消等操作必须让相同案件和目标重复执行时返回原结果，而不是产生第二次业务操作。 |

`action` 的执行顺序固定为：检查 `requires` → 渲染 `args` 和幂等键 → 调用已注册工具 → 消费临时事实 → 校验返回状态 → 保存工具结果 → 按 `transitions` 跳转。

`on_guard_failure` 与 `transitions.error` 的区别：前者表示“还没有资格调用工具”，后者表示“工具已经调用，但业务或服务返回失败”。

### 4.4 `respond`：向用户说明结果

```json
{
  "type": "respond",
  "template": "退款申请已提交，状态为 {{ refund_submission.status }}。",
  "next": "done"
}
```

| 字段 | 类型 | 实际含义 |
|---|---|---|
| `template` | string | 面向用户的回复模板。模板只能引用 facts；“已提交”“已取消”等成功表述必须对应工具真实结果。 |
| `next` | node ID | 可选。存在时先输出回复，再继续运行；省略时该回复结束本轮并将案件标为完成。 |

### 4.5 `wait`：等待外部事件

```json
{"type": "wait", "event": "human_case_updated", "next": "report_human_result"}
```

| 字段 | 类型 | 实际含义 |
|---|---|---|
| `event` | string | 外部恢复事件的类型，例如人工审核完成。 |
| `next` | node ID | 事件到达后恢复到的节点。当前 CLI 原型只持久化等待状态；生产实现需要事件入口。 |

### 4.6 `end`：流程完成

`end` 没有业务字段。引擎到达它时把案件状态设置为 `completed`。它只表示 workflow 结束，不表示退款一定成功；成功与否必须由前面的结果节点说明。

## 5. `mutable_inputs`：处理用户后续修改

用户在确认前修改出发日期、金额、渠道或账号，是正常流程行为。不能直接覆盖一个字段后继续，因为搜索结果、报价和确认可能都是旧输入产生的。

```json
"mutable_inputs": {
  "travel_date": {
    "type": "string",
    "on_change": "search_flights",
    "priority": 10,
    "invalidates": [
      "flight_search",
      "selected_flight",
      "cabin_quote",
      "booking_confirmation"
    ]
  }
}
```

| 字段 | 实际含义 |
|---|---|
| key | 用户输入字段名，必须被某个 `ask.collect` 收集。 |
| `type` | 该字段允许的数据类型。Harness 在写入前检查，不能让模型把字符串“eligible”写进工具拥有的资格字段。 |
| `enum` | 可选的允许值列表，例如账号关系只能是 `current` 或 `other`。 |
| `on_change` | 该输入被修改后重新计算的入口节点。它应指向最早受影响的步骤。 |
| `priority` | 同一条消息修改多个字段时的重算优先级；数值越小越早。 |
| `invalidates` | 修改后必须删除的派生事实、来源和版本。旧搜索结果、旧报价和旧确认都应列出。 |

### 5.1 字段修改的完整示例

下面的声明表示：`travel_date` 是用户可以再次修改的输入；如果它已经有值且用户提供了新值，工作流必须从 `search_flights` 重新查询，并清除基于旧日期产生的结果。

```json
{
  "mutable_inputs": {
    "travel_date": {
      "type": "string",
      "on_change": "search_flights",
      "priority": 10,
      "invalidates": [
        "flight_search",
        "selected_flight",
        "cabin_quote",
        "booking_confirmation"
      ]
    }
  }
}
```

字段的实际关系是：

```text
travel_date
    ↓
flight_search
    ↓
selected_flight
    ↓
cabin_quote
    ↓
booking_confirmation
```

第一次收集日期时，Harness 只写入用户事实并继续向前执行。如果案件已经查询并选定航班，用户随后说“改成 2026-09-21”，Harness 应产生结构化修改：

```json
{
  "travel_date": "2026-09-21"
}
```

引擎随后会：

1. 校验字段类型，并确认它是声明过的 `mutable_input`。
2. 更新日期，增加该事实的 revision，并记录来源为 `user`。
3. 删除 `invalidates` 列出的事实、来源和 revision。
4. 把 `current_node` 设置为 `search_flights`，清除等待用户状态。
5. 重新查询航班；之后用户需要重新选择航班、舱位和报价，并重新确认。

修改前的案件事实可能是：

```json
{
  "travel_date": "2026-09-20",
  "flight_search": {"date": "2026-09-20", "flights": ["F1", "F2"]},
  "selected_flight": "F1",
  "cabin_quote": {"cabin": "business", "price": 2500},
  "booking_confirmation": true
}
```

修改日期后，旧的搜索结果、选中航班、报价和确认事实都不能继续使用；日期以外仍然有效的用户输入（例如出发地、到达地和舱位偏好）可以保留并作为新查询的参数。

`priority` 只在一条消息修改多个字段时使用。引擎选择数值最小的 `on_change` 入口，从最早受影响的步骤重新执行。`invalidates` 是 workflow 作者明确声明的清理清单；如果某个派生事实可能依赖该输入，就必须列入其中。

引擎还记录 `fact_sources` 和 `fact_revisions`：用户字段来源是 `user`，工具结果来源是 `tool:<name>`。只有用户拥有的 mutable input 可以被用户更正；工具拥有的订单、资格和成功状态不能被覆盖。

### 机票例子

```text
日期 9 月 19 日
  → 查询航班
  → 选择航班 F1
  → 选择商务舱
  → 获取报价
  → 等待确认

用户：改成明天
  → 更新日期并增加 revision
  → 删除旧航班、旧选择、旧报价、旧确认
  → 跳回 search_flights
  → 重新选择航班、舱位、报价并确认
```

如果已经出票，不能继续使用这个“未确认预订”流程修改日期。应根据业务状态路由到独立的改签或退票 workflow。

## 6. 事实、来源与权限

`facts` 是案件上下文，不是模型的自由写入区：

- Agent 可以从用户消息提取当前 `ask.collect` 声明的输入。
- 工具可以写入订单、订阅、资格和操作结果。
- Harness/引擎拒绝模型直接写入可信事实。
- `requires`、分支条件和模板都只读取 facts。
- 敏感值在工具调用后应通过 `consume_facts` 清除，并在审计日志中脱敏。

生产环境还应对持久化的敏感输入做加密或短期保留。当前 CLI 原型使用 SQLite 演示流程语义，不能直接作为真实验证码存储方案。

## 7. 校验分层

写好一个 JSON 后，需要经过三层检查：

1. **JSON Schema**：类型、必填字段、枚举、额外字段、节点结构。
2. **语义 loader**：起点和所有跳转目标存在；工具已注册；每个工具状态都有迁移；表达式安全；mutable input 被 ask 收集且入口存在。
3. **业务服务和工具门禁**：当前账号、订单渠道、退款资格和幂等状态在真实业务服务再次校验。

Schema 通过不等于流程业务正确。比如 Schema 无法知道 Apple 订单不能调用自有退款工具，这个约束必须在 workflow 分支、工具权限和后端服务中同时实现。

## 8. 最小编写流程

1. 为稳定的业务目标创建一个 workflow ID 和版本。
2. 列出用户输入、工具事实和允许修改的 mutable inputs。
3. 先画节点和迁移，再写每个节点字段。
4. 为每个 action 写全 `requires`、`on_guard_failure`、`result_statuses` 和 `transitions`。
5. 为所有写操作配置幂等键。
6. 为会被用户修改的上游输入列出完整 `invalidates` 集合。
7. 运行 Schema 和语义校验，再用失败、超时、重复提交和用户更正场景测试。
