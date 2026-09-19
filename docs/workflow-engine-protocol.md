# Workflow Engine 交互协议

状态：Draft
协议版本：0.2.0

本文定义外部组件与 Workflow Engine 之间的结构化交互协议。协议独立于 HTTP、消息队列、RPC 和进程内调用，可用于 CLI、服务化部署和异步执行环境。

本文依赖 [Workflow Definition 规范](./workflow-definition-spec.md) 中的 Workflow、Slot、Artifact、Node、Policy、revision 和失效语义。

自然语言如何被理解并编译为 Engine Command，见 [Harness Interpretation 协议](./harness-interpretation-protocol.md)。

---

## 1. 范围与原则

### 1.1 协议目标

本协议定义：

- 谁可以向 Engine 提交输入；
- Engine 接受哪些 Command；
- Command 的公共信封和幂等规则；
- Engine 如何返回 Decision；
- Engine 可以产生哪些 Emission；
- Harness、Tool Executor、Timer 和 Event Adapter 的职责边界；
- 并发、顺序、超时、重试和错误语义；
- ask、slot.change、工具调用和外部事件的完整交互。

### 1.2 非目标

本文不定义：

- 用户自然语言如何解析；
- LLM 提示词和模型选择；
- Workflow Definition 字段；
- Runtime State 的数据库结构；
- HTTP URL、消息队列 topic 或 RPC 方法名；
- 工具服务内部实现；
- 前端或客服界面。

### 1.3 核心原则

1. Engine 只接受结构化 Command，不接受原始自然语言。
2. Harness 不能直接修改 Runtime State。
3. Artifact 只能由对应 action、call、wait 或系统事件产生。
4. Engine 的状态变化、Decision 和 Emission 必须原子提交。
5. 外部副作用通过 Emission 请求，并通过后续 Command 返回结果。
6. Command 和 Emission 都必须可幂等处理。
7. 协议不绑定传输方式。

## 2. 参与方与职责

### 2.1 参与方

~~~text
用户
  ↓
Harness
  ↓ Command
Workflow Engine
  ↓ Emission
  ├── Harness
  ├── Tool Executor
  ├── Timer Service
  ├── Event Adapter
  ├── Subworkflow Runner
  └── Audit / Monitoring
~~~

### 2.2 Harness

Harness 负责：

- 将用户消息解释为 interaction.answer、slot.change 或 interaction.cancel；
- 保存并回传 Engine 发出的 interaction_id；
- 将 interaction.requested 和 response.produced 转换成用户可理解的内容；
- 附带真实 actor、channel 和 trace 信息。

Harness 不得：

- 设置 active node；
- 直接写 Artifact；
- 伪造 tool.result；
- 指定 Workflow 跳转目标；
- 计算或覆盖失效范围；
- 绕过 expected_instance_revision；
- 修改 Engine 发出的业务结果。

### 2.3 Tool Executor

Tool Executor 消费 tool.requested，执行注册工具，再向 Engine 提交 tool.result。它负责网络调用、凭证、底层重试边界和工具合同校验。

### 2.4 Timer Service

Timer Service 消费 timer.requested 和 timer.cancelled，在到期后提交 timer.fired。它不决定超时后的 Workflow 路径。

### 2.5 Event Adapter

Event Adapter 将人工审核、支付回调、库存变化等可信外部事件转换为 external.event，并验证事件来源和签名。

### 2.6 Subworkflow Runner

Subworkflow Runner 消费 subworkflow.requested，启动固定版本的子 Workflow，并在子流程终止后提交 subworkflow.result。单进程实现 MAY 将该角色包含在 Engine 内部。

### 2.7 调用权限矩阵

| Command | Harness | Tool Executor | Timer | Event Adapter | Subworkflow Runner | Operator |
|---|---:|---:|---:|---:|---:|---:|
| workflow.start | 是 | 否 | 否 | 可选 | 是 | 是 |
| interaction.answer | 是 | 否 | 否 | 否 | 否 | 否 |
| interaction.cancel | 是 | 否 | 否 | 否 | 否 | 是 |
| slot.change | 是 | 否 | 否 | 可选 | 否 | 可选 |
| tool.result | 否 | 是 | 否 | 否 | 否 | 否 |
| timer.fired | 否 | 否 | 是 | 否 | 否 | 否 |
| external.event | 否 | 否 | 否 | 是 | 否 | 可选 |
| subworkflow.result | 否 | 否 | 否 | 否 | 是 | 否 |
| workflow.cancel | 否 | 否 | 否 | 否 | 可选 | 是 |

实现必须在协议校验之外再次执行身份认证和授权。

## 3. 交互模型

### 3.1 Command

Command 是请求 Engine 修改一个 Workflow Instance 的输入。一个 Command 只能属于一个实例；workflow.start 除外，因为它创建实例。

### 3.2 Decision

