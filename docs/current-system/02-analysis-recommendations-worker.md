# 02 分析、推荐与 worker

## 1. 分析 run 的核心状态机

`analysis_runs.status` 可能是：

```text
queued
  -> dispatching
  -> running
  -> succeeded

queued/dispatching
  -> cancelled

running
  -> cancelling
  -> cancelled

running/dispatching
  -> failed

dispatching/running stale
  -> queued 或 failed
```

状态含义：

- `queued`：HTTP API 已创建 run，等待 dispatcher。
- `dispatching`：dispatcher 已 claim 这条 run，正在投递 Celery task。
- `running`：worker 已抢到任务并进入执行。
- `cancelling`：用户取消正在运行的任务，等待 cooperative cancellation。
- `cancelled`：取消完成。
- `succeeded`：分析成功，结果已写入 `analysis_run_results`。
- `failed`：分析失败，`analysis_runs.error` 有失败原因。

## 2. 用户创建一次分析

前端入口是 `/analysis/new`：

```text
web/src/routes/analysis/new.tsx
  -> runsApi.create()
  -> POST /runs
```

请求字段：

- `ticker`：会 trim + upper，允许 `A-Z 0-9 . _ - ^`，最长 32。
- `trade_date`：不能是未来日期。
- `asset_type`：`stock` 或 `crypto`。
- `analysts`：至少一个，不能重复。

后端 `POST /runs` 的步骤：

1. 要求当前用户是 `admin` 或 `operator`。
2. 读取用户模型设置快照；没有则 409。
3. 对当前用户行做容量锁。
4. 检查用户 backlog 容量。
5. 创建 `analysis_runs`：
   - `run_id=run_*`
   - `status=queued`
   - 保存 ticker/trade_date/asset_type/analysts/user_id
   - 保存 `llm_config` 快照
6. 写 `analysis_run_events` 的 `run_queued`。
7. commit 后返回 202 和 queue_position。

这里不会直接 `apply_async`。如果 Celery beat/dispatcher 没跑，run 会一直停在 `queued`。

## 3. dispatcher 如何派发

Celery beat 在 `tradingagents/worker/celery_app.py` 中注册两个周期任务：

- `dispatch_queued_runs_task`
- `sweep_stale_runs_task`

dispatcher 逻辑在 `tradingagents/worker/dispatcher.py`：

```text
dispatch_once(session, enqueue, config)
  -> capacity_left = max_running_system - count_active_runs()
  -> round-robin 扫描有 queued run 的 user
  -> 如果该用户 active run 未超过 max_running_per_user
       claim_next_queued_for_dispatch()
       status = dispatching
       lease_expires_at = now + run_lease_seconds
       commit
       enqueue(run_analysis_task)
       写 celery_task_id
       commit
```

先 commit `dispatching` 再 enqueue 是为了避免 fast worker 在 row 还没可见时开始执行，导致状态竞争。

## 4. worker 如何执行 run

Celery task 是 `tradingagents.worker.jobs.run_analysis_task(run_id)`。

执行包装：

1. 打开 DB session。
2. 找 run owner 的目标语言。
3. 如果需要翻译，准备 `on_section` callback。
4. 调 `execute_analysis_run()`。
5. 成功后 backfill 缺失翻译 section。
6. 如果 `IBKR_AUTO_PROPOSE=true`，best-effort 自动创建 trade proposal。

`execute_analysis_run()` 的关键步骤：

1. `start_dispatched_run(run_id)`：`dispatching -> running`。
2. 写 15% progress：准备模型、数据源和智能体配置。
3. 写 35% progress：开始智能体分析。
4. 创建 `RunContext`：
   - run_id
   - user_id
   - memory_store
   - cancellation_token
5. 带 heartbeat 执行 `run_tradingagents_analysis()`。
6. 如果期间 run 变成 cancelling/cancelled，则标记取消并退出。
7. 写 85% progress：保存报告。
8. `store_success()` 写 result、run_succeeded。
9. 写 artifacts。

异常处理：

- `AnalysisCancelled`：标记 cancelled。
- 其他异常：rollback 后 `store_failure()`，run 变 failed，再把异常抛给 Celery。

## 5. sweeper 如何修复卡住任务

`sweep_once()` 处理两类问题：

