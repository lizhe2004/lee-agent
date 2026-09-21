# 客服 Agent 总体设计

状态：Draft 0.2

## 1. 项目目标

本项目要构建一个能够处理复杂客诉业务的智能客服 Agent。用户使用自然语言描述问题，系统按照可审计、可恢复、可重算的业务流程处理案件。

第一阶段覆盖命令行对话，验证以下能力：

- 退款、取消自动续费和机票预订等流程；
- 身份认证、OTP、权限和不可逆操作确认；
- 用户修改已经提供的信息后，自动失效旧结果并重新计算；
- 一次消息提供多个字段；
- 一次消息包含多个业务目标；
- 用户给出多个候选值、无法确定值或拒绝回答；
- 工具调用、幂等、副作用和审计。

本项目不是一个允许大模型自由跳转和执行工具的聊天机器人。模型负责理解自然语言；确定性组件负责校验、状态变化和业务执行。

## 2. 要解决的根本问题

### 2.1 自然语言和确定性业务规则之间的边界

用户说的是自然语言，业务系统需要的是经过类型、权限、身份和版本校验的结构化输入。模型可以提出候选，但不能直接授予权限、确认资格或执行副作用。

### 2.2 流程状态会变化

用户可能在确认阶段说“改成明天”，或者修改手机号后要求重新认证。系统不能只覆盖当前节点，而要根据数据依赖使旧航班、报价、确认、认证等派生结果失效，并重新计算最早需要执行的步骤。

### 2.3 用户输入不一定是一个确定值

用户可能说：

```text
明天后天都行
小米粥或者米饭吧，我记不得了
```

系统必须保留候选及其关系，不能擅自选第一个值。是否允许集合、是否由系统代选、是否必须澄清，由 Workflow 的值策略决定。

### 2.4 多个业务目标可以同时出现

用户可能在退款流程中又要求取消自动续费。模型只报告两个业务目标，Router 根据案件状态和调度策略决定继续、恢复、新建还是并行；模型不能判断哪个是“新流程”。

## 3. 核心运行模型

```text
Case
├── active_workflows        活动 Workflow Instance
├── committed_slots         已被流程接受的确定值
├── proposals               尚未解析的用户提议和候选值
├── artifacts               工具或节点产生的派生结果
├── pending_interactions    当前等待用户处理的问题
├── effects                 已提交的外部副作用及结果
├── revisions               并发控制版本
└── audit_events            不可变审计事件
```

### 3.1 Case

一个客服案件。Case 可以同时包含多个业务目标和多个 Workflow Instance，但不能直接替代 Workflow Instance。

### 3.2 Workflow Definition

带版本的静态流程合同，定义：

- Slot 和 Artifact；
- 节点、输入、输出和迁移；
- 数据依赖和特殊 Policy；
- ask 的提问形式和允许事件；
- 工具、效果和失败处理；
- Slot 变化后的失效和重算规则。

Definition 不保存用户数据、当前节点、工具结果或 revision。

### 3.3 Workflow Instance

某个 Case 按一个准确 Definition 版本运行出来的实例，保存当前节点、等待状态、已确认 Slot、候选提议、Artifact、Effect 和 revision。

### 3.4 Proposal

Proposal 是从用户消息中提取出来、尚未被 Workflow 接受的语义提议。它可以包含：

- 一个候选值；
- 多个候选值以及 `any_of`、`all_of` 或 `exactly_one` 关系；
- 用户是否明确选择；
- 用户是否允许系统代选；
- 用户无法回答或表达歧义的信息。

Proposal 不是 Slot，也不是 Engine Command。

### 3.5 Slot

Slot 是流程接受的业务变量。Slot 可以是单值、集合或结构化对象，但具体类型、基数、来源和可修改性必须在 Definition 中声明。

只有通过 Workflow Policy 解析的 Proposal 才能写入 committed Slot。

### 3.6 Artifact

Artifact 是根据 Slot、其他 Artifact 或工具结果计算出的派生事实，例如航班列表、身份认证结果、退款资格和报价。用户不能直接写入 Artifact。

### 3.7 Effect