Decision 是 Engine 对某个 Command 的直接处理结果，说明 Command 是否被接受、实例 revision 是否变化，以及本次产生了哪些 Emission。

### 3.3 Emission

Emission 是 Engine 原子产生的外部可观察输出。它可以是：

- 需要执行的 Effect，例如 tool.requested；
- 需要展示的 Interaction，例如 interaction.requested；
- 生命周期 Event，例如 workflow.completed；
- 审计 Event，例如 state.invalidated。

### 3.4 逻辑处理函数

协议可以抽象为：

~~~text
handle(definition, state, command)
  → decision
  → new_state
  → emissions[]
~~~

new_state、decision 和 emissions 必须在同一个逻辑事务中提交。

## 4. Command 公共信封

### 4.1 结构

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_01J7Y8F1",
  "type": "slot.change",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "expected_instance_revision": 18,
  "actor": {
    "type": "user",
    "id": "user_123",
    "tenant_id": "tenant_a"
  },
  "trace": {
    "correlation_id": "conv_456",
    "causation_id": "msg_789"
  },
  "occurred_at": "2026-09-19T10:00:00+08:00",
  "payload": {}
}
~~~

### 4.2 公共字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| protocol_version | string | 是 | Engine 协议版本 |
| command_id | string | 是 | 全局唯一幂等键 |
| type | command-type | 是 | Command 类型 |
| workflow_instance_id | string | 除 workflow.start 外 | 目标实例 ID |
| expected_instance_revision | integer | 用户交互和主动修改既有实例时 | 调用方预期的实例 revision |
| actor | object | 是 | 发起主体 |
| trace | object | 否 | 链路追踪信息 |
| occurred_at | datetime | 是 | 事件在来源系统发生的时间 |
| payload | object | 是 | Command 专属负载 |

### 4.3 actor

| 字段 | 必填 | 含义 |
|---|---:|---|
| type | 是 | user、system、tool、timer、event_source、workflow、operator |
| id | 是 | 已认证主体 ID |
| tenant_id | 多租户时 | 数据隔离范围 |
| roles | 否 | 已验证角色摘要；Engine 仍需按策略授权 |

actor 不得携带访问令牌、密码或工具凭证。

Command 的实际发送组件身份必须来自经过认证的传输上下文，例如 mTLS service identity 或已验证的进程内调用者，不能只相信 payload.actor。actor 表示业务上“代表谁执行”；传输身份表示“哪个组件提交了 Command”。Engine 必须同时审计两者。

### 4.4 trace

| 字段 | 含义 |
|---|---|
| correlation_id | 将同一会话或业务请求关联起来 |
| causation_id | 导致本 Command 的上游消息、Emission 或事件 ID |
| trace_id | 分布式追踪 ID |

trace 不参与 Workflow 业务判断。

### 4.5 expected_instance_revision

expected_instance_revision 用于乐观并发控制。它与 Engine 当前实例 revision 不一致时，Command 不得修改状态，Decision 返回 conflict。

interaction.answer、interaction.cancel、slot.change 和 workflow.cancel 必须提供 expected_instance_revision。

tool.result、timer.fired、external.event 和 subworkflow.result MAY 省略 expected_instance_revision，因为异步发送方不一定知道实例的最新 revision；它们必须通过 invocation_id、timer_id、correlation_key 或 call_id 对当前活动等待做 compare-and-set。若同时提供 expected_instance_revision，则 Engine 也必须校验。关联 ID 过期时，即使 revision 匹配也必须拒绝。

### 4.6 Command 幂等

- 同一个 command_id 和相同规范化 payload 重复提交，必须返回 duplicate Decision。
- 同一个 command_id 携带不同 payload，必须返回 COMMAND_ID_REUSED。
- duplicate Decision 必须引用原 Decision，并可返回原 Emissions，但 Emission ID 必须保持不变。
- duplicate 不得再次增加 revision，也不得产生新的 Emission ID。

## 5. Workflow 生命周期 Command

### 5.1 workflow.start

创建一个固定 Definition 版本的 Workflow Instance。

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_start_001",
  "type": "workflow.start",
  "actor": {
    "type": "user",
    "id": "user_123",
    "tenant_id": "tenant_a"
  },
  "occurred_at": "2026-09-19T10:00:00+08:00",
  "payload": {
    "workflow": {
      "id": "flight_booking",
      "version": "1.0.0"
    },
    "start_key": "tenant_a:user_123:flight_booking:req_001",
    "initial_slots": {
      "origin": "北京",
      "destination": "上海"
    },
    "parent": null
  }
}
~~~

| payload 字段 | 必填 | 含义 |
|---|---:|---|
| workflow.id | 是 | Workflow ID |
| workflow.version | 是 | 准确 Definition 版本 |
| start_key | 是 | 防止重复创建实例的业务幂等键 |
| initial_slots | 否 | 初始 Slot 值 |
| parent | 子 Workflow 时 | 父实例、call node 和调用令牌 |

