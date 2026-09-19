# 订机票 Workflow（目标规范设计稿）

对应定义：[flight_booking.v1.design.json](../../workflows/flight_booking.v1.design.json)。

这是一份面向未来运行时的设计稿，不承诺能被当前原型 loader 直接加载。它用于确定正式规范需要支持的字段和语义。

## 静态定义

JSON 中的 `slots`、`artifacts`、`policies` 和 `nodes` 都是静态定义：

- `slots` 定义用户输入的类型、所有者、敏感性和是否允许后续修改。
- `artifacts` 定义工具或节点产生的派生事实。
- `nodes.inputs` / `nodes.outputs` 供引擎编译依赖图。
- `policies` 声明无法仅靠数据依赖推导的业务失效规则。
- `nodes.allowed_intents` 和 `intent_routes` 允许 `ask` 节点被修改请求打断。

## 动态状态示例

运行时不修改 JSON 定义，而是创建独立的案件状态：

```json
{
  "case_id": "case_1001",
  "workflow_id": "flight_booking",
  "workflow_version": 1,
  "current_node": "confirm_booking",
  "status": "waiting_for_user",
  "revision": 7,
  "slots": {
    "origin": "北京",
    "destination": "上海",
    "departure_date": "2026-09-20",
    "cabin": "business",
    "selected_flight_id": "CA123",
    "passenger_name": "张三"
  },
  "artifacts": {
    "flight_search": {
      "value": {"flights": [{"id": "CA123", "price": 2100}]},
      "depends_on": {
        "origin": 1,
        "destination": 1,
        "departure_date": 2,
        "cabin": 1
      },
      "source": "tool:flight.search",
      "revision": 3
    },
    "cabin_quote": {
      "value": {"price": 2100, "cabin": "business"},
      "depends_on": {"selected_flight_id": 1, "cabin": 1},
      "source": "tool:flight.quote",
      "revision": 4
    }
  }
}
```

## 修改日期的运行过程

用户在 `confirm_booking` 节点说“改成明天”时，Harness 先产生临时 patch：

```json
{
  "intent": "modify",
  "slot_changes": {"departure_date": "2026-09-21"}
}
```

引擎再执行以下步骤：

1. 校验日期格式，并把 patch 合并进 State 的 `slots`。
2. 根据 `nodes.inputs` / `nodes.outputs` 的依赖图找到受影响的 artifacts。
3. 合并 `policies.departure_date.invalidates` 中的额外事实。
4. 清除搜索结果、旧航班选择、旧报价和旧确认。
5. 按 `change_policy.restart_at` 回到 `search_flights`。
6. 重新搜索、选择、报价，并再次等待确认。

`slot_changes` 是本轮消息的临时结果；`slots` 和 `artifacts` 才是持久化的动态状态。