1. `dispatching` 且 lease 过期：
   - 回到 `queued`
   - error/reason 是 dispatch lease expired
2. `running/cancelling` 心跳 stale：
   - 如果 attempt_count 已达到 max_attempts，标记 failed。
   - 否则 requeue。

`cancelling` 但还没 started/heartbeat 的任务会直接标记 cancelled。

## 6. TradingAgentsGraph 的执行拓扑

核心类：`tradingagents/graph/trading_graph.py::TradingAgentsGraph`。

初始化时构造：

- quick LLM
- deep LLM
- tool nodes
- `ConditionalLogic`
- `GraphSetup`
- `Propagator`
- `Reflector`
- `SignalProcessor`

初始 state 包含：

- `messages`
- `company_of_interest`
- `asset_type`
- `trade_date`
- `past_context`
- `market_report`
- `sentiment_report`
- `news_report`
- `fundamentals_report`
- `investment_debate_state`
- `risk_debate_state`

当前 graph 拓扑：

```text
START
  -> selected analysts in sequence
     每个 analyst:
       Analyst node
         -> tools_* if LLM requested tools
         -> Msg Clear * if report ready
  -> Bull Researcher
  -> Bear Researcher
  -> ... 多空辩论直到 max_debate_rounds
  -> Research Manager
  -> Trader
  -> Aggressive Analyst
  -> Conservative Analyst
  -> Neutral Analyst
  -> ... 风险辩论直到 max_risk_discuss_rounds
  -> Portfolio Manager
  -> END
```

虽然配置名里有 `analyst_concurrency_limit`，当前 graph 边仍是顺序连接，默认不是 analyst fan-out 并行执行。

## 7. Analyst 和工具

四类 analyst：

| key | 节点名 | 输出字段 | 主要职责 |
| --- | --- | --- | --- |
| `market` | Market Analyst | `market_report` | 价格、技术指标、趋势 |
| `social` | Sentiment Analyst | `sentiment_report` | 新闻、StockTwits、Reddit 情绪 |
| `news` | News Analyst | `news_report` | 公司新闻、宏观新闻、内幕交易 |
| `fundamentals` | Fundamentals Analyst | `fundamentals_report` | 财务、资产负债表、现金流、利润表 |

工具调用路径：

```text
agent prompt
  -> LangChain tool
  -> tradingagents/agents/utils/*_tools.py
  -> tradingagents/dataflows/interface.py
  -> yfinance 或 alpha_vantage 实现
```

vendor 配置：

- `DEFAULT_CONFIG["data_vendors"]`：按类别设置。
- `DEFAULT_CONFIG["tool_vendors"]`：按单个工具覆盖，优先级更高。

fallback 规则：

- `route_to_vendor()` 先走配置的 vendor。
- 如果 Alpha Vantage 触发 rate limit，会 fallback 到可用的其他 vendor。
- 其他异常不会自动 fallback。

## 8. 研究、交易、风险和组合经理

研究阶段：

- Bull Researcher 读取四份 analyst report，形成多头论证。
- Bear Researcher 形成空头论证。
- `investment_debate_state` 保存双方历史、当前回复和轮次。
- Research Manager 总结成 `investment_plan`，评级使用五档之一。

交易阶段：

- Trader 读取 analyst reports 和 research plan。
- 输出 `trader_investment_plan`，偏交易执行视角。

风险阶段：

- Aggressive Analyst 强调机会。
- Conservative Analyst 强调防守。
- Neutral Analyst 综合平衡。
- `risk_debate_state` 保存三方历史和轮次。

最终阶段：

- Portfolio Manager 读取 research plan、trader plan、risk debate 和 past context。
- 输出 `final_trade_decision`。
- `SignalProcessor` 从 markdown 中解析最终评级：
  - `BUY`
  - `OVERWEIGHT`
  - `HOLD`
  - `UNDERWEIGHT`
  - `SELL`
- 解析不到时默认 `HOLD`。

## 9. 报告和 artifact

worker 调用 `tradingagents/worker/analysis.py::run_tradingagents_analysis()`。

它会：

