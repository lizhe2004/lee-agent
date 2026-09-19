# Workflow Definition 规范

状态：Draft
规范版本：0.1.0

本文定义一种可移植、可校验、可确定性执行的 Workflow Definition 格式。它面向长期演进，不依赖任何现有代码、存储方案或 Agent 框架。

---

# 第一部分：Definition 语言

## 1. 范围与设计原则

### 1.1 规范目标

Workflow Definition 描述：

- 流程接受哪些输入；
- 流程产生哪些派生结果；
- 有哪些节点以及节点之间如何迁移；
- 节点读取和写入哪些数据；
- 数据之间存在哪些依赖；
- 输入变化后哪些结果失效；
- 哪些业务、安全规则必须额外执行；
- 工具失败、超时和副作用如何处理；
- 如何调用其他 Workflow。

### 1.2 非目标

本文不定义 Skill、LLM 意图识别、多意图案件调度、数据库结构、工具网络协议、UI、话术或任何现有实现的兼容方式。

外部系统可以把用户语言转换成输入修改、确认、取消等事件，但 Workflow Engine 只能执行 Definition 中明确声明的节点、迁移和副作用。

### 1.3 确定性原则

对于相同的 Definition、初始状态和事件序列，Engine 必须产生相同的控制流决策和状态变化。外部工具返回值可以不同，但其可接受状态和后续迁移必须由 Definition 约束。

### 1.4 规范关键词

- MUST：实现必须满足。
- MUST NOT：实现禁止执行。
- SHOULD：除非有明确理由，否则应满足。
- MAY：可选能力。

### 1.5 Definition 与 Runtime 的边界

Definition 是静态、带版本、不可变的流程合同。Runtime State 是某个 Workflow Instance 的当前值、版本和执行进度。

Definition 不保存当前节点、实际用户值、工具调用结果、revision 或等待事件实例。这些属于 Runtime State。本文只在第三部分定义解释 Definition 所需的抽象运行语义。

## 2. 基础语法

### 2.1 标识符

Workflow、input、artifact、node、policy 的 ID 必须以小写字母开头，只包含小写字母、数字和下划线，并在所属命名空间内唯一。显示名称和自然语言文案不得作为 ID。

### 2.2 引用

数据引用必须包含命名空间：

~~~text
inputs.origin
inputs.departure_date
artifacts.flight_search
context.workflow_instance_id
~~~

节点迁移目标直接使用 node ID。合法数据命名空间：

| 命名空间 | 含义 |
|---|---|
| inputs | 调用方、用户或外部事件提供的输入 |
| artifacts | Workflow 执行产生的派生结果 |
| context | Engine 提供的只读执行上下文 |

### 2.3 数据类型

规范内置 string、boolean、integer、number、date、datetime、duration、money、phone、email、enum、object 和 array。复杂对象应通过 schema 引用 JSON Schema 或等价的已注册类型。

### 2.4 表达式

requires、branch condition 和 policy condition 使用受限表达式语言。表达式只能读取已声明引用，不得调用任意代码或产生副作用，并采用 true、false、unknown 三值逻辑。除非字段另有规定，unknown 按条件不满足处理。

### 2.5 模板

模板只能引用节点 inputs 中声明的数据，不得读取未声明状态，也不得调用函数或工具。

### 2.6 版本

Definition 使用 MAJOR.MINOR.PATCH 语义化版本。已启动的 Workflow Instance 必须固定到解析后的准确 Definition 版本。

## 3. Workflow 顶层对象

### 3.1 基本结构

~~~json
{
  "spec_version": "0.1",
  "id": "flight_booking",
  "version": "1.0.0",
  "title": "预订机票",
  "description": "查询航班、选择舱位、确认并创建订单",
  "entry": "collect_trip",
  "inputs": {},
  "artifacts": {},
  "nodes": {},
  "dependencies": [],
  "policies": []
}
~~~

### 3.2 顶层字段

| 字段 | 类型 | 必填 | 含义 |
|---|---|---:|---|
| spec_version | string | 是 | 本文规范的版本 |
| id | identifier | 是 | Workflow 稳定 ID |
| version | semver | 是 | Definition 版本 |
| title | string | 否 | 面向维护者的名称 |
| description | string | 否 | 流程用途说明 |
| entry | node ID | 是 | 新实例入口节点 |
| inputs | object | 是 | 输入声明 |
| artifacts | object | 是 | 派生结果声明 |
| nodes | object | 是 | 节点定义 |
| dependencies | array | 否 | 对自动依赖图的显式补充或覆盖 |
| policies | array | 否 | 业务、安全和风控规则 |

