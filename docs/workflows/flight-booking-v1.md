# 机票预订 Workflow 示例

这是一个面向 Workflow Definition 规范 0.2 的设计示例，不是当前可执行代码。

## 1. 业务目标

```text
收集行程 → 查询航班 → 选择航班 → 选择舱位 → 获取报价 → 用户确认 → 创建订单
```

默认询问顺序是出发地、到达地、日期和舱位，但用户可以一次提供多个字段。

## 2. Slot

| Slot | 类型 | 基数 | 提议策略 | 说明 |
|---|---|---|---|---|
| `origin` | string | single | user_must_choose | 出发城市 |
| `destination` | string | single | user_must_choose | 到达城市 |
| `departure_date` | date | single | user_must_choose | 出发日期 |
| `departure_date_candidates` | date | set | backend_may_filter | 只有定义支持候选日期查询时使用 |
| `cabin` | enum | single | user_must_choose | economy、business、first |
| `selected_flight_id` | string | single | user_must_choose | 依赖当前航班列表 |
| `booking_confirmed` | boolean | single | user_must_choose | 用户最终确认 |

默认 Definition 不启用 `departure_date_candidates`，所以“明天后天都行”会被保存为未解决 Proposal，并要求澄清或走显式代选 Policy。

## 3. Artifact 和依赖

```text
slots.origin + slots.destination + slots.departure_date + slots.cabin
  → artifacts.flight_search
  → slots.selected_flight_id
  → artifacts.cabin_quote
  → slots.booking_confirmed
  → artifacts.booking
```

`flight_search`、`cabin_quote` 和 `booking` 是 Artifact；用户不能直接写入。`selected_flight_id` 和 `booking_confirmed` 是 Slot，但分别依赖航班列表和报价。

## 4. 节点

### `collect_trip`（ask）

- `kind=form`；fields 为 `origin`、`destination`、`departure_date`；
- `inputs=[]`；`outputs` 为三个 Slot；
- 用户一次提供 A、B、C 时，Harness 生成三个 Proposal；Engine 校验后跳过已满足的 ask；
- 缺少字段时只询问缺少的字段。

### `search_flights`（action）

- inputs：四个行程 Slot；
- outputs：`artifacts.flight_search`；
- 工具：`flight.search`；
- 只有所有输入是 committed Slot 且 valid 时才执行；
- 结果为空进入无结果路径，技术失败进入重试或人工路径。

### `select_flight`（ask）

- `kind=selection`；options 来自 `artifacts.flight_search`；
- fields 为 `selected_flight_id`；
- 选项失效后不得接受旧航班号。

### `collect_cabin`（ask）

- `kind=selection` 或 `text`；fields 为 `cabin`；
- 只接受 Definition 声明的舱位。

### `quote_cabin`（action）

- inputs：`flight_search`、`selected_flight_id`、`cabin`；
- outputs：`artifacts.cabin_quote`；
- 报价过期时不能进入确认。

### `confirm_booking`（ask）

- `kind=confirmation`；fields 为 `booking_confirmed`；
- `accepts` 为 `answer`、`cancel`；
- 用户说“改成明天”时不是确认，Harness 生成对 `departure_date` 的 correction Proposal。

### `create_booking`（action）

- requires：`booking_confirmed == true` 且报价仍 valid；
- outputs：`artifacts.booking`；
- 必须带幂等键；重复提交不能创建第二个订单。

## 5. 多候选日期

用户说：

```text
明天后天都行
```

Model Candidate：

```json
{
  "proposals": [
    {
      "target": "slots.departure_date",
      "candidates": [{"raw_value": "明天"}, {"raw_value": "后天"}],
      "relation": "any_of",
      "commitment": "user_accepts_any"
    }
  ]
}
```

默认单值日期策略下，Engine 不把其中一个写入 `departure_date`。系统可以：

1. 询问用户更倾向哪一天；
2. 使用已声明的“优先较早可用日期” Policy，并记录代选原因；
3. 使用另一个显式声明的候选日期集合 Slot 和查询工具。

## 6. 修改日期

用户在确认时说“改成明天”：

1. Harness 生成对 `slots.departure_date` 的 correction Proposal；
2. Engine 校验 revision 和 Slot Policy；
3. 使 `flight_search`、`selected_flight_id`、`cabin_quote` 和确认相关状态失效；
4. 重新查询并生成新的交互；
5. 旧航班、价格和确认不能继续使用。

模型和 Harness 不提交 `restart_at` 或 `invalidates`；这些由 Definition 和 Engine 计算。

## 7. 多业务目标

用户说：

```text
改成明天，另外把自动续费也关了。
```

Harness 交付一个机票 Proposal 和一个 `cancel_auto_renewal` Business Intent。Router 决定第二个目标是排队、并行还是暂停当前流程处理。
