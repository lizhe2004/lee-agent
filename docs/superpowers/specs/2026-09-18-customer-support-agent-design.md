# 智能客服 Agent：Workflow、Harness 与 Skills 设计

## 1. 目标与范围

首个版本提供 CLI 客服对话，覆盖退款和取消自动续费等客诉。系统必须将自然语言理解与业务操作控制分开：模型负责理解、追问和表达；程序负责流程状态、前置条件、工具权限、业务结果记录。

首个可交付切片为端到端退款流程，支持当前账号及跨账号身份验证、订单查询、播放记录和历史退款查询、资格评估、渠道分流、退款提交和人工升级。流程定义使用结构化格式，能够被引擎执行并生成供人阅读的流程文档。

## 2. 核心术语

- **Agent**：模型驱动的客服角色。提取用户信息、提出下一步动作，并根据真实工具结果组织回复。模型不能直接修改可信业务事实或绕过流程。
- **Skill**：给 Agent 加载的领域指引，包括触发条件、收集信息、表达方式、解释规则和边界。Skill 不是安全门，也不是业务数据的权威来源。
- **Workflow definition**：机器可读的流程图定义，描述节点、条件、动作、迁移和失败路径。它是关键业务流程顺序与门槛的可执行来源。
- **Workflow engine**：解析和校验 workflow definition，持久化流程实例，并确定性地执行节点和迁移。
- **Harness**：Agent 运行时外壳，协调对话、Skill 加载、workflow engine、受控工具调用、持久化、审计、错误处理和模型输出。
- **业务工具**：验证码、订单、订阅、退款资格、退款提交和人工转接等后端能力。关键授权和业务约束应在工具服务端再次校验。

关系：Harness 包含或调用 workflow engine；workflow engine 根据定义控制步骤；Agent 在 Harness 中工作并使用 Skill；只有 Harness 在通过流程和权限检查后才调用工具。

## 3. 设计原则

1. **机器流程与 Agent 指引分离**：workflow 控制执行顺序；skill 控制对话理解和表达。两者可以引用同一个 workflow ID，但不复制权威退款规则。
2. **失败关闭**：缺少门槛、未知工具状态、未知节点或流程配置错误时，不执行敏感操作；明确失败或转人工。
3. **业务事实来自工具**：身份验证、订单存在、订阅状态、资格和操作成功只能由可信服务结果确认，不能由模型推断。
4. **工作流版本固定**：启动流程实例时记录 workflow 版本；后续恢复继续使用该版本。
5. **可组合但不穷举组合**：预先定义可复用的业务流程和能力；运行时将一条客诉拆成已登记的目标并组合，不为每种意图组合单独编写 workflow 或 skill。
6. **高影响操作可追溯**：记录状态迁移、规则版本、工具调用和结果；敏感凭据不得进入普通日志。
7. **支持更正用户输入**：用户输入与工具派生事实分别记录来源和版本；修改上游输入后，撤销所有依赖它的派生事实与旧确认，再从指定节点重新计算。

## 4. Workflow 定义格式

首版采用 JSON 定义，并提供正式的 JSON Schema（Draft 2020-12）作为结构规范。运行时先按 JSON Schema 校验结构，再执行额外的语义校验（目标节点存在、工具已注册、状态迁移完整、表达式安全）并编译为内存图。自然语言文档由 JSON 定义生成，避免维护两份互相漂移的流程。

字段的业务运行语义、来源、权限和用户更正规则见 [`docs/workflow-definition-spec.md`](../../workflow-definition-spec.md)。JSON Schema 只定义结构，不能替代这份规范说明。

首版节点类型：

- `ask`：向用户提问并从回答中提取指定字段；保存后暂停，等待下一条用户消息。
- `branch`：基于已验证 facts 确定性选择迁移。
- `action`：调用注册工具；调用前检查 `requires`；按工具返回的枚举状态选择迁移。
- `respond`：生成或渲染面向用户的最终解释。
- `wait`：等待异步事件或人工处理。
- `end`：结束流程实例。

顶层 `mutable_inputs` 声明可由用户提供且允许后续修改的事实。每项包含类型、修改后的重算入口 `on_change`、修改入口优先级 `priority`，以及必须清除的派生事实列表 `invalidates`。每个 mutable input 必须由至少一个 `ask.collect` 节点收集；`on_change` 必须指向有效节点。schema 定义格式，loader 执行这些跨字段语义校验。

示例：