Engine 必须验证 initial_slots 的类型、source 和权限。调用方不得传入 Artifact、active node 或 revision。

### 5.2 workflow.cancel

请求终止整个 Workflow Instance。

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_cancel_001",
  "type": "workflow.cancel",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "expected_instance_revision": 27,
  "actor": {
    "type": "operator",
    "id": "op_42",
    "tenant_id": "tenant_a"
  },
  "occurred_at": "2026-09-19T10:05:00+08:00",
  "payload": {
    "reason": "duplicate_case",
    "mode": "graceful"
  }
}
~~~

| payload 字段 | 必填 | 含义 |
|---|---:|---|
| reason | 是 | 稳定、机器可读的取消原因 |
| mode | 是 | 第一版固定为 graceful |

graceful cancel 必须遵守 Workflow 中的副作用和补偿规则。协议不提供跳过补偿、删除审计记录或强制改写终态的能力。

## 6. Interaction Command

### 6.1 interaction.answer

回答当前 interaction.requested。

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_answer_001",
  "type": "interaction.answer",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "expected_instance_revision": 8,
  "actor": {
    "type": "user",
    "id": "user_123",
    "tenant_id": "tenant_a"
  },
  "occurred_at": "2026-09-19T10:01:00+08:00",
  "payload": {
    "interaction_id": "int_abc",
    "answers": {
      "slots.selected_flight_id": "CA123"
    }
  }
}
~~~

| payload 字段 | 必填 | 含义 |
|---|---:|---|
| interaction_id | 是 | `interaction.requested` 发出的本次交互唯一 ID |
| answers | 是 | Slot 引用到规范化值的映射 |

Engine 必须验证：

- interaction_id 当前有效；
- answers 只包含 ask.request.fields；
- Slot source 允许当前 actor；
- 值符合 Slot 类型；
- 选项仍属于当前 valid options_from；
- interaction_id 未被 Slot 修改或重算撤销。

### 6.2 interaction.cancel

取消当前 ask 交互，并按 ask.on.cancel 迁移。

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_interaction_cancel_001",
  "type": "interaction.cancel",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "expected_instance_revision": 8,
  "actor": {
    "type": "user",
    "id": "user_123",
    "tenant_id": "tenant_a"
  },
  "occurred_at": "2026-09-19T10:01:00+08:00",
  "payload": {
    "interaction_id": "int_abc",
    "reason": "user_cancelled"
  }
}
~~~

interaction.cancel 只处理当前交互。取消整个实例使用 workflow.cancel。

## 7. Slot 修改 Command

### 7.1 slot.change

slot.change 在实例尚未终止时修改一个或多个既有 Slot。它不表示跳转到某个节点；Engine 根据依赖图、Policy 和重算前沿决定后续执行。

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_slot_change_001",
  "type": "slot.change",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "expected_instance_revision": 18,
  "actor": {
    "type": "user",
    "id": "user_123",
    "tenant_id": "tenant_a"
  },
  "trace": {
    "correlation_id": "conv_456",
    "causation_id": "msg_789"
  },
  "occurred_at": "2026-09-19T10:03:00+08:00",
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
~~~

| payload 字段 | 必填 | 含义 |
|---|---:|---|
| changes | 是 | Slot 引用到新值的映射，至少一项 |
| expected_slot_revisions | 是 | 每个被修改 Slot 的当前 revision |
| reason | 是 | 稳定修改原因 |

Engine 必须将同一个 slot.change 中的所有 changes 作为原子集合处理。任一修改不合法时，整个 Command 被拒绝。

Harness 不提交 invalidates、restart_at 或 target_node。它们由 Definition 和 Engine 计算。

### 7.2 slot.change 结果

成功处理后，Decision 可以包含摘要：

~~~json
{
  "change_summary": {
    "changed": ["slots.departure_date"],
    "stale": [
      "artifacts.flight_search",
      "slots.selected_flight_id",
      "artifacts.cabin_quote"
    ],
    "invalid": ["slots.booking_confirmed"],
    "recompute_frontier": ["search_flights"]
  }
}
~~~

该摘要用于可观察性，不允许调用方覆盖。

## 8. Tool Command

### 8.1 tool.result

Tool Executor 使用 tool.result 返回 tool.requested 的执行结果。

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_tool_result_001",
  "type": "tool.result",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "expected_instance_revision": 10,
  "actor": {
    "type": "tool",
    "id": "flight_search_executor",
    "tenant_id": "tenant_a"
  },
  "occurred_at": "2026-09-19T10:01:10+08:00",
  "payload": {
    "invocation_id": "inv_123",
    "attempt": 1,
    "status": "success",
    "result": {
      "flights": [
        {
          "id": "CA123",
          "price": 2100
        }
      ]
    },
    "error": null
  }
}
~~~