未知顶层字段必须被拒绝，除非规范定义了明确的扩展命名空间。

## 4. 数据声明

### 4.1 Input

Input 是从 Workflow 外部进入流程的数据，来源可以是用户、调用方或可信外部事件。

~~~json
{
  "inputs": {
    "departure_date": {
      "type": "date",
      "required": true,
      "source": ["user"],
      "mutable": "until_irreversible_effect",
      "sensitive": false
    },
    "cabin": {
      "type": "enum",
      "values": ["economy", "business", "first"],
      "required": true,
      "source": ["user"],
      "mutable": "until_irreversible_effect"
    }
  }
}
~~~

#### 4.1.1 Input 字段

| 字段 | 必填 | 含义 |
|---|---:|---|
| type | 是 | 规范化后的数据类型 |
| schema | 复杂类型时 | 类型结构 |
| values | enum 时 | 允许值 |
| required | 是 | Workflow 成功完成前是否必须存在 |
| source | 是 | 允许写入来源：user、caller、event、system |
| mutable | 是 | never、always、until_irreversible_effect |
| default | 否 | 无外部值时的确定性默认值 |
| sensitive | 否 | 是否属于敏感数据 |
| retention | 否 | 建议保留范围：turn、instance、audit、none |

required 不表示 Workflow 启动时必须已有该值。节点可以在真正使用之前收集它。

#### 4.1.2 用户选择也是 Input

用户从工具结果中做出的选择仍然是 Input，例如 inputs.selected_flight_id。但它依赖搜索结果。产生该选择的 ask 节点必须读取 artifacts.flight_search 并输出 inputs.selected_flight_id，因此搜索结果失效时，该选择也会失效。

### 4.2 Artifact

Artifact 是节点产生的派生事实。工具结果、计算结果、验证结果和确认结果都属于 Artifact。

~~~json
{
  "artifacts": {
    "flight_search": {
      "type": "object",
      "schema": "types/FlightSearchResult@1",
      "owner": "tool",
      "validity": {"ttl": "PT60S"},
      "sensitive": false
    },
    "identity_verified": {
      "type": "boolean",
      "owner": "system",
      "validity": {"ttl": "PT10M"},
      "sensitive": true
    }
  }
}
~~~

| 字段 | 必填 | 含义 |
|---|---:|---|
| type | 是 | artifact 值类型 |
| schema | 复杂类型时 | 值结构 |
| owner | 是 | tool、system、workflow |
| validity.ttl | 否 | 最长有效时间 |
| sensitive | 否 | 是否敏感 |
| retention | 否 | 建议保留范围 |

Artifact 的 producer 由 node.outputs 推导，不在 artifact 中重复声明。默认每个 artifact 只有一个 producer。需要多来源合并时，应通过明确的 merge action 产生最终 artifact。

### 4.3 Input 与 Artifact 的边界

- 外部主体提供或选择的值是 Input；
- Workflow 通过工具、计算或验证产生的值是 Artifact；
- 用户不能直接写入 Artifact；
- 工具不能绕过节点 output 合同修改 Input；
- 同一个名称不能同时存在于两个命名空间。

### 4.4 数据有效性

| 状态 | 含义 |
|---|---|
| absent | 尚无值 |
| pending | 正在产生 |
| valid | 当前可使用 |
| stale | 上游版本或 TTL 已变化，需要重算 |
| invalid | 被业务或安全规则撤销 |
| error | 最近一次产生失败 |

只有 valid 数据可以满足节点 inputs 和 requires。

## 5. 流程图声明

### 5.1 Node 公共字段

| 字段 | 含义 |
|---|---|
| type | 节点类型 |
| inputs | 节点会读取的完整数据引用 |
| outputs | 节点被允许写入的数据引用 |
| requires | 执行前必须满足的确定性条件 |
| timeout | 单次节点执行时限 |
| retry | 重试规则 |
| metadata | 不影响运行语义的扩展信息 |

#### 5.1.1 node.inputs

node.inputs 是完整读取声明。工具参数模板、requires、branch condition、response 模板和 output 计算引用的数据都必须出现在 inputs 中。缺少声明属于 Definition 错误，Engine 不得偷偷读取未声明数据。

#### 5.1.2 node.outputs