```json
"mutable_inputs": {
  "travel_date": {
    "type": "string",
    "on_change": "search_flights",
    "priority": 10,
    "invalidates": ["flight_search", "selected_flight", "cabin_quote", "booking_confirmation"]
  }
}
```

Action 节点至少需要 `tool`、参数映射、`requires`、结果状态迁移和失败处理。前置条件未满足是流程分支，不是模型推理结果；应跳到显式配置的失败节点。未配置失败路径时拒绝执行并报告流程配置错误。

`on_guard_failure` 是 action 的必需字段，值为流程图中的节点 ID。引擎逐条计算 `requires`；若任一条件不满足，记录未满足条件，不调用工具，转到该节点。若字段缺失或目标节点不存在，流程定义校验失败。工具正常返回的业务状态使用 `transitions` 映射；工具异常使用显式的错误状态迁移。前置条件不满足与工具报错是两类不同事件。

退款流程定义片段：

```json
{
  "$schema": "../../schemas/workflow.schema.json",
  "id": "refund_request",
  "version": 1,
  "start": "collect_order_clues",
  "nodes": {
    "collect_order_clues": {
      "type": "ask",
      "collect": ["charge_date", "amount", "purchase_channel_hint", "purchase_account_hint"],
      "prompt": "请提供扣款日期、金额，以及可能的购买账号和渠道。",
      "next": "verify_account"
    },
    "verify_account": {
      "type": "action",
      "tool": "verify_purchase_account",
      "args": {"phone": "{{ purchase_account_phone }}"},
      "requires": ["purchase_account_phone"],
      "on_guard_failure": "ask_for_account",
      "result_statuses": ["verified", "failed", "expired", "error"],
      "transitions": {
        "verified": "find_order",
        "failed": "escalate",
        "expired": "ask_for_account",
        "error": "escalate"
      }
    },
    "ask_for_account": {
      "type": "ask",
      "collect": ["purchase_account_phone"],
      "prompt": "请提供购买账号绑定的手机号，以便验证账号归属。",
      "next": "verify_account",
      "max_visits": 3,
      "on_limit": "escalate"
    }
  }
}
```

该片段只展示 JSON 结构；可执行 workflow 文件必须包含所有迁移目标节点，并通过正式 schema 和语义校验。

完整定义需要覆盖确认、提交、提交状态报告、重试上限、超时、取消和人工升级。流程 schema 还应限制条件表达式为安全的受限语法，不使用任意代码执行。

## 5. Workflow engine 运行语义

每个流程实例持久化：`case_id`、`workflow_id`、`workflow_version`、`current_node`、`status`、`facts`、`fact_sources`、`fact_revisions`、节点访问计数、工具调用记录和审计事件。用户输入来源标为 `user`；外部工具写入的可信事实带工具来源。模型不得覆盖工具拥有的事实。

单轮运行：

1. Harness 根据 case ID 加载实例和固定版本的定义。
2. Harness 先判断消息是当前问题的回答，还是对之前已提供的 mutable input 的更正。首次提供字段按当前 ask 处理；更正仅允许写入 workflow 声明的 mutable inputs，并按声明类型校验。日期相对表达式需按案件时区解析；无法唯一确定时先澄清。若一条消息同时包含“确认”和输入更正，更正优先，旧确认不生效。
3. 输入更正后递增该字段版本，记录来源，清除该 mutable input 声明的 `invalidates` 中所有 facts 及其来源/版本，并跳到 `on_change` 重新计算。多字段更正时选择 `priority` 数值最小的入口，以确保从最早受影响步骤重跑。失效的派生事实不能用于工具参数、资格判断或最终确认。
4. 若不是更正，且实例正在等待用户，Agent 仅将回复提取成当前 `ask.collect` 声明的字段；程序校验字段类型和来源，再合并 facts。模型不能写入受保护字段，如 `identity_verified`、`refund_eligibility` 或工具结果。
5. 引擎从 `current_node` 开始推进：`branch` 计算迁移；`action` 检查守卫后调用注册工具、保存返回值并按状态迁移。
6. 到达 `ask` 时，Agent 结合 skill 和流程提示生成自然语言问题；保存实例为等待用户后返回。
7. 到达 `wait` 时持久化并等待事件；到达 `end` 时关闭案件。

在机票示例中，航班搜索、已选航班、商务舱报价和确认都依赖出发日期。用户在确认前把日期改为明天，流程清除这些旧结果，跳回航班搜索，要求重新选航班、查舱位/价格并确认。已出票后不能把日期字段改掉后重跑预订；那应转入独立的改签/退票流程。