| payload 字段 | 必填 | 含义 |
|---|---:|---|
| invocation_id | 是 | tool.requested 生成的调用 ID |
| attempt | 是 | 对应的执行尝试序号 |
| status | 是 | 工具合同声明的稳定状态 |
| result | success 或业务状态需要时 | 工具结构化结果 |
| error | 技术失败时 | 规范化错误 |

Engine 必须验证 invocation_id、tool identity、attempt、等待状态和结果 schema。已撤销或被重算替代的 invocation 返回 STALE_INVOCATION，不能写入 Artifact。

Tool Executor 不得提交 transition、Artifact 名称或下一节点。

## 9. Timer、外部事件与子 Workflow Command

### 9.1 timer.fired

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_timer_001",
  "type": "timer.fired",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "expected_instance_revision": 12,
  "actor": {
    "type": "timer",
    "id": "timer_service",
    "tenant_id": "tenant_a"
  },
  "occurred_at": "2026-09-21T10:00:00+08:00",
  "payload": {
    "timer_id": "timer_123",
    "scheduled_for": "2026-09-21T10:00:00+08:00"
  }
}
~~~

Timer Service 不得决定 timeout transition。Engine 根据 timer_id 对应的节点和 Definition 选择路径。

### 9.2 external.event

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_event_001",
  "type": "external.event",
  "workflow_instance_id": "wfi_refund_001",
  "expected_instance_revision": 23,
  "actor": {
    "type": "event_source",
    "id": "refund_review_service",
    "tenant_id": "tenant_a"
  },
  "occurred_at": "2026-09-20T09:00:00+08:00",
  "payload": {
    "event_id": "review_evt_123",
    "event_type": "refund.manual_review_completed",
    "correlation_key": "wfi_refund_001",
    "data": {
      "decision": "approved",
      "review_id": "review_42"
    }
  }
}
~~~

| payload 字段 | 必填 | 含义 |
|---|---:|---|
| event_id | 是 | 来源系统事件幂等键 |
| event_type | 是 | 稳定事件类型 |
| correlation_key | 是 | 对应 wait node 的关联值 |
| data | 是 | 通过事件合同校验的结构化数据 |

来源签名验证应在 Event Adapter 完成，Engine 仍须验证 actor、event_type、correlation_key 和 payload schema。

### 9.3 subworkflow.result

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_child_result_001",
  "type": "subworkflow.result",
  "workflow_instance_id": "wfi_parent_001",
  "expected_instance_revision": 14,
  "actor": {
    "type": "workflow",
    "id": "wfi_child_001",
    "tenant_id": "tenant_a"
  },
  "occurred_at": "2026-09-19T10:04:00+08:00",
  "payload": {
    "call_id": "call_identity_001",
    "child_instance_id": "wfi_child_001",
    "outcome": "completed",
    "result": {
      "verified": true
    }
  }
}
~~~

父 Engine 只能读取 call node 的 map_outputs 声明的字段。子 Workflow 的内部 Slots、Artifacts 和节点状态不得泄露给父流程。

## 10. Decision

### 10.1 公共结构

~~~json
{
  "protocol_version": "0.2",
  "command_id": "cmd_slot_change_001",
  "status": "accepted",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "previous_instance_revision": 18,
  "current_instance_revision": 19,
  "execution_status": "waiting",
  "outcome": null,
  "change_summary": null,
  "emissions": [],
  "error": null
}
~~~

| 字段 | 必填 | 含义 |
|---|---:|---|
| protocol_version | 是 | 协议版本 |
| command_id | 是 | 对应 Command |
| status | 是 | accepted、rejected、conflict、duplicate、failed |
| workflow_instance_id | start 成功后或既有实例时 | 实例 ID |
| previous_instance_revision | 既有实例时 | 处理前 revision |
| current_instance_revision | 有实例时 | 处理后 revision |
| execution_status | 有实例时 | running、waiting、completed、cancelled、failed |
| outcome | 终止时 | Definition end.outcome |
| change_summary | slot.change 时可选 | 失效和重算摘要 |
| emissions | 是 | 本次原子产生的 Emission |
| error | 非 accepted 时 | 规范化错误 |

### 10.2 status

| status | 含义 | 是否改变实例 |
|---|---|---:|
| accepted | Command 已处理 | 可能 |
| rejected | Command 合法但不符合当前业务或状态约束 | 否 |
| conflict | expected_instance_revision 不匹配 | 否 |
| duplicate | command_id 已处理；返回原 revision 和原 Emission ID | 否 |
| failed | Engine 在提交前发生不可恢复错误 | 否 |

accepted 不代表业务成功，只代表 Command 已被 Engine 接受并确定性处理。

## 11. Emission 公共信封

### 11.1 结构

