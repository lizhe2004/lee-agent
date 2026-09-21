# Lee Agent

Lee Agent 是一个面向复杂客诉场景的智能客服 Agent 设计项目。

项目目标不是让大模型自由聊天或自由调用工具，而是把自然语言理解接入可审计、可恢复、可重算的业务流程。当前仓库以长期规范和场景设计为主，暂不保留 Python Demo 实现。

## 解决的问题

- 退款、取消自动续费、机票预订等多步骤业务；
- OTP、身份认证、权限和不可逆操作确认；
- 用户中途修改日期、手机号或其他已提供信息；
- 用户一次消息提供多个字段；
- 用户提供多个候选值，例如“明天后天都行”；
- 用户在当前流程中提出第二个业务目标；
- 工具调用、幂等、副作用和审计。

## 核心架构

```text
用户
  ↓
Model：提取语义候选
  ↓
Harness：校验、规范化、建立信任边界
  ↓
Router：调度多个业务目标
  ↓
Workflow Engine：确定性执行 SOP 和状态变化
  ↓
Tools：提供可信查询和副作用结果
```

Model 不能决定节点跳转、身份认证、退款资格、工具调用或 revision。Engine 只接收经过 Harness 校验的结构化输入。

## 从哪里开始读

1. [总体设计](docs/architecture-overview.md)
2. [大模型交互协议](docs/model-interaction-protocol.md)
3. [Harness Interpretation 协议](docs/harness-interpretation-protocol.md)
4. [Workflow Definition 规范](docs/workflow-definition-spec.md)
5. [Workflow Engine 协议](docs/workflow-engine-protocol.md)
6. [对话测试用例](docs/conversation-test-cases.md)

场景示例位于 [docs/workflows](docs/workflows/)：

- 退款；
- 取消自动续费；
- 机票预订。

## 关键概念

- **Case**：一个客服案件，可以包含多个业务目标。
- **Workflow Instance**：某个案件按一个准确 Definition 版本运行的实例。
- **Proposal**：用户提出但尚未被流程接受的候选值或候选集合。
- **Slot**：Workflow 接受的业务变量。
- **Artifact**：由节点或工具产生的派生结果。
- **Effect**：退款、取消订阅、创建订单等外部副作用。

特别要区分：

```text
Proposal ≠ Slot
Slot ≠ Artifact
Model Candidate ≠ Engine Command
```

## 当前状态

当前仓库处于规范重构阶段。文档用于确定长期架构和协议边界，后续实现应先通过文档中的场景测试，再逐步恢复 CLI、Harness、Engine 和工具适配器。

## 设计要求

- 静态 Workflow Definition 不保存运行时数据；
- 用户修改输入后，派生结果按依赖图和 Policy 失效；
- 未解决的多个候选不能被自动当成第一个候选；
- 可信字段只能由 Engine、Tool 或授权事件产生；
- 所有副作用都要有幂等键、结果状态和审计记录；
- 协议扩展通用语义，不为单个话术增加特例字段。