node.outputs 是写入白名单：

- action 通常写 artifact；
- ask 通常写 user-sourced input；
- wait 可以写 event-sourced input 或 artifact；
- call 写映射后的子 Workflow 结果；
- branch、respond 和 end 通常没有 output。

工具返回但未声明为 output 的字段不得写入 Workflow State。

#### 5.1.3 inputs 与 requires

inputs 回答“节点读取什么”，用于依赖图和数据血缘；requires 回答“什么条件下允许执行”，用于业务门槛。requires 中引用的数据也必须包含在 inputs 中。

### 5.2 ask

ask 暂停流程并等待外部输入。

~~~json
{
  "type": "ask",
  "inputs": ["artifacts.flight_search"],
  "outputs": ["inputs.selected_flight_id"],
  "request": {
    "kind": "selection",
    "prompt": "请选择航班",
    "options_from": "artifacts.flight_search.flights",
    "accepts": ["answer", "modify", "cancel"]
  },
  "on": {
    "answer": "quote_cabin",
    "cancel": "cancelled"
  }
}
~~~

输入修改事件是 Workflow Instance 的标准事件，即使不属于当前问题的普通 answer，也必须按第 14 章处理。

### 5.3 action

action 调用已注册的确定性工具。

~~~json
{
  "type": "action",
  "inputs": [
    "inputs.origin",
    "inputs.destination",
    "inputs.departure_date",
    "inputs.cabin"
  ],
  "outputs": ["artifacts.flight_search"],
  "tool": "flight.search@2",
  "arguments": {
    "origin": "{{ inputs.origin }}",
    "destination": "{{ inputs.destination }}",
    "date": "{{ inputs.departure_date }}",
    "cabin": "{{ inputs.cabin }}"
  },
  "result": {"value": "artifacts.flight_search"},
  "statuses": {
    "success": "select_flight",
    "no_result": "report_no_result",
    "business_error": "report_search_failure",
    "technical_error": "escalate"
  },
  "effect": {"kind": "none"}
}
~~~

工具所有可能状态必须被 statuses 覆盖。未知状态必须安全停止。

### 5.4 branch

branch 按顺序计算条件，第一个 true 分支获胜。default 必填，condition 为 unknown 时不命中。

~~~json
{
  "type": "branch",
  "inputs": ["artifacts.order"],
  "cases": [
    {
      "when": "artifacts.order.channel == 'ios'",
      "next": "guide_apple_refund"
    }
  ],
  "default": "evaluate_refund"
}
~~~

### 5.5 respond

respond 产生结构化响应，并可继续迁移。成功、已退款、已出票等事实性表达必须来自 valid artifact。

### 5.6 wait

wait 等待可信外部事件。事件必须通过类型、来源和 correlation key 校验，并声明 received 与 timeout 路径。

### 5.7 call

call 调用另一个确定性 Workflow。

~~~json
{
  "type": "call",
  "inputs": ["inputs.phone_number"],
  "outputs": ["artifacts.identity_verified"],
  "workflow": {
    "id": "identity_verification",
    "version": "2.1.0"
  },
  "map_inputs": {
    "phone_number": "inputs.phone_number"
  },
  "map_outputs": {
    "verified": "artifacts.identity_verified"
  },
  "on": {
    "completed": "find_order",
    "cancelled": "cancelled",
    "failed": "escalate"
  }
}
~~~

发布时必须把子 Workflow 引用固定到准确版本。父 Workflow 只能读取 map_outputs 声明的结果。

### 5.8 end

end 终止实例并声明 outcome。Workflow outcome 不等于某项业务操作天然成功，业务成功必须由可信 artifact 支撑。

### 5.9 Transition

Transition 是节点定义的一部分，常见形式为 next、on、statuses、cases 和 default。每个目标必须引用当前 Definition 中存在的 node。

## 6. Dependencies

### 6.1 自动依赖图

编译器根据每个节点的 inputs 和 outputs 生成依赖边。默认每个 output 依赖该节点的全部 inputs。

~~~text
inputs.origin ─────────┐
inputs.destination ────┼→ artifacts.flight_search
inputs.departure_date ─┘
~~~

### 6.2 显式 dependencies

显式 dependencies 用于补充或收窄自动推导结果：