~~~json
{
  "protocol_version": "0.2",
  "emission_id": "em_01J7Y900",
  "type": "interaction.requested",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "instance_revision": 19,
  "sequence": 31,
  "caused_by_command_id": "cmd_slot_change_001",
  "created_at": "2026-09-19T10:03:00+08:00",
  "payload": {
    "interaction_id": "int_01J7Y901",
    "node_id": "collect_trip",
    "request": {
      "kind": "text",
      "prompt": "请提供出发信息",
      "fields": ["slots.origin"],
      "options": []
    },
    "accepted_commands": [
      "interaction.answer",
      "interaction.cancel",
      "slot.change"
    ]
  }
}
~~~

### 11.2 公共字段

| 字段 | 必填 | 含义 |
|---|---:|---|
| protocol_version | 是 | 协议版本 |
| emission_id | 是 | 全局唯一 Emission ID |
| type | 是 | Emission 类型 |
| workflow_instance_id | 是 | 来源实例 |
| instance_revision | 是 | 产生该 Emission 的实例 revision |
| sequence | 是 | 实例内单调递增序号 |
| caused_by_command_id | 是 | 直接触发本 Emission 的 Command |
| created_at | 是 | Engine 提交时间 |
| payload | 是 | 类型专属负载 |

消费者必须按 emission_id 幂等处理。sequence 用于检测实例内遗漏和乱序，不用于跨实例排序。

## 12. Interaction Emission

### 12.1 interaction.requested

~~~json
{
  "protocol_version": "0.2",
  "emission_id": "em_interaction_001",
  "type": "interaction.requested",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "instance_revision": 19,
  "sequence": 31,
  "caused_by_command_id": "cmd_slot_change_001",
  "created_at": "2026-09-19T10:03:00+08:00",
  "payload": {
    "interaction_id": "int_select_002",
    "node_id": "select_flight",
    "request": {
      "kind": "selection",
      "prompt": "请选择航班",
      "fields": ["slots.selected_flight_id"],
      "options": [
        {
          "value": "CA123",
          "label": "CA123 10:00 起飞"
        }
      ]
    },
    "accepted_commands": [
      "interaction.answer",
      "interaction.cancel",
      "slot.change"
    ]
  }
}
~~~

| payload 字段 | 含义 |
|---|---|
| interaction_id | 本次交互的唯一 ID；重新发起 ask 时必须生成新值 |
| node_id | 当前 ask node |
| request | 已根据 valid State 解析的请求 |
| request.kind | form、selection、confirmation、text |
| request.prompt | 展示内容 |
| request.fields | 允许 interaction.answer 写入的 Slots |
| request.options | selection 的当前有效选项 |
| accepted_commands | 当前状态允许的交互 Command |

Harness 可以调整渠道展示形式，但不得改变 fields、options.value、accepted_commands 或业务含义。

`interaction_id` 的生命周期规则：

- 每次产生 `interaction.requested` 都必须生成新的 ID，包括同一 ask 节点重新执行；
- ID 在回答、取消、上游修改导致的失效或实例终止后不再有效；
- Engine 必须拒绝引用已关闭或已替代 ID 的 Command；
- 使用同一 `command_id` 重试已经成功处理的 Command 时，仍按 Command 幂等规则返回原 Decision；
- ID 用于精确关联一次交互，不是身份认证凭证；
- Harness 保存真实 ID，但不把它发送给语言模型。

### 12.2 response.produced

~~~json
{
  "protocol_version": "0.2",
  "emission_id": "em_response_001",
  "type": "response.produced",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "instance_revision": 20,
  "sequence": 32,
  "caused_by_command_id": "cmd_answer_002",
  "created_at": "2026-09-19T10:04:00+08:00",
  "payload": {
    "node_id": "report_no_result",
    "code": "FLIGHT_NO_RESULT",
    "message": "当前条件下没有可用航班。",
    "data": {}
  }
}
~~~

Harness 可以本地化 message，但不得把失败结果改写为成功，也不得修改 code 和 data 的业务含义。

## 13. Effect Emission

### 13.1 tool.requested

~~~json
{
  "protocol_version": "0.2",
  "emission_id": "em_tool_001",
  "type": "tool.requested",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "instance_revision": 10,
  "sequence": 18,
  "caused_by_command_id": "cmd_answer_001",
  "created_at": "2026-09-19T10:01:05+08:00",
  "payload": {
    "invocation_id": "inv_123",
    "node_id": "search_flights",
    "tool": "flight.search@2",
    "arguments": {
      "origin": "北京",
      "destination": "上海",
      "date": "2026-09-20",
      "cabin": "business"
    },
    "attempt": 1,
    "timeout": "PT10S",
    "idempotency_key": null,
    "allowed_statuses": [
      "success",
      "no_result",
      "business_error",
      "technical_error"
    ]
  }
}
~~~

