# Harness Interpretation 协议

状态：Draft 0.2

本文定义 Harness 如何把[大模型交互协议](./model-interaction-protocol.md)产生的 Model Candidate，转换成可信的 Proposal、Engine 输入或 Router Request。

总体架构见[总体设计](./architecture-overview.md)。Workflow 的静态合同见[Workflow Definition 规范](./workflow-definition-spec.md)，Engine 的执行接口见[Workflow Engine 协议](./workflow-engine-protocol.md)。

## 1. Harness 的边界

Harness 是不可信自然语言和确定性业务执行之间的信任边界。

Harness 负责：

- 从可信会话、当前 Engine Emission 和 Case State 构造 Model Request；
- 裁剪历史、Artifact 和敏感数据；
- 校验模型输出结构、版本、request ID 和白名单；
- 验证 Proposal 是否有当前消息依据；
- 按 Field/Slot Registry 规范化日期、金额、电话、枚举和候选值；
- 验证 Slot 来源、mutable、字段基数和 Workflow Policy；
- 使用可信状态补充 actor、revision、interaction ID 和 command ID；
- 把合法 Proposal 交给 Engine，把 Business Intent 交给 Router；
- 在歧义、冲突、过期状态或模型失败时阻止执行并生成澄清。

Harness 不负责：

- 决定 Workflow 是继续、恢复、新建还是并行；
- 决定节点跳转、Artifact 失效范围或重算入口；
- 生成身份认证、退款资格、工具结果或业务成功状态；
- 把多个候选值擅自压成第一个值；
- 让模型输出的 revision、权限或工具字段获得信任。

## 2. 一轮处理流程

```text
可信 Runtime State + 当前消息
          ↓
Harness 构造 Model Request
          ↓
Model Candidate
          ↓
结构、白名单、原文和类型校验
          ↓
Proposal / Business Intent / Ambiguity
          ↓                         ↓
Workflow Engine               Intent Router
```

## 3. Model Candidate 校验

### 3.1 信封校验

Harness 必须检查：

- 结果是单个 JSON 对象；
- `protocol_version` 与 Request 一致；
- `request_id` 与 Request 一致；
- `proposals`、`interaction_acts`、`business_intents`、`unmapped_requests` 和 `ambiguities` 都存在且元素类型正确；
- 没有未知顶层字段；
- 没有控制字段、工具调用和 Policy 结果。

失败时不得生成 Engine Command 或 Router Request。

### 3.2 Proposal 校验

对每个 Proposal：

1. `target` 必须属于本轮 `allowed_slots` 或当前 `pending_interaction.fields`；
2. 修改已有值时目标 Slot 必须 `mutable=true`；
3. `candidates` 必须非空，候选数量和 `relation` 必须一致；
4. `raw_value` 必须能在当前用户消息或允许的指代上下文中定位；
5. 目标类型、枚举、格式和时区规则必须通过确定性校验；
6. `commitment` 不能绕过 Workflow 的基数和解析 Policy；
7. 同一目标的冲突 Proposal 必须进入澄清，不能按数组顺序选值。

Harness 可以生成如下规范化 Proposal：

```json
{
  "target": "slots.departure_date",
  "candidates": [
    {"raw_value": "明天", "normalized_value": "2026-09-21"},
    {"raw_value": "后天", "normalized_value": "2026-09-22"}
  ],
  "relation": "any_of",
  "commitment": "user_accepts_any",
  "evidence": {"message_id": "msg_101", "text": "明天后天都行"}
}
```

`normalized_value`、`evidence`、actor、revision 和 interaction ID 是 Harness 产生的可信交接字段，不是模型必须输出的字段。

### 3.3 Interaction Act 校验

| Model Act | 前置条件 | Harness 处理 |
|---|---|---|
| `answer` | 当前有 ask，且目标 Proposal 只引用当前 `pending_interaction.fields` | 交给当前 ask 的值策略 |
| `slot_change` | 目标 Slot 在 `allowed_slots` 且可修改 | 作为实例级 Proposal 交给 Engine；不由模型指定重算节点 |
| `cancel_interaction` | `pending_interaction.accepts` 包含 `cancel` | 编译为当前交互取消事件 |
| `unable_to_answer` | `pending_interaction.accepts` 包含 `unable_to_answer` | 编译为无法回答事件；不写入当前 fields |