~~~json
{
  "dependencies": [
    {
      "target": "artifacts.booking_confirmation",
      "sources": [
        "inputs.departure_date",
        "inputs.selected_flight_id",
        "artifacts.cabin_quote"
      ],
      "mode": "replace"
    },
    {
      "target": "artifacts.refund_eligibility",
      "sources": ["artifacts.risk_assessment"],
      "mode": "extend"
    }
  ]
}
~~~

| 字段 | 含义 |
|---|---|
| target | 被影响的数据 |
| sources | target 的直接上游 |
| mode | extend 追加；replace 替换自动依赖 |
| when | 可选的条件依赖表达式 |

replace 可能造成漏失效，SHOULD 仅用于 output 确实只依赖部分 node.inputs 的情况。

### 6.3 直接依赖与传递依赖

Definition 只声明直接依赖。Engine 必须计算传递闭包。F → B → A 中，F 改变后 B 和 A 都失效，作者不需要维护 invalidates: [B, A]。

### 6.4 条件依赖

条件依赖只在 when 为 true 时建立。Engine 在产生 target 时必须记录本次实际启用的依赖边。

### 6.5 循环

纯数据依赖图必须是有向无环图。循环交互使用控制流循环和新的 revision，不得建立 artifact 自依赖。

## 7. Policies

### 7.1 使用边界

Policy 只表达普通数据血缘无法完整推导的业务、安全或权限规则。例如手机号变化后强制重新发送 OTP，或已经出票后修改日期必须进入改签流程。普通的“输入变化导致依赖结果重算”不得重复写成 policy。

### 7.2 Policy 结构

~~~json
{
  "policies": [
    {
      "id": "phone_changed_reverify",
      "priority": 100,
      "trigger": {
        "type": "input.changed",
        "ref": "inputs.phone_number"
      },
      "when": "artifacts.identity_verified == true",
      "effects": [
        {
          "type": "invalidate",
          "targets": [
            "artifacts.otp_verified",
            "artifacts.identity_verified"
          ]
        },
        {
          "type": "redirect",
          "node": "send_otp"
        }
      ],
      "reason": "identity_scope_changed"
    }
  ]
}
~~~

标准 trigger 包括 input.changed、artifact.changed、artifact.expired、external.event、effect.committed 和 permission.changed。

标准 effect：

| effect | 含义 |
|---|---|
| invalidate | 将目标标为 invalid |
| require_revalidation | 要求指定验证结果重新产生 |
| block | 阻止当前操作并返回原因 |
| redirect | 指定必须进入的处理节点 |

Policy 不得直接产生业务成功结果，也不得把 invalid 数据改回 valid。

### 7.3 优先级与冲突

同一事件触发多个 policy 时，按 priority 从高到低计算；invalidate 和 require_revalidation 取并集；block 优先于 redirect；相同最高优先级的不同 redirect 属于冲突，Engine 必须安全停止。

---

# 第二部分：静态语义

## 8. 名称与引用解析

Loader 必须检查：

- entry 存在；
- 所有 transition 目标存在；
- 所有 input 和 artifact 引用存在；
- node.outputs 的目标已声明；
- call 的子 Workflow 和映射字段存在；
- policy trigger 和 effect 目标存在；
- context 引用属于规范允许的只读字段。

## 9. 类型检查

编译器必须验证：

- 默认值符合 input 类型；
- enum 值在允许集合中；
- 工具参数与工具合同一致；
- 工具结果与 artifact schema 一致；
- 表达式运算符适用于对应类型；
- call 输入输出映射类型兼容；
- end result 类型符合 Workflow 对外合同。

## 10. 图编译

### 10.1 控制流图

控制流图由 entry、next、on、statuses、cases 和 default 构建。

编译器必须检查入口可达性、非终止节点的后继、不可达节点、没有退出条件的循环，以及等待节点的恢复或超时路径。

### 10.2 数据依赖图

数据依赖图由 node.inputs、node.outputs 和显式 dependencies 构建。编译产物至少包括：

~~~text
producer_by_data
consumers_by_data
upstream_dependencies
reverse_dependencies
~~~

### 10.3 Producer 规则

每个 artifact 默认只有一个 producer。每个可由 ask 写入的 input 可以有一个收集节点，并允许外部修改事件更新。

多个节点竞争写同一个 artifact 属于 Definition 错误，除非通过规范化 merge 节点形成单一 producer。

## 11. Definition 合法性

发布前必须满足：