| payload 字段 | 含义 |
|---|---|
| invocation_id | 本次逻辑工具调用 ID |
| node_id | 来源 action node |
| tool | 固定版本的工具合同 |
| arguments | 已完成模板渲染和类型校验的参数 |
| attempt | 尝试序号 |
| timeout | 本次执行时限 |
| idempotency_key | 副作用工具的幂等键 |
| allowed_statuses | Definition 允许返回的状态 |

Tool Executor 不得修改 arguments。需要重试时，由 Engine 根据 retry 规则产生新的 tool.requested；Tool Executor 的网络层瞬时重试不得突破 timeout 和幂等边界。

### 13.2 timer.requested

~~~json
{
  "protocol_version": "0.2",
  "emission_id": "em_timer_001",
  "type": "timer.requested",
  "workflow_instance_id": "wfi_refund_001",
  "instance_revision": 23,
  "sequence": 40,
  "caused_by_command_id": "cmd_review_start_001",
  "created_at": "2026-09-19T10:00:00+08:00",
  "payload": {
    "timer_id": "timer_review_timeout_001",
    "purpose": "node_timeout",
    "due_at": "2026-09-21T10:00:00+08:00",
    "node_id": "wait_manual_review"
  }
}
~~~

### 13.3 timer.cancelled

当等待节点因 slot.change、取消或其他事件提前失效时，Engine 产生 timer.cancelled。Timer Service 必须幂等撤销；即使撤销与触发并发，Engine 仍通过 timer_id 和实例状态拒绝过期 timer.fired。

### 13.4 subworkflow.requested

~~~json
{
  "protocol_version": "0.2",
  "emission_id": "em_child_001",
  "type": "subworkflow.requested",
  "workflow_instance_id": "wfi_parent_001",
  "instance_revision": 14,
  "sequence": 22,
  "caused_by_command_id": "cmd_answer_003",
  "created_at": "2026-09-19T10:03:00+08:00",
  "payload": {
    "call_id": "call_identity_001",
    "node_id": "verify_identity",
    "workflow": {
      "id": "identity_verification",
      "version": "2.1.0"
    },
    "slots": {
      "phone_number": "13800000000"
    }
  }
}
~~~

Subworkflow Runner 必须使用 call_id 作为父子调用幂等键。

## 14. 生命周期与审计 Emission

### 14.1 workflow.waiting

表示实例等待用户、工具、Timer、外部事件或子 Workflow。payload 至少包含 waiting_for、node_id 和对应关联 ID。

### 14.2 workflow.completed

~~~json
{
  "protocol_version": "0.2",
  "emission_id": "em_completed_001",
  "type": "workflow.completed",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "instance_revision": 30,
  "sequence": 50,
  "caused_by_command_id": "cmd_tool_result_009",
  "created_at": "2026-09-19T10:10:00+08:00",
  "payload": {
    "outcome": "completed",
    "result": {
      "booking_id": "booking_123"
    }
  }
}
~~~

### 14.3 workflow.failed

表示实例进入终止失败状态。payload 包含规范化 error 和最后 node_id，但不得泄露内部堆栈、凭证或敏感 Slot。

### 14.4 workflow.cancelled

表示 workflow.cancel 或 Definition 路径使实例终止取消。payload 包含稳定 reason 和已执行补偿摘要。

### 14.5 human_action.requested

表示需要人工处理。payload 包含稳定任务类型、可展示上下文、允许的结果事件合同和 correlation key。敏感信息必须按接收方权限裁剪。

### 14.6 state.invalidated

~~~json
{
  "protocol_version": "0.2",
  "emission_id": "em_invalidated_001",
  "type": "state.invalidated",
  "workflow_instance_id": "wfi_01J7Y7ZZ",
  "instance_revision": 19,
  "sequence": 30,
  "caused_by_command_id": "cmd_slot_change_001",
  "created_at": "2026-09-19T10:03:00+08:00",
  "payload": {
    "cause": {
      "type": "slot.changed",
      "refs": ["slots.departure_date"]
    },
    "stale": [
      "artifacts.flight_search",
      "slots.selected_flight_id",
      "artifacts.cabin_quote"
    ],
    "invalid": ["slots.booking_confirmed"],
    "policies": []
  }
}
~~~

state.invalidated 用于审计和调试。消费者不得通过它直接修改 Engine State。

## 15. 提交、投递与顺序

### 15.1 原子 Outbox

Engine 必须在一个逻辑事务中提交：

~~~text
Runtime State 新 revision
Command 处理记录
Decision
Emissions / Outbox
~~~

不得先修改状态再尝试生成 Emission，也不得先发送 Effect 再提交状态。

### 15.2 投递语义

推荐采用至少一次投递：

- Engine 保证已提交 Emission 最终可重新投递；
- 消费者按 emission_id 去重；
- Engine 按 command_id 去重；
- Tool Executor 还按 invocation_id 和 idempotency_key 去重；
- Timer 按 timer_id 去重。