常规前置条件不满足时，执行 `on_guard_failure`/显式失败迁移，不调用工具。未知返回状态、工具参数校验失败、节点缺失或不完整配置属于系统/配置错误，不由 Agent 自行选路。写操作使用幂等键；超时后的重试不得造成重复退款或重复取消。

首版采用同步工具执行；后台审核、人工等待等长任务通过 `wait` 节点和事件恢复扩展。一个简化的解释器只需支持上述节点类型、受限条件表达式、工具注册表和持久化接口。

## 6. Harness 职责

Harness 提供以下组件接口：

- 对话入口和案件创建/恢复。
- 意图提取与结构化输出校验。
- Skill 注册和按需加载。
- Workflow 注册、启动和事件分发。
- 工具注册表及参数 schema。
- 在工具调用前执行 workflow 守卫与授权策略；对拒绝操作失败关闭。
- 持久化案件、facts、等待状态和 workflow 版本。
- 审计工具调用与迁移；重试策略、超时、幂等和人工升级。
- 最终回复校验，确保只有依据真实工具结果表达成功。

模型提出的是候选动作或字段提取结果，不是直接授权。Harness 根据当前节点决定可用动作并复核候选调用。

## 7. Skill 组织

首版提供端到端入口 skill `refund_request`，描述退费意图识别、收集信息、提问和解释策略，并引用 `workflow_id: refund_request`。Skill 不包含可变资格公式、不自行判断工具结果，也不试图代替 workflow。

`subscription_cancellation` 可作为另一条端到端业务 skill/workflow。身份验证、渠道说明、人工升级等只有在多流程确实共享时才拆成可复用指引或子流程；不为每个用户意图组合新建 skill。

Skill 是否有 workflow 是可选的：纯知识问答 skill 可以没有；会改变订阅、退款或账号状态的操作应走受控 workflow。

## 8. 多意图与运行时编排

意图路由将用户目标转换成已登记的类型化目标，例如 `refund_charge`、`cancel_renewal`、`lookup_subscription`，并附带目标账号范围。通用案件编排器按已配置的依赖规则组合目标：敏感查询前验证对应账号；退款前定位订单并评估资格；取消和退款分别记录结果。

编排器不为所有组合预先保存完整流程，也不接受模型生成任意执行图。它只组合已登记的目标和子流程；未知目标、歧义、授权范围不明时先澄清或转人工。新增用户目标可以加入现有案件，保留已完成步骤，但必须重新检查依赖和授权范围。

## 9. 渠道与客诉处理要求

- Apple 购买走 Apple 退款申请路径；自有渠道退款工具不得操作第三方订单。
- 取消自动续费与退还既有扣款是独立目标和结果。
- 跨账号操作必须验证目标账号；验证状态不能跨账号复用。
- 查询播放记录、历史退款等敏感数据前需要已验证身份和匹配订单。
- 工具失败、数据冲突或资格不确定时，转人工并附上最少必要处理摘要。

## 10. 验证策略

引擎单元测试覆盖：流程 schema 校验、缺失节点、未知工具状态、branch 求值、前置条件失败时不调用工具、状态恢复和版本固定。

Harness 集成测试覆盖：工具调用权限、模型尝试越过节点、事实字段来源保护、幂等重试、超时和审计脱敏。

端到端对话样例覆盖：当前账号退款、跨账号 OTP、Apple 订单、未符合资格、订单查不到、播放记录查询失败、取消续费但仍要求退款、复合意图含家庭成员账号、用户中断后恢复。

验收重点是不变量：未验证不查敏感数据；未评估资格不提交退款；第三方订单不走自有退款；取消成功不等于退款成功；未知工具结果不被报告为成功。

## 11. 实施阶段

1. 定义并校验 workflow schema 和安全条件表达式。
2. 实现可持久化的状态机解释器，使用退款流程做首个端到端切片。
3. 实现 Harness 对话循环、工具注册表、事实来源控制、审计和幂等。
4. 添加 `refund_request` skill，并由 workflow 定义生成流程文档。
5. 增加取消续费流程与复合意图案件编排。
6. 使用上述不变量及对话样例验收。

首版建议使用 Python CLI、JSON workflow 定义和本地 SQLite 持久化；业务工具先通过确定性 mock 接口模拟。工具接口与流程引擎保持分离，以便后续接入真实账号、订单、订阅和退款服务。