1. 从 `DEFAULT_CONFIG` 拷贝配置。
2. 用 run 创建时保存的 `llm_config` 覆盖 provider/model/backend_url。
3. 如有用户加密 API key，解密后放入 config。
4. 创建 `TradingAgentsGraph`。
5. 调 `graph.propagate()`。
6. 调 `save_analysis_report()` 保存 Markdown。
7. 抽取 reports 和 JSON-safe final_state。

报告目录结构：

```text
reports/<ticker>_<timestamp 或 run_id>/
  1_analysts/
  2_research/
  3_trading/
  4_risk/
  5_portfolio/
  complete_report.md
```

Web/API run 带 `run_id` 时，还会写 artifact metadata 到 DB。

## 10. SSE 和前端进度

`GET /runs/{run_id}/events` 的逻辑：

1. 握手时检查 run 是否存在且当前用户可访问。
2. 从 DB event 表补发 `last_event_id` 之后的历史事件。
3. 如果 Redis 可用，订阅 `run:{run_id}` pubsub，拿实时事件。
4. 遇到 `run_succeeded/run_failed/run_cancelled` 结束流。
5. 每轮未终止时 sleep 1 秒。

前端详情页：

- run 状态是 `queued/dispatching/running/cancelling` 时每 3 秒轮询。
- SSE terminated 后 invalidate run/result/artifacts query。
- 成功后加载 `DecisionCard` 和 `AgentReportTabs`。

## 11. 取消逻辑

用户取消：

- `queued/dispatching`：直接变 `cancelled`。
- `running`：先变 `cancelling`。
- 有 `celery_task_id` 时调用 Celery revoke。

真正执行中的 graph 是 cooperative cancellation：

- `CancellationToken` 查 DB 中 run 是否已 cancelling/cancelled。
- `GraphSetup._cancellable()` 包住每个 node/tool，执行前后检查。
- `_run_graph()` streaming 每个 chunk 前后也检查。
- 触发后抛 `AnalysisCancelled`，worker 标记 cancelled。

## 12. 翻译逻辑

目标语言来自 run owner 的 `users.language`。

- `en`：不翻译。
- 非 `en`：优先使用用户专门的 translation settings。
- 没有 translation settings 时，回退分析模型。

翻译分两阶段：

1. mid-run：`on_section_ready` 第一次看到某个 report section 非空时，enqueue `translate_section_task`。
2. post-success：result 写入后遍历所有 reports，缺什么 section 补什么。

翻译是 best-effort：

- section 为空跳过。
- 已翻译跳过。
- 翻译失败不会让 run failed。

## 13. 推荐功能详细流程

### 13.1 Watchlist

`GET /recommendations/watchlist`：

- 没有 row 时返回空列表。

`PUT /recommendations/watchlist`：

- 保存用户 tickers。
- repository 会做去重/规范化/校验。
- 当前 repository 不允许保存空列表，但 generate 阶段允许没有 watchlist row 或 tickers 为空。

### 13.2 生成推荐

`POST /recommendations/generate`：

1. 当前用户必须有模型设置。
2. 读取 watchlist。
3. 没有 watchlist 时 tickers 为空，表示 broad market。
4. 创建 quick LLM。
5. `RecommendationGenerator.generate()` 构建 prompt：
   - watchlist
   - 最近分析上下文
   - today
   - UI language
6. 要求模型返回 JSON `recommendations`。
7. 解析、去重、规范 ticker、容忍坏字段。
8. 最多保存 5 个候选。
9. 写 `recommendation_batches` 和 `recommendation_items`。

推荐项字段：

- `ticker`
- `source`：`watchlist` 或 `model_expansion`
- `priority`
- `reason`
- `risk`
- `status=recommended`

### 13.3 分析推荐项

`POST /recommendations/batches/{batch_id}/analyze`：

1. 要求 `admin/operator`。
2. 当前用户必须有模型设置快照。
3. 找 batch 和 item。
4. 读取 item 关联 run 的最新状态，失败/取消会标记成可重试。
5. 只有 `recommended` 和 `analysis_failed` 可以触发分析。
6. 对每个 item 单独检查容量。
7. 创建普通 stock analysis run：
   - `trade_date=date.today()`
   - `asset_type=stock`
   - analysts 固定四类全开
8. item 标记 `analysis_queued` 并写 run_id。

后续不再有推荐专属执行链，完全回到普通 analysis run。
