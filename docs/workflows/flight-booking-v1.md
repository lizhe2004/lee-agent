# 订机票 Workflow（目标规范设计稿）

对应定义：[flight_booking.v1.design.json](../../workflows/flight_booking.v1.design.json)。

该文件是面向未来运行时的设计稿，与 [Workflow Definition 规范](../workflow-definition-spec.md) 第 18.1 节的机票示例保持一致。它用于说明静态 Workflow Definition，不承诺能被当前原型 loader 直接加载。

## 1. 静态 Definition

定义中的主要部分是：

- `slots`：用户提供或选择的业务输入；
- `artifacts`：工具和节点产生的派生事实；
- `nodes[].inputs / outputs`：用于编译数据依赖图；
- `nodes[].request`：ask 节点发给用户的交互请求；
- `nodes[].request.accepts`：Engine 在当前等待点接受的交互事件；
- `nodes[].on`：Engine 对已验证交互结果的确定性迁移；
- `dependencies`：无法从节点输入输出直接推导的显式数据依赖；
- `policies`：无法由普通数据依赖表达的额外业务规则。

`request.accepts` 中的 `answer` 和 `cancel` 是 Engine 事件，不是退款、关闭自动续费等 Business Intent。Harness 会把模型的 `answer` 和 `cancel_interaction` Interaction Act 分别编译为 `interaction.answer` 和 `interaction.cancel` Command。

Workflow Definition 不声明 `new_intent`，也不通过节点上的 `intent_routes` 处理跨流程业务目标。

## 2. 自然语言处理边界

用户在 `confirm_booking` 等待确认时说：

~~~text
改成明天吧，另外把自动续费也关了
~~~

模型按照 [Harness Interpretation 协议](../harness-interpretation-protocol.md) 输出两类语义：

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

Harness 分别处理：

1. 将 `slot_change` 校验并编译为发给当前机票 Workflow Instance 的 `slot.change`；
2. 将 `cancel_auto_renewal` 编译为 Router Request；
3. Router 根据活动案件判断它应继续已有流程、恢复已有流程还是创建额外流程。

模型不判断 `cancel_auto_renewal` 是不是“新意图”。

## 3. “改成明天”的运行过程

Harness 向 Engine 提交的核心 Command：

~~~json
{
  "type": "slot.change",
  "workflow_instance_id": "wfi_booking_001",
  "expected_instance_revision": 7,
  "payload": {
    "changes": {
      "slots.departure_date": "2026-09-20"
    },
    "expected_slot_revisions": {
      "slots.departure_date": 2
    },
    "reason": "user_correction"
  }
}
~~~

Engine 执行：

1. 校验 Workflow Instance、revision、Slot revision、权限和值类型；
2. 更新 `slots.departure_date`；
3. 根据节点 `inputs / outputs` 编译出的反向依赖图计算传递失效；
4. 使 `artifacts.flight_search`、`slots.selected_flight_id`、`artifacts.cabin_quote`、`slots.booking_confirmed` 等旧派生状态失效；
5. 计算最早需要重新执行的生产者节点；
6. 重新搜索、选航班和报价；
7. 产生新的 `interaction.requested`，要求用户基于新结果再次确认。

依赖链为：

~~~text
slots.departure_date
  → artifacts.flight_search
  → slots.selected_flight_id
  → artifacts.cabin_quote
  → slots.booking_confirmed
  → artifacts.booking
~~~

模型不指定 `search_flights`，Harness 不维护手写的完整失效清单，Engine 根据 Definition 的数据依赖计算重算路径。

## 4. 静态定义与动态状态

Definition 是带版本的静态配置；每次订票创建独立的 Workflow Instance State。运行时状态保存：

- 固定的 Definition ID 和版本；
- 当前 revision 和生命周期状态；
- Slot 当前值、Slot revision 和有效性；
- Artifact 当前值、血缘和有效性；
- 当前等待的 interaction 和 interaction_id；
- 已请求或已提交的副作用；
- 审计和幂等记录。

用户修改日期时不会改写 Definition。Engine 只更新该实例的动态状态，并根据固定 Definition 重新计算。