- 所有引用可解析；
- 所有表达式可类型检查；
- 数据依赖图无环；
- artifact producer 唯一；
- 节点只能写 outputs 白名单；
- action statuses 完整；
- branch 有 default；
- retry 不会重复不可幂等副作用；
- irreversible action 声明输入修改后的处理方式；
- policy 不产生循环 redirect；
- call 图不存在不受控递归。

---

# 第三部分：规范性运行语义

## 12. 抽象运行时模型

本章只定义解释 Definition 所需的抽象对象，不规定持久化 JSON 或数据库结构。

### 12.1 Workflow Instance

每个实例至少具有：

~~~text
workflow_id
workflow_version
instance_id
execution_status
active_nodes
input_values
artifact_values
committed_effects
event_log
~~~

### 12.2 Value Revision

每个 input 和 artifact 值都有单调递增的 revision。新值、重新确认和重新验证都会产生新 revision。

### 12.3 Runtime depends_on

节点成功产生 output 时，Engine 必须记录本次实际使用的上游 revision：

~~~json
{
  "artifact": "artifacts.flight_search",
  "revision": 3,
  "depends_on": {
    "inputs.origin": 1,
    "inputs.destination": 1,
    "inputs.departure_date": 4
  }
}
~~~

Definition 中的 dependencies 是静态可能依赖；Runtime depends_on 是本次实际血缘。

## 13. 节点执行

### 13.1 基本循环

~~~text
选择可执行节点
→ 检查 input 状态
→ 计算 requires
→ 执行节点
→ 校验结果
→ 原子提交 outputs、revision、血缘和事件
→ 选择 transition
→ 继续，直到 ask、wait、end 或安全停止
~~~

### 13.2 输入检查

节点的所有 inputs 必须为 valid。存在 absent、pending、stale、invalid 或 error 时，节点不可执行。

### 13.3 requires

requires 为 false 或 unknown 时，节点不得执行。Definition 必须通过显式迁移或上游节点解决缺失门槛，不允许 Engine 猜测。

### 13.4 原子提交

节点结果、output revisions、depends_on、transition 和审计事件必须作为一个逻辑事务提交。失败时不得留下部分 valid output。

### 13.5 暂停与恢复

ask 和 wait 产生等待令牌。恢复事件必须匹配实例、节点、事件类型和 correlation 信息。过期等待令牌不得恢复已被重新执行替代的节点。

## 14. 输入修改与重新计算

### 14.1 修改是标准事件

输入修改不是“当前 ask 的异常答案”，而是 Workflow Instance 可在任何等待点接收的标准事件：

~~~json
{
  "type": "input.change",
  "changes": {
    "inputs.departure_date": "2026-09-20"
  },
  "expected_revisions": {
    "inputs.departure_date": 4
  }
}
~~~

expected_revisions 用于避免并发覆盖。

### 14.2 修改事务

Engine 必须按以下顺序处理：

1. 验证 input 存在；
2. 验证事件来源属于 input.source；
3. 验证 mutable 规则；
4. 规范化并校验新值；
5. 原子比较 expected revision；
6. 写入新值并增加 revision；
7. 计算依赖失效；
8. 执行匹配 policies；
9. 计算重新执行计划；
10. 撤销过期等待令牌并恢复执行。

同一事件中的多个 changes 必须作为一个原子修改集合处理，不能逐个回退流程。

### 14.3 失效传播

对于每个改变的 input：

1. 从 reverse_dependencies 找到直接消费者；
2. 沿依赖图传播到所有传递下游；
3. 普通派生结果标记为 stale；
4. policy 撤销的安全或业务结果标记为 invalid；
5. 依赖旧数据的确认、选择和授权一并失效。

确认必须依赖它所确认的全部业务数据。日期、航班或价格任一变化，旧确认都不能复用。

### 14.4 重新执行边界

Engine 从失效子图中选择最小重算前沿：

- output 已失效；
- node 的上游 inputs 当前 valid；
- 该 node 之前没有另一个必须先重算的失效 producer。

前沿节点按数据依赖拓扑顺序执行。需要用户重新选择时，执行会自然停在对应 ask。

这不是把 current node 简单设置回某个固定节点。重新入口由当前失效子图和可用输入共同计算。

### 14.5 机票修改示例

~~~text
inputs.departure_date
        ↓
artifacts.flight_search
        ↓
inputs.selected_flight_id
        ↓
artifacts.cabin_quote
        ↓
inputs.booking_confirmed
~~~

确认时用户修改日期：

