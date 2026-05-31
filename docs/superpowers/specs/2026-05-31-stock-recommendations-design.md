# 股票推荐功能设计

日期：2026-05-31
分支：`phase/9-broker-integration`
状态：设计已确认，待拆实施计划

## 目标

把侧边栏里会刷新整个页面的「刷新数据」改造成股票推荐工作流：

- 每个用户的 watchlist 存到应用数据库里，不再依赖环境变量。
- 使用用户已经配置好的分析模型推荐 5 支股票。
- 保存每次推荐批次，形成可回看的历史记录。
- 推荐结果先进入待确认列表，用户手动选择后才开始分析。
- 为选中的推荐股票创建普通分析任务，并把分析任务关联回推荐项。

这是推荐和筛选功能，不是自动交易功能。它不应该直接下单，也不应该直接创建交易审批。

## 已确认决策

- 推荐范围：优先从用户 watchlist 推荐，同时允许模型扩展推荐新股票。
- 分析触发：只支持手动触发。推荐结果先进入确认列表。
- Watchlist 来源：按用户持久化到数据库。
- 推荐历史：保留每个推荐批次，用户可以回看当时推荐了什么、后来分析了哪些。
- 页面布局：独立的「推荐股票」工作台，从侧边栏进入。
- 批次数量：第一版固定每次推荐 5 支股票。
- 推荐输入模式：轻量模式。只使用 watchlist、最近分析历史、当前日期和明确的 prompt/schema，不扫描实时行情或新闻。
- 模型来源：使用用户的分析模型配置。推荐生成优先使用 quick 模型。
- 推荐转分析的参数：全部使用默认值：`asset_type=stock`、今天日期、全量分析师。

## 产品流程

1. 用户从侧边栏打开 `/recommendations`。
2. 用户编辑并保存自己的 watchlist。
3. 用户点击「生成推荐」。
4. 后端读取用户的模型设置、watchlist 和最近分析历史。
5. 后端调用该用户分析模型配置里的 quick LLM，要求生成 5 支推荐股票。
6. 后端校验 ticker 格式，保存推荐批次和推荐项，然后返回批次结果。
7. 用户查看每个推荐 ticker 的理由、风险、来源和优先级。
8. 用户手动勾选一个或多个推荐项，然后点击「开始分析」。
9. 后端为每个选中的推荐项创建普通分析任务，使用默认分析参数。
10. 每个推荐项记录对应的 `run_id`，状态变为 `analysis_queued`。
11. 历史批次保持可见，并链接到已创建的分析任务。

## 侧边栏改动

当前 `Sidebar` 中的「刷新数据」按钮会调用 `location.reload()`。需要把它替换为一个导航入口：

- 文案："Recommend Stocks" / "推荐股票"
- 目标路由：`/recommendations`
- 不刷新整个页面。

原来的 "Last refresh" 时间戳应该删除或重命名，避免用户以为这里仍然是全局刷新。如果保留，它只能表示最近一次推荐批次的时间。

## 前端设计

新增路由：

```text
/recommendations
```

在侧边栏 Analysis 分组下新增入口：

```text
Recommendations
Agent Reasoning
New Analysis
```

推荐页包含四个区域：

1. Watchlist 设置
   - 可编辑 ticker 输入区。
   - 保存按钮。
   - 对非法 ticker 显示校验错误。
   - 点击保存后立即持久化到后端。

2. 生成推荐
   - 主按钮：「生成推荐」。
   - 生成中禁用按钮。
   - 如果模型设置缺失，展示跳转到 `/settings/model` 的入口。

3. 当前批次
   - 用表格或紧凑卡片展示最新推荐批次。
   - 字段：复选框、ticker、来源、优先级、推荐理由、风险、状态、关联 run。
   - 用户只能选择状态仍为 `recommended` 的推荐项。
   - 操作按钮：「分析所选股票」。

