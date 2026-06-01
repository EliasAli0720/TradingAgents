# 06 数据模型与状态参考

## 1. 核心分析表

### `analysis_runs`

一条分析任务。

关键字段：

- `run_id`：主键，形如 `run_*`。
- `status`：run 状态。
- `ticker`
- `trade_date`
- `asset_type`
- `analysts`：JSON list。
- `user_id`
- `llm_config`：创建 run 时的用户模型设置快照。
- `priority`
- `attempt_count`
- `max_attempts`
- `current_phase`
- `progress_percent`
- `current_step`
- `celery_task_id`
- `error`
- `dispatched_at`
- `heartbeat_at`
- `lease_expires_at`
- `started_at`
- `finished_at`
- `created_at`
- `updated_at`

状态参考：

```text
queued | dispatching | running | cancelling | succeeded | failed | cancelled
```

### `analysis_run_events`

run 事件流。用于进度、SSE 补历史和调试。

字段：

- `id`
- `run_id`
- `event_type`
- `payload`
- `created_at`

常见 event_type：

- `run_queued`
- `run_dispatching`
- `run_started`
- `run_progress`
- `run_succeeded`
- `run_failed`
- `run_cancelled`

### `analysis_run_results`

成功 run 的结构化结果。

字段：

- `run_id`
- `decision`
- `reports`
- `final_state`
- `created_at`

`decision` 是 `SignalProcessor` 解析出的五档评级之一。`reports` 是展示给前端的扁平报告 map。`final_state` 是完整 graph state 的 JSON-safe 版本。

### `analysis_run_artifacts`

报告 artifact 元数据，不直接存完整文件内容。

字段：

- `artifact_id`
- `run_id`
- `kind`
- `storage_backend`
- `storage_key`
- `content_type`
- `size_bytes`
- `sha256`
- `created_at`

### `analysis_run_translations`

报告 section 翻译。

复合主键：

- `run_id`
- `lang`
- `section`

字段：

- `content`
- `created_at`

### `analysis_memory_entries`

Web/API 下的分析记忆和反思。

字段：

- `user_id`
- `run_id`
- `ticker`
- `trade_date`
- `rating`
- `decision_markdown`
- `pending`
- `raw_return`
- `alpha_return`
- `holding_days`
- `reflection`
- `created_at`

用于后续同 ticker 或跨 ticker 分析时注入历史经验。

## 2. 用户和认证表

### `users`

字段：

- `user_id`
- `username`
- `password_hash`
- `role`
- `is_active`
- `language`
- `created_at`
- `last_login_at`

角色：

```text
admin | operator | viewer
```

### `sessions`

字段：

- `session_id`
- `user_id`
- `csrf_token`
- `created_at`
- `last_seen_at`
- `expires_at`
- `revoked_at`
- `user_agent`
- `ip_text`

session cookie 保存 `session_id`，CSRF cookie/header 保存 `csrf_token`。

## 3. 模型设置表

### `user_model_settings`

字段：

- `user_id`
- `llm_provider`
- `deep_think_llm`
- `quick_think_llm`
- `backend_url`
- `encrypted_api_key`
- `created_at`
- `updated_at`

run 创建时会把这些字段 snapshot 到 `analysis_runs.llm_config`，因此用户修改设置不会改变已排队 run。

### `user_translation_settings`

字段：

- `user_id`
- `llm_provider`
- `model`
- `backend_url`
- `encrypted_api_key`
- `created_at`
- `updated_at`

### `llm_provider_options`

模型 catalog 的 provider 维度：

- `provider_id`
- `label`
- `required_env_var`
- `default_backend_url`
- `backend_url_editable`
- `supports_custom_model`
- `sort_order`

### `llm_model_options`

模型 catalog 的具体 model：

- `provider_id`
- `mode`：`quick` 或 `deep`
- `model_id`
- `label`
- `sort_order`

## 4. 推荐表

### `user_watchlists`

字段：

- `user_id`
- `tickers`
- `created_at`
- `updated_at`

### `recommendation_batches`

字段：

- `batch_id`
- `user_id`
- `status`：`succeeded/failed`
- `watchlist_snapshot`
- `model_snapshot`
- `prompt_version`
- `error`
- `created_at`

### `recommendation_items`

字段：

- `item_id`
- `batch_id`
- `user_id`
- `ticker`
- `source`
- `priority`
- `reason`
- `risk`
- `status`
- `run_id`
- `error`
- `created_at`
- `updated_at`

`source`：

```text
watchlist | model_expansion
```