~~~text
departure_date revision 4 → 5
→ flight_search stale
→ selected_flight_id stale
→ cabin_quote stale
→ booking_confirmed invalid
→ 重算前沿为 search_flights
→ 搜索完成后停在 select_flight
→ 用户重新选择、报价和确认
~~~

origin、destination、cabin 等没有被影响的 valid input 保留。

### 14.6 不可逆副作用后的修改

如果修改会影响已提交的 irreversible effect，Engine 不得删除历史结果或假装回退。action 必须声明处理方式：

~~~json
{
  "effect": {
    "kind": "irreversible",
    "idempotency_key": "{{ context.workflow_instance_id }}:create_booking",
    "on_input_change": {
      "mode": "redirect",
      "node": "start_change_booking"
    }
  }
}
~~~

| mode | 含义 |
|---|---|
| reject | 拒绝修改并返回稳定原因 |
| redirect | 进入改签、撤销或补偿节点 |
| compensate | 先执行声明的补偿 action |

已提交副作用及其结果是历史事实，不得因为上游输入改变而被删除或改写。Engine 应保留该 effect 和结果的原始血缘，再执行 reject、redirect 或 compensate。

已经进入终止状态的 Workflow Instance 不再接收 input.change。终止后出现的新修改诉求应由调用方启动新的修改、撤销或补偿 Workflow；该调度方式不属于本文范围。

## 15. 错误、副作用与恢复

### 15.1 错误分类

~~~text
validation_error
guard_failed
business_error
transport_error
timeout
contract_error
policy_conflict
~~~

只有 Definition 明确列出的错误才可自动迁移或重试。

### 15.2 Retry

自动 retry 只适用于声明为可重试的错误。不可幂等写操作不得自动重试。

### 15.3 Effect

action 必须声明 none、reversible 或 irreversible。reversible 或 irreversible action 必须声明 idempotency key。reversible action SHOULD 声明 compensation。

### 15.4 恢复

实例恢复时必须根据已提交事件、幂等键和等待令牌继续。Engine 不得因为进程重启重复执行已提交副作用。

## 16. Policy 执行

Policy 在匹配 trigger 的事件事务中执行：

~~~text
接收事件
→ 计算静态依赖失效
→ 匹配 policy trigger
→ 计算 when
→ 合并 effects
→ 检查冲突
→ 原子提交失效、阻断或 redirect
~~~

依赖失效和 policy effect 不能分两次提交，否则中间状态可能错误地执行节点。

---

# 第四部分：一致性与示例

## 17. 实现一致性要求

### 17.1 Definition Validator

兼容实现必须提供 JSON 结构校验、引用解析、类型检查、控制流检查、数据依赖检查和 policy 冲突检查。

### 17.2 Workflow Compiler

兼容实现必须固定子 Workflow 版本，生成控制流图、数据依赖图、反向依赖索引和 producer/consumer 索引，并输出可审计的编译诊断。

### 17.3 Workflow Engine

兼容实现必须支持确定性节点执行、revision、运行时血缘、原子 input change、级联失效、最小重算前沿、policy 执行、幂等副作用和崩溃恢复。

### 17.4 Tool Adapter

兼容实现必须支持输入输出合同校验、稳定状态枚举、timeout、错误分类、idempotency key 传递、correlation 和审计信息。

## 18. 完整示例

### 18.1 订机票核心 Definition

以下示例重点展示数据依赖、确认和修改后的重算路径：