4. 历史批次
   - 按创建时间列出以前的推荐批次。
   - 展开批次后展示推荐项详情和关联 run 状态。
   - 历史数据只读，但可点击进入分析详情。

页面风格沿用当前控制台的安静工具型设计：信息密度高、行列清晰、卡片克制，不做营销式 hero。

## 后端 API

新增路由前缀：

```text
/recommendations
```

端点：

```http
GET /recommendations/watchlist
PUT /recommendations/watchlist
POST /recommendations/generate
GET /recommendations/batches
GET /recommendations/batches/{batch_id}
POST /recommendations/batches/{batch_id}/analyze
```

### GET /recommendations/watchlist

返回当前用户的 watchlist。如果用户还没有保存过，返回空列表。

响应：

```json
{
  "tickers": ["AAPL", "MSFT", "NVDA"],
  "updated_at": "2026-05-31T10:00:00Z"
}
```

### PUT /recommendations/watchlist

请求：

```json
{
  "tickers": ["AAPL", "MSFT", "NVDA", "TSLA", "GOOGL"]
}
```

校验规则：

- 统一转换为大写。
- 使用和分析任务相同的 ticker 格式规则。
- 去重并保留原始顺序。
- 至少需要 1 个 ticker。
- 第一版最多允许 50 个 ticker。

### POST /recommendations/generate

为当前用户生成并保存一个新的推荐批次。

第一版请求体可以为空：

```json
{}
```

响应：

```json
{
  "batch_id": "rec_...",
  "status": "succeeded",
  "created_at": "2026-05-31T10:05:00Z",
  "items": [
    {
      "item_id": "reci_...",
      "ticker": "NVDA",
      "source": "watchlist",
      "priority": 1,
      "reason": "Strong AI infrastructure momentum...",
      "risk": "High valuation and earnings sensitivity...",
      "status": "recommended",
      "run_id": null
    }
  ]
}
```

失败情况：

- `409`：模型设置未配置。
- `409`：watchlist 未配置。
- `502`：模型调用失败，或模型返回内容无法使用。

### POST /recommendations/batches/{batch_id}/analyze

为选中的推荐项创建分析任务。

请求：

```json
{
  "item_ids": ["reci_1", "reci_2"]
}
```

行为：

- 只能操作当前用户自己的批次和推荐项。
- 只有 `recommended` 状态的推荐项可以创建分析任务。
- 每个创建出的 run 使用：
  - `asset_type = "stock"`
  - `trade_date = date.today()`
  - `analysts = ["market", "social", "news", "fundamentals"]`
  - 用户已保存的模型设置快照，规则与 `POST /runs` 一致
- 应复用 `POST /runs` 的容量限制检查。
- 允许部分成功：成功的推荐项保留 run 链接；失败的推荐项仍保持 `recommended`，并在响应中带错误原因。

响应：

```json
{
  "created": [
    {"item_id": "reci_1", "ticker": "NVDA", "run_id": "run_..."}
  ],
  "failed": [
    {"item_id": "reci_2", "ticker": "MSFT", "detail": "too many queued analysis runs"}
  ]
}
```

## 数据模型

新增表均为 additive 变更。

### `user_watchlists`

- `user_id`：主键，外键到 `users.user_id`
- `tickers`：JSON list
- `created_at`
- `updated_at`

### `recommendation_batches`

- `batch_id`：主键
- `user_id`：索引
- `status`：`succeeded` 或 `failed`
- `watchlist_snapshot`：JSON list
- `model_snapshot`：JSON object，保存 provider/model/backend 元数据，不保存解密后的 API key
- `prompt_version`
- `error`
- `created_at`

### `recommendation_items`

- `item_id`：主键
- `batch_id`：外键
- `user_id`：索引
- `ticker`：索引
- `source`：`watchlist` 或 `model_expansion`
- `priority`：整数，1 表示最高优先级
- `reason`：文本
- `risk`：文本
- `status`：`recommended`、`analysis_queued`、`analysis_failed`、`ignored`
- `run_id`：可为空，外键到 `analysis_runs.run_id`
- `error`：可为空的文本
- `created_at`
- `updated_at`