`answer` 不限制同一句话中的其他 Proposal。用户可以同时回答当前字段和提前提供未来字段；这些字段仍分别校验，并由 Engine 按同一轮状态处理规则决定是否原子提交。

### 3.4 Intent 校验

Business Intent 必须：

- 出现在当前 `intent_catalog`；
- 有当前消息中的依据；
- 只使用该 Intent 允许的实体引用；
- 不包含 Workflow ID、节点、Router 决策或权限结论。

Harness 不判断它是新目标。Router 结合 Case 的活动和暂停 Workflow 决定继续、恢复、新建或并行。

## 4. Proposal 到 Engine 的交接

### 4.1 已确定的单值 Proposal

当 Proposal 为 `relation=single` 且 Workflow Policy 允许直接提交时，Harness 生成 Engine 可接受的结构化输入。Harness 补充：

- `workflow_instance_id`；
- `expected_instance_revision`；
- 认证 actor；
- `command_id` 和幂等键；
- 当前有效的 `interaction_id`（如果回答 ask）。

Harness 不提交 `target_node`、`invalidates`、`restart_at` 或工具参数。

### 4.2 多个候选 Proposal

对于 `relation=any_of`、`all_of` 或 `exactly_one`：

1. 如果 Definition 声明了候选集合 Slot 和解析工具，保留候选并交给该 Policy；
2. 如果 Definition 声明了确定的代选策略，交给 Engine/Tool 代选并记录原因；
3. 如果目标 Slot 是单值且没有代选策略，不生成单值写入 Command；
4. Harness 生成澄清请求或保留 Proposal 等待下一轮。

模型不能把候选数组直接塞进普通单值 Slot。

### 4.3 修改已确认 Slot

用户说“日期改成明天”时，Harness 只提交对 `slots.departure_date` 的合法 Proposal。失效范围和重算入口由 Engine 根据 Definition 的依赖图和 Policy 计算。

### 4.4 多个业务目标

用户说“改成明天，另外取消自动续费”时，Harness 交付：

- 当前机票 Workflow 的 Proposal；
- `cancel_auto_renewal` Router Request。

Router 决定调度关系，Harness 不自行排序或新建 Workflow。

## 5. 确定性规范化

Harness 使用 Request 的 `reference_time` 和 `timezone`：

- “明天”转换为具体日期；
- 金额转换为货币和最小单位；
- 手机号按 Registry 规则处理；
- enum 使用稳定值而不是显示文本；
- selection 必须匹配当前有效选项；
- 无法规范化时保留原文并要求澄清，不猜测值。

## 6. 失败、歧义和过期状态

以下情况不得生成执行 Command：

- 当前 `interaction_id` 已关闭或被替代；
- instance revision 已变化；
- Slot 已变成不可修改；
- 当前选项来自已失效 Artifact；
- 同一目标有互相冲突的候选；
- 证据不能在当前消息或允许上下文中定位；
- 用户无法回答且 Workflow 没有对应替代路径。

Harness 应重新读取 Runtime State 后重新解释，或向用户提出最小澄清问题。

## 7. 与其他协议的边界

| 对象 | 产生者 | Harness 是否可直接改写 |
|---|---|---:|
| Model Candidate | Model | 否，只能拒绝或规范化 |
| Proposal | Harness | 可以根据校验结果生成 |
| committed Slot | Engine | 否 |
| Artifact | Engine/Tool | 否 |
| Workflow 路径 | Engine/Router | 否 |
| Engine Command | Harness | 可以从可信状态编译 |
| Router Request | Harness | 可以从可信状态编译 |

## 8. 审计

Harness 至少记录：

- Model protocol version 和模型请求 ID；
- 当前消息 ID 和上下文版本；
- 原始 Model Candidate 摘要；
- 校验结果和拒绝原因；
- 生成的 Proposal、Engine Command 和 Router Request ID；
- revision、interaction ID 和 Policy 决策引用。

原始敏感数据必须按会话和租户策略脱敏。