~~~json
{
  "spec_version": "0.1",
  "id": "flight_booking",
  "version": "1.0.0",
  "entry": "collect_trip",
  "inputs": {
    "origin": {
      "type": "string",
      "required": true,
      "source": ["user"],
      "mutable": "until_irreversible_effect"
    },
    "destination": {
      "type": "string",
      "required": true,
      "source": ["user"],
      "mutable": "until_irreversible_effect"
    },
    "departure_date": {
      "type": "date",
      "required": true,
      "source": ["user"],
      "mutable": "until_irreversible_effect"
    },
    "cabin": {
      "type": "enum",
      "values": ["economy", "business", "first"],
      "required": true,
      "source": ["user"],
      "mutable": "until_irreversible_effect"
    },
    "selected_flight_id": {
      "type": "string",
      "required": true,
      "source": ["user"],
      "mutable": "until_irreversible_effect"
    },
    "booking_confirmed": {
      "type": "boolean",
      "required": true,
      "source": ["user"],
      "mutable": "until_irreversible_effect"
    }
  },
  "artifacts": {
    "flight_search": {
      "type": "object",
      "schema": "types/FlightSearchResult@1",
      "owner": "tool",
      "validity": {"ttl": "PT60S"}
    },
    "cabin_quote": {
      "type": "object",
      "schema": "types/CabinQuote@1",
      "owner": "tool",
      "validity": {"ttl": "PT60S"}
    },
    "booking": {
      "type": "object",
      "schema": "types/Booking@1",
      "owner": "tool"
    }
  },
  "nodes": {
    "collect_trip": {
      "type": "ask",
      "outputs": [
        "inputs.origin",
        "inputs.destination",
        "inputs.departure_date",
        "inputs.cabin"
      ],
      "request": {
        "kind": "form",
        "prompt": "请提供出发地、目的地、日期和舱位",
        "accepts": ["answer", "cancel"]
      },
      "on": {
        "answer": "search_flights",
        "cancel": "cancelled"
      }
    },
    "search_flights": {
      "type": "action",
      "inputs": [
        "inputs.origin",
        "inputs.destination",
        "inputs.departure_date",
        "inputs.cabin"
      ],
      "outputs": ["artifacts.flight_search"],
      "tool": "flight.search@2",
      "arguments": {
        "origin": "{{ inputs.origin }}",
        "destination": "{{ inputs.destination }}",
        "date": "{{ inputs.departure_date }}",
        "cabin": "{{ inputs.cabin }}"
      },
      "result": {"value": "artifacts.flight_search"},
      "statuses": {
        "success": "select_flight",
        "no_result": "no_result",
        "technical_error": "failed"
      },
      "effect": {"kind": "none"}
    },
    "select_flight": {
      "type": "ask",
      "inputs": ["artifacts.flight_search"],
      "outputs": ["inputs.selected_flight_id"],
      "request": {
        "kind": "selection",
        "prompt": "请选择航班",
        "options_from": "artifacts.flight_search.flights",
        "accepts": ["answer", "modify", "cancel"]
      },
      "on": {
        "answer": "quote_cabin",
        "cancel": "cancelled"
      }
    },
    "quote_cabin": {
      "type": "action",
      "inputs": [
        "inputs.selected_flight_id",
        "inputs.cabin"
      ],
      "outputs": ["artifacts.cabin_quote"],
      "tool": "flight.quote@1",
      "arguments": {
        "flight_id": "{{ inputs.selected_flight_id }}",
        "cabin": "{{ inputs.cabin }}"
      },
      "result": {"value": "artifacts.cabin_quote"},
      "statuses": {
        "success": "confirm_booking",
        "sold_out": "search_flights",
        "technical_error": "failed"
      },
      "effect": {"kind": "none"}
    },
    "confirm_booking": {
      "type": "ask",
      "inputs": [
        "inputs.origin",
        "inputs.destination",
        "inputs.departure_date",
        "inputs.cabin",
        "inputs.selected_flight_id",
        "artifacts.cabin_quote"
      ],
      "outputs": ["inputs.booking_confirmed"],
      "request": {
        "kind": "confirmation",
        "prompt": "请确认航班和价格",
        "accepts": ["answer", "modify", "cancel"]
      },
      "on": {
        "answer": "create_booking",
        "cancel": "cancelled"
      }
    },
    "create_booking": {
      "type": "action",
      "inputs": [
        "inputs.selected_flight_id",
        "artifacts.cabin_quote",
        "inputs.booking_confirmed"
      ],
      "outputs": ["artifacts.booking"],
      "requires": ["inputs.booking_confirmed == true"],
      "tool": "booking.create@3",
      "arguments": {
        "flight_id": "{{ inputs.selected_flight_id }}",
        "quote_id": "{{ artifacts.cabin_quote.id }}"
      },
      "result": {"value": "artifacts.booking"},
      "statuses": {
        "success": "completed",
        "price_changed": "quote_cabin",
        "technical_error": "failed"
      },
      "effect": {
        "kind": "irreversible",
        "idempotency_key": "{{ context.workflow_instance_id }}:booking",
        "on_input_change": {
          "mode": "redirect",
          "node": "start_change_booking"
        }
      }
    },
    "start_change_booking": {
      "type": "call",
      "inputs": ["artifacts.booking"],
      "workflow": {
        "id": "flight_booking_change",
        "version": "1.0.0"
      },
      "map_inputs": {
        "booking_id": "artifacts.booking.id"
      },
      "map_outputs": {},
      "on": {
        "completed": "completed",
        "cancelled": "completed",
        "failed": "failed"
      }
    },
    "no_result": {"type": "end", "outcome": "no_result"},
    "cancelled": {"type": "end", "outcome": "cancelled"},
    "failed": {"type": "end", "outcome": "failed"},
    "completed": {
      "type": "end",
      "inputs": ["artifacts.booking"],
      "outcome": "completed",
      "result": {
        "booking_id": "artifacts.booking.id"
      }
    }
  },
  "dependencies": [],
  "policies": []
}
~~~