推荐项上冗余保存 `user_id`，作为授权保护条件；这与项目里现有 repository 的 user scope 风格保持一致。

## 推荐生成

新增一个小型服务，例如 `tradingagents/api/recommendation_service.py`。

输入：

- 当前用户 id
- 用户 watchlist
- 同一用户最近的分析摘要
- 当前日期
- 用户模型设置快照

服务构造一个聚焦 prompt：

- 必须推荐 5 支股票。
- 优先从 watchlist 中选择，但允许有明确理由的模型扩展推荐。
- 返回结构化 JSON，包含 ticker、source、priority、reason、risk。
- 不允许编造已经完成的分析结论。
- 推荐理由和风险说明要简短，适合作为分析前的筛选依据。

使用现有 LLM client factory：

- `llm_provider` 来自用户模型设置
- 模型使用 `quick_think_llm`
- `backend_url` 来自用户模型设置
- 如果用户保存了 API key，使用解密后的用户 key；否则走现有 LLM client 的服务端环境变量回退逻辑

输出校验：

- 优先用 Pydantic 解析结构化输出。
- 拒绝非法 ticker。
- 对 ticker 去重。
- 如果校验后少于 5 支，但至少有 1 支有效股票，则只保存有效推荐，并把批次标记为 `succeeded`。
- 如果没有任何有效推荐，返回 `502`，不要创建会误导用户的空批次。

## 最近分析上下文

把同一用户最近完成的分析任务作为轻量上下文：

- 最多取最近 10 个 `succeeded` run。
- 包含 ticker、分析日期、最终评级和最终决策的一小段摘录。
- 不包含完整报告，避免推荐生成变得昂贵。

这样模型可以保留一定连续性，但不会调用市场数据工具。

## 授权

- 所有推荐端点都要求登录。
- `viewer` 可以查看推荐历史和 watchlist。
- `operator` 和 `admin` 可以生成推荐并创建分析任务。
- 如果后续产品希望 viewer 也能生成推荐，可以独立放宽，不影响分析创建权限。

## 错误处理

- 模型设置缺失：显示清晰提示，并提供模型设置页入口。
- Watchlist 缺失：提示用户先保存 watchlist。
- Watchlist 中存在非法 ticker：返回字段级校验错误。
- 模型超时或 provider 失败：不创建空批次，前端展示可重试错误。
- 批量创建分析任务部分失败：展示每个 item 的失败原因，失败项保持可选择。
- 已经关联 run 的推荐项被重复提交：返回失败项，错误原因是 `already analyzed`。

## 测试

后端：

- Watchlist get/put 的规范化、去重、校验和鉴权。
- 推荐生成要求已配置模型设置和 watchlist。
- 推荐服务能解析有效结构化输出，并拒绝非法 ticker。
- 批次和推荐项能持久化，当前批次/历史批次按用户隔离。
- Analyze 端点按默认参数创建 run。
- Analyze 端点处理容量限制失败和部分成功。
- 非 owner 不能访问其他用户的推荐批次。

前端：

- Watchlist 表单能保存并重新加载。
- 生成推荐按钮调用 API，并渲染批次项目。
- 模型设置缺失时能链接到 `/settings/model`。
- 选择推荐项并开始分析后，展示创建出的 run 链接。
- 历史批次能正常展示。
- 侧边栏不再调用 `location.reload()`。

## 不在范围内

- 自动分析推荐股票。
- 用实时行情或新闻扫描作为推荐输入。
- 为每支推荐单独配置分析日期或分析师。
- 单独的推荐模型设置。
- 从推荐直接创建交易提案或下单。
- 推荐效果评分；第一版只保存历史，不做绩效评估。