协议不宣称跨网络 exactly-once。

### 15.3 实例内顺序

同一 Workflow Instance 的 Command 必须串行提交。实现可以并发接收，但最终只能有一个 Command 成功更新某个 revision。

用户回答、异步工具结果、Timer 和外部事件可能乱序到达。Engine 必须分别依靠 `interaction_id`、`invocation_id`、`timer_id`、correlation key 和可用的 instance revision 判定是否仍然有效。

### 15.4 Emission 拉取与恢复

传输适配器必须支持从某个 sequence 之后重新读取 Emission。Harness 重连时应恢复尚未完成的 interaction.requested，而不是重新创建 ask。

## 16. 查询接口

查询不属于 Command，不得改变 Runtime State。实现 SHOULD 提供以下逻辑查询：

| Query | 用途 |
|---|---|
| instance.summary | 返回状态、revision、outcome 和等待类型 |
| instance.pending_interaction | Harness 恢复当前 interaction.requested |
| instance.emissions | 按 sequence 增量读取 Emission |
| instance.audit | 授权运维查看节点、失效和副作用记录 |

查询结果必须按 actor 权限过滤。Harness 默认不应获得完整敏感 State。

## 17. 错误模型

### 17.1 Error 结构

~~~json
{
  "code": "REVISION_CONFLICT",
  "category": "conflict",
  "message": "Workflow instance revision does not match.",
  "retryable": true,
  "details": {
    "expected_instance_revision": 18,
    "current_instance_revision": 19
  }
}
~~~

| 字段 | 含义 |
|---|---|
| code | 稳定机器错误码 |
| category | validation、authorization、conflict、state、contract、internal |
| message | 不含敏感数据的可读说明 |
| retryable | 使用新条件重试是否可能成功 |
| details | 经过安全过滤的结构化上下文 |

### 17.2 标准错误码

| code | Decision status | 含义 |
|---|---|---|
| INVALID_COMMAND | rejected | Command 结构不合法 |
| UNSUPPORTED_PROTOCOL_VERSION | rejected | 协议版本不支持 |
| COMMAND_ID_REUSED | rejected | 相同 command_id 使用不同 payload |
| WORKFLOW_NOT_FOUND | rejected | Workflow Definition 不存在 |
| WORKFLOW_VERSION_NOT_FOUND | rejected | 准确版本不存在 |
| INSTANCE_NOT_FOUND | rejected | 实例不存在或不可见 |
| INSTANCE_TERMINAL | rejected | 实例已经终止 |
| REVISION_CONFLICT | conflict | expected_instance_revision 不匹配 |
| UNAUTHORIZED_COMMAND | rejected | actor 无权发送该 Command |
| INVALID_INTERACTION_ID | rejected | interaction_id 不存在或已过期 |
| INVALID_SLOT | rejected | Slot 不存在或不能修改 |
| SLOT_REVISION_CONFLICT | conflict | Slot revision 不匹配 |
| SLOT_VALUE_INVALID | rejected | Slot 值不符合类型或约束 |
| STALE_INVOCATION | rejected | 工具调用已被撤销或替代 |
| INVALID_TIMER | rejected | Timer 不匹配当前等待 |
| INVALID_EXTERNAL_EVENT | rejected | 外部事件合同或关联信息错误 |
| TOOL_CONTRACT_ERROR | rejected | 工具状态或结果不符合合同 |
| POLICY_BLOCKED | rejected | Policy 明确阻止操作 |
| POLICY_CONFLICT | failed | 多个 Policy effect 无法确定性合并 |
| ENGINE_INTERNAL_ERROR | failed | Engine 在提交前内部失败 |

### 17.3 重试规则

- validation 和 authorization 错误不得原样重试；
- conflict 应重新读取当前 revision 后由调用方决定；
- duplicate 使用原 Decision 的 revision、outcome 和 Emission ID，不重新执行；
- ENGINE_INTERNAL_ERROR 只有在 command_id 不变时才可安全重试；
- Tool、Timer 和外部事件不得通过更换 ID 绕过 stale 检查。

## 18. 安全与数据保护

### 18.1 信任边界

Harness 是非可信业务输入适配器。即使 Harness 使用 LLM，Engine 仍必须验证所有 Slot、revision、interaction_id 和权限。Engine 必须从认证传输上下文识别发送组件，再校验其是否可以代表 payload.actor。

Tool Executor、Timer 和 Event Adapter 是受认证服务，但其 payload 仍必须通过合同校验。

### 18.2 字段写入权限

- Harness 只能写 Definition 中 source 允许 user 或 caller 的 Slot；
- Event Adapter 只能写 source 允许 event 的 Slot 或 wait outputs；
- Tool Executor 只能返回当前 invocation 的工具结果；
- Timer 只能提交已签发 timer_id；
- 子 Workflow 只能返回 map_outputs 允许的结果；
- Operator 不能直接写 Artifact 或 active node。