该 Definition 不需要为 departure_date 手写完整 invalidates 清单。依赖链由 node.inputs 和 node.outputs 自动形成：

~~~text
departure_date
→ flight_search
→ selected_flight_id
→ cabin_quote
→ booking_confirmed
→ booking
~~~

### 18.2 退款流程核心依赖

~~~text
inputs.account_relation
inputs.phone_number
        ↓
artifacts.identity_verified
        ↓
artifacts.order
   ┌────┼───────────┐
   ↓    ↓           ↓
play_history  refund_history  payment_channel
   └────┼───────────┘
        ↓
refund_eligibility
        ↓
refund_confirmation
        ↓
refund_submission
~~~

核心节点：

~~~json
{
  "verify_identity": {
    "type": "call",
    "inputs": ["inputs.phone_number"],
    "outputs": ["artifacts.identity_verified"],
    "workflow": {
      "id": "identity_verification",
      "version": "2.1.0"
    },
    "map_inputs": {
      "phone_number": "inputs.phone_number"
    },
    "map_outputs": {
      "verified": "artifacts.identity_verified"
    },
    "on": {
      "completed": "find_order",
      "cancelled": "cancelled",
      "failed": "escalate"
    }
  },
  "route_payment_channel": {
    "type": "branch",
    "inputs": ["artifacts.order"],
    "cases": [
      {
        "when": "artifacts.order.payment_channel == 'ios'",
        "next": "guide_apple_refund"
      }
    ],
    "default": "evaluate_refund"
  },
  "evaluate_refund": {
    "type": "action",
    "inputs": [
      "artifacts.order",
      "artifacts.play_history",
      "artifacts.refund_history",
      "artifacts.identity_verified"
    ],
    "outputs": ["artifacts.refund_eligibility"],
    "requires": ["artifacts.identity_verified == true"],
    "tool": "refund.evaluate@4",
    "result": {"value": "artifacts.refund_eligibility"},
    "statuses": {
      "eligible": "confirm_refund",
      "ineligible": "report_ineligible",
      "manual_review": "wait_manual_review",
      "technical_error": "escalate"
    },
    "effect": {"kind": "none"}
  }
}
~~~

手机号变化时，普通依赖传播会使身份相关结果 stale；安全 policy 进一步要求重新验证：

~~~json
{
  "id": "phone_changed_reverify",
  "priority": 100,
  "trigger": {
    "type": "input.changed",
    "ref": "inputs.phone_number"
  },
  "effects": [
    {
      "type": "invalidate",
      "targets": [
        "artifacts.identity_verified",
        "artifacts.refund_eligibility"
      ]
    },
    {
      "type": "redirect",
      "node": "verify_identity"
    }
  ],
  "reason": "identity_scope_changed"
}
~~~

---

# 附录 A：字段归属速查

~~~text
Workflow
├── spec_version
├── id
├── version
├── entry
├── inputs
├── artifacts
├── nodes
│   ├── type
│   ├── inputs
│   ├── outputs
│   ├── requires
│   ├── timeout
│   ├── retry
│   └── 节点类型专属字段
├── dependencies
└── policies
~~~

# 附录 B：核心概念对照

| 概念 | 静态或运行时 | 作用 |
|---|---|---|
| input declaration | 静态 | 定义外部输入合同 |
| artifact declaration | 静态 | 定义派生事实合同 |
| node.inputs/outputs | 静态 | 定义节点读写集合并生成基础依赖 |
| dependencies | 静态 | 补充或覆盖自动依赖 |
| policies | 静态 | 定义数据血缘之外的业务和安全规则 |
| revision | 运行时 | 标识具体值版本 |
| depends_on | 运行时 | 记录某次结果实际使用的上游 revision |
| stale | 运行时 | 上游变化导致需要重算 |
| invalid | 运行时 | 业务或安全规则明确撤销 |