Effect 是影响外部世界的操作，例如退款、取消订阅、创建订单和发送短信。Effect 必须有明确的前置条件、幂等键、结果状态和审计记录。

## 4. 组件职责

### 4.1 Model

Model 只负责从当前消息和受限上下文中提取语义候选：回答、Proposal、业务目标、无法映射请求和歧义。

Model 不得产生 Workflow 跳转、revision、权限结论、工具调用、认证结果、资格结果或业务成功状态。

### 4.2 Harness

Harness 是自然语言和业务执行之间的信任边界，负责：

- 构造模型输入视图；
- 裁剪历史和敏感数据；
- 校验模型 JSON、字段白名单和原文依据；
- 规范化日期、金额、号码、枚举和候选值；
- 读取可信 Runtime State 补充 revision、interaction ID 和 actor；
- 把 Proposal 交给 Router 或 Engine；
- 在无法确定时发起澄清，不擅自执行。

### 4.3 Router

Router 处理 Business Intent 和 Case 级调度。它根据活动流程、暂停流程、能力目录、互斥策略和优先级决定继续、恢复、新建、并行或澄清。

### 4.4 Workflow Engine

Engine 不理解自然语言。它只接收经过 Harness 校验的结构化输入，按 Definition 和 Runtime State 确定性执行：

- 校验输入、Policy、权限和 revision；
- 解析 Proposal 并提交 Slot；
- 保存未解决候选；
- 级联失效 Artifact；
- 计算最小重算前沿；
- 调用工具和管理 Effect；
- 产生新的 Pending Interaction 或完成结果。

### 4.5 Tool Executor

Tool Executor 只调用已注册工具，并返回 Definition 声明的状态和数据。工具不能直接改变 Workflow State。

## 5. 一轮消息的标准流程

```text
用户消息
  ↓
Harness 构造 Model Request
  ↓
Model 输出语义候选
  ↓
Harness 进行 JSON、白名单、原文、类型、权限和版本校验
  ↓
Proposal / Business Intent / Ambiguity
  ↓                         ↓
Workflow Engine             Intent Router
  ↓                         ↓
状态变化、工具、提问       继续 / 恢复 / 新建 / 并行 / 澄清
```

Harness 不把模型输出直接交给 Engine。Engine 也不接受模型提供的节点、revision、Policy 或工具字段。

## 6. 修改已确认信息

当用户修改一个 Slot 时，Engine 依据依赖图反向传播失效：

```text
departure_date
       ↓
flight_search_result
       ↓
selected_flight
       ↓
cabin_quote
       ↓
booking_confirmation
```

普通数据依赖由 `inputs/outputs` 和 Artifact 依赖边表达；手机号变化后必须重新 OTP 认证等安全规则由 Policy 表达。Engine 计算失效和重算，模型不指定跳转节点。

## 7. 文档地图

| 文档 | 责任 |
|---|---|
| [README](../README.md) | 项目入口、范围和阅读顺序 |
| 本文 | 总体架构、核心模型和组件边界 |
| [大模型交互协议](./model-interaction-protocol.md) | Model Request 和 Model Candidate |
| [Harness 协议](./harness-interpretation-protocol.md) | 候选校验、规范化和交接 |
| [Workflow Definition 规范](./workflow-definition-spec.md) | 静态流程合同 |
| [Workflow Engine 协议](./workflow-engine-protocol.md) | Engine Command、Decision 和 Emission |
| [对话测试用例](./conversation-test-cases.md) | 场景、预期状态和禁止副作用 |
| [Workflow 示例](./workflows/) | 退款、取消续费和机票流程的设计示例 |

## 8. 设计原则

1. 模型提出候选，Engine 决定是否接受。
2. 已确认 Slot 和未解决 Proposal 分开保存。
3. 业务规则写入 Definition 和 Policy，不写进 Prompt。
4. 普通依赖使用数据血缘，特殊安全影响使用 Policy。
5. 每个副作用都必须可审计、可幂等、可恢复。
6. 新场景优先扩展通用数据模型和 Policy，不为一句新话术增加一个特殊枚举。