`status`：

```text
recommended | analysis_queued | analysis_failed | ignored
```

注意：item status 不是 run status。前端 batch detail 会附带 `run_status`。

## 5. Broker 和交易表

### `broker_status`

主要给 IBKR server connector mirror 使用。Webull status 通常来自 `broker_credentials`。

字段：

- `id`
- `broker`
- `gateway_online`
- `brokerage_session`
- `account_id`
- `paper`
- `last_refresh_at`
- `last_error`
- `updated_at`

### `broker_credentials`

per-user Webull 凭据。

字段：

- `id`
- `user_id`
- `broker`
- `account_id`
- `region`
- `auth_type`
- `access_token_enc`
- `refresh_token_enc`
- `app_key_enc`
- `app_secret_enc`
- `token_expires_at`
- `refresh_expires_at`
- `scope`
- `status`
- `created_at`
- `updated_at`

重要约束：

- 当前唯一键是 `(user_id, broker)`。
- 因此一个用户当前只能有一个 active Webull credential。

状态：

```text
connected | expired | revoked
```

auth_type：

```text
oauth | api_key
```

### `trade_approvals`

交易建议和人工审批。

字段：

- `approval_id`
- `run_id`
- `requested_by_user_id`
- `ticker`
- `conid`
- `side`
- `order_type`
- `quantity`
- `limit_price`
- `time_in_force`
- `estimated_price`
- `estimated_value`
- `whatif_init_margin`
- `whatif_commission`
- `risk_verdict`
- `agent_reasoning`
- `status`
- `approved_by_user_id`
- `approved_at`
- `submitted_order_id`
- `error`
- `created_at`
- `updated_at`

状态：

```text
pending | approved | submitted | failed | rejected | expired
```

### `broker_orders`

服务端订单 mirror。

字段：

- `broker_order_id`
- `approval_id`
- `requested_by_user_id`
- `account_id`
- `ticker`
- `conid`
- `side`
- `order_type`
- `quantity`
- `limit_price`
- `time_in_force`
- `status`
- `filled_qty`
- `filled_avg_price`
- `submitted_at`
- `updated_at`
- `raw_event`

状态来自统一 `OrderStatus`：

```text
pending | filled | partially_filled | cancelled | rejected | expired
```

### `portfolio_snapshots`

组合每日快照，用于业绩曲线。

字段：

- `user_id`
- `account_id`
- `broker`
- `snapshot_date`
- `cash`
- `invested_value`
- `total_value`
- `daily_pnl`
- `daily_pnl_pct`
- `open_positions`
- `updated_at`

维度是 `(user_id, account_id, broker, snapshot_date)`。

## 6. BrokerAdapter 统一模型

所有 broker adapter 都要满足 `tradingbot/broker/base.py`。

### AccountInfo

- `cash`
- `portfolio_value`
- `buying_power`
- `equity`
- `daytrade_count`

### Position

- `ticker`
- `qty`
- `avg_entry_price`
- `current_price`
- `market_value`
- `unrealized_pnl`
- `unrealized_pnl_pct`
- `side`

### Order

- `order_id`
- `ticker`
- `side`
- `qty`
- `order_type`
- `status`
- `submitted_at`
- `filled_qty`
- `filled_avg_price`
- `filled_at`
- `limit_price`
- `reject_reason`

### BrokerAdapter 方法

- `get_account()`
- `get_positions()`
- `get_position(ticker)`
- `submit_order(...)`
- `get_order(order_id)`
- `cancel_order(order_id)`
- `get_order_history(limit)`
- `get_latest_price(ticker)`
- `close_position(ticker)`
- `is_market_open()`

## 7. 配置对象关系

### API settings

来自 `tradingagents/api/config.py`，服务 API/worker/queue。

### DEFAULT_CONFIG

来自 `tradingagents/default_config.py`，服务 TradingAgentsGraph：

- LLM provider/model
- output language
- debate rounds
- checkpoint
- data vendors
- results/reports/cache/memory paths

### TRADINGBOT_CONFIG

来自 `tradingbot/config.py`，服务 broker、risk、scheduler、自动交易：

- broker 类型
- IBKR/Webull/Alpaca 配置
- watchlist
- 仓位比例
- 风控参数
- SQLite db path

Web/API worker 执行分析时，会用用户 `llm_config` 覆盖 `DEFAULT_CONFIG`。交易接口构造 broker/risk 时使用 `TRADINGBOT_CONFIG`，但 Webull per-user token/account 会由 `broker_provider` 动态注入。