### 18.3 敏感数据

- Command、Decision 和 Emission 日志必须按字段敏感级别脱敏；
- interaction.requested 不得返回 Harness 无权查看的 Artifact；
- Error details 不得包含 OTP、访问令牌、完整手机号或支付凭证；
- Tool credentials 不得进入协议 payload；
- audit 查询必须独立授权。

### 18.4 防重放

实现必须校验 command_id、event_id、interaction_id、invocation_id、timer_id、时间窗口和 actor。跨租户复用任何关联 ID 必须被拒绝。

## 19. 协议版本与兼容性

### 19.1 protocol_version

protocol_version 控制信封和字段语义，不等于 Workflow Definition 的 spec_version。

### 19.2 兼容规则

- 增加可选字段属于向后兼容；
- 增加消费者必须处理的新状态或新必填字段属于不兼容；
- 删除或改变字段语义属于不兼容；
- 未识别的 Command type 必须拒绝；
- 未识别的 Emission type 不得静默确认，消费者必须告警或进入死信处理。

## 20. 完整交互时序

### 20.1 启动并等待用户

~~~text
Harness
  → workflow.start
Engine
  → Decision accepted, revision 1
  → interaction.requested(interaction_id=int_trip)
Harness
  → 向用户询问出发地、目的地、日期和舱位
~~~

### 20.2 回答后调用工具

~~~text
Harness
  → interaction.answer(int_trip, slots...)
Engine
  → Decision accepted, revision 2
  → tool.requested(invocation_id=inv_search)
Tool Executor
  → tool.result(inv_search, success, flights)
Engine
  → Decision accepted, revision 3
  → interaction.requested(interaction_id=int_select)
~~~

### 20.3 确认时修改日期

~~~text
当前状态：
  node = confirm_booking
  revision = 18
  interaction_id = int_confirm

Harness
  → slot.change(
      expected_instance_revision=18,
      departure_date=2026-09-20
    )

Engine 原子处理：
  departure_date revision 增加
  flight_search stale
  selected_flight_id stale
  cabin_quote stale
  booking_confirmed invalid
  int_confirm 撤销
  recompute_frontier = search_flights

Engine
  → Decision accepted, revision 19
  → state.invalidated
  → tool.requested(invocation_id=inv_search_2)

Tool Executor
  → tool.result(inv_search_2, success, new_flights)

Engine
  → interaction.requested(
      node=select_flight,
      interaction_id=int_select_2
    )
~~~

如果旧 int_confirm 随后提交 interaction.answer，Engine 必须返回 INVALID_INTERACTION_ID。

### 20.4 异步人工审核

~~~text
Engine
  → human_action.requested(correlation_key=review_42)
  → timer.requested(timer_review_timeout)

人工审核系统完成
  → Event Adapter
  → external.event(
      event_type=refund.manual_review_completed,
      correlation_key=review_42
    )

Engine 原子处理：
  写入审核 Artifact
  关闭人工审核等待状态
  产生 timer.cancelled
  继续后续节点
~~~

### 20.5 并发修改

~~~text
Harness A 读取 revision 20
Harness B 读取 revision 20

A → slot.change(expected_instance_revision=20)
Engine → accepted, current_instance_revision=21

B → interaction.answer(expected_instance_revision=20)
Engine → conflict, REVISION_CONFLICT
~~~

B 必须重新读取 pending interaction 或最新 Emission，不能自动把旧回答套用到 revision 21。

---

## 附录 A：Command 速查

| Command | 核心关联字段 | 主要发送方 |
|---|---|---|
| workflow.start | start_key | Harness、业务系统、Subworkflow Runner |
| interaction.answer | interaction_id | Harness |
| interaction.cancel | interaction_id | Harness |
| slot.change | expected_slot_revisions | Harness、可信业务系统 |
| tool.result | invocation_id | Tool Executor |
| timer.fired | timer_id | Timer Service |
| external.event | event_id、correlation_key | Event Adapter |
| subworkflow.result | call_id、child_instance_id | Subworkflow Runner |
| workflow.cancel | reason | Operator、父 Workflow |

## 附录 B：Emission 速查

| Emission | 主要消费者 |
|---|---|
| interaction.requested | Harness |
| response.produced | Harness |
| tool.requested | Tool Executor |
| timer.requested | Timer Service |
| timer.cancelled | Timer Service |
| subworkflow.requested | Subworkflow Runner |
| workflow.waiting | 监控、调用方 |
| workflow.completed | 调用方、父 Workflow |
| workflow.failed | 调用方、监控 |
| workflow.cancelled | 调用方、父 Workflow |
| human_action.requested | 人工系统 |
| state.invalidated | 审计、监控 |
