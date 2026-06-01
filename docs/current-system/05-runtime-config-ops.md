# 05 运行、配置与排障

## 1. 本地开发最常用启动顺序

先准备 Python 和依赖：

```bash
uv sync
```

复制配置：

```bash
cp .env.example .env
```

至少配置：

- `DATABASE_URL`
- `REDIS_URL`
- 一个 LLM provider 的 API key，或使用 Ollama。
- `MODEL_API_KEY_ENCRYPTION_KEY`，如果要在页面保存用户 API key 或 Webull secret。

生成 Fernet key：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

启动 API 队列栈：

```bash
./start.sh api
```

启动桌面端：

```bash
./scripts/start_frontend_dev.sh
```

只启动浏览器 Vite：

```bash
FRONTEND_TARGET=browser ./scripts/start_frontend_dev.sh
```

## 2. `start.sh api` 做什么

`./start.sh api` 大致会：

1. 加载 `.env`。
2. 检查 `.venv/bin/python`。
3. 启动 Docker PostgreSQL/Redis。
4. 执行 API DB 初始化。
5. 启动 Uvicorn FastAPI。
6. 启动 Celery worker。
7. 启动 Celery beat。

常用辅助命令：

```bash
./start.sh api-status
./start.sh api-stop
```

## 3. 其他入口

CLI：

```bash
tradingagents
python -m cli.main
```

Python API 示例：

```bash
python main.py
```

自动交易机器人：

```bash
python run_bot.py --ticker AAPL --once
python run_bot.py --once --approval
python run_bot.py
```

Streamlit dashboard：

```bash
python run_dashboard.py
python run_auth.py
```

IBKR server connector：

```bash
python run_broker.py
```

手动 sidecar 调试：

```bash
python run_sidecar.py --host 127.0.0.1 --port 8788 --token devtoken
```

## 4. 端口

| 组件 | 默认端口 |
| --- | --- |
| FastAPI | 8000 |
| Vite | 5173 |
| Streamlit dashboard | 8501 |
| PostgreSQL | 5432 |
| Redis | 6379 |
| sidecar 手动模式 | 8788 |
| sidecar Electron 模式 | 随机空闲 loopback 端口 |
| TWS paper | 7497 |
| TWS live | 7496 |
| IB Gateway paper | 4002 |
| IB Gateway live | 4001 |

## 5. LLM 配置

默认分析配置在 `tradingagents/default_config.py`。

支持环境变量覆盖：

- `TRADINGAGENTS_LLM_PROVIDER`
- `TRADINGAGENTS_DEEP_THINK_LLM`
- `TRADINGAGENTS_QUICK_THINK_LLM`
- `TRADINGAGENTS_LLM_BACKEND_URL`
- `TRADINGAGENTS_OUTPUT_LANGUAGE`
- `TRADINGAGENTS_MAX_DEBATE_ROUNDS`
- `TRADINGAGENTS_MAX_RISK_ROUNDS`
- `TRADINGAGENTS_CHECKPOINT_ENABLED`
- `TRADINGAGENTS_BENCHMARK_TICKER`

Web/API 里更重要的是用户模型设置：

- run 创建时会把用户设置 snapshot 存进 `analysis_runs.llm_config`。
- worker 执行时使用这个 snapshot。
- 这避免用户后续修改模型设置影响已排队 run。

## 6. 数据源配置

数据源默认在 `DEFAULT_CONFIG`：

```python
data_vendors = {
  "core_stock_apis": "yfinance",
  "technical_indicators": "yfinance",
  "fundamental_data": "yfinance",
  "news_data": "yfinance",
}
```

可以通过 `tool_vendors` 单独覆盖某个工具。

Alpha Vantage 需要 `ALPHA_VANTAGE_API_KEY`。当 Alpha Vantage rate limit 时，路由层会 fallback 到其他 vendor。

## 7. TradingBot/Broker 配置

`tradingbot/config.py` 读取：

### Broker

- `TRADINGBOT_BROKER`：`mock/alpaca/ibkr/webull`。
- `ALPACA_API_KEY`
- `ALPACA_API_SECRET`
- `ALPACA_PAPER`
- `IBKR_PAPER`

### IBKR

- `IBKR_HOST`
- `IBKR_PORT`
- `IBKR_CLIENT_ID`
- `IBKR_ACCOUNT_ID`
- `IBKR_MARKET_DATA_TYPE`
- `IBKR_AUTO_PROPOSE`
- `IBKR_CMD_QUEUE`

### Webull

- `WEBULL_APP_KEY`
- `WEBULL_APP_SECRET`
- `WEBULL_REGION`
- `WEBULL_ENDPOINT`
- `WEBULL_CONNECT_TIMEOUT`
- `WEBULL_READ_TIMEOUT`
- `WEBULL_CLIENT_ID`
- `WEBULL_CLIENT_SECRET`
- `WEBULL_REDIRECT_URI`
- `WEBULL_SCOPE`
- `WEBULL_OAUTH_BASE`
- `WEBULL_POST_AUTH_REDIRECT`

说明：

- OAuth 模式使用平台级 Webull app/client 配置。
- API key 模式使用用户在页面提交的 app_key/app_secret，并加密存 DB。
- per-user token/account_id 会在 request time 注入，不从 env 直接读取。

### 风控和仓位

- `FULL_POSITION_PCT`
- `PARTIAL_POSITION_PCT`
- `PARTIAL_EXIT_PCT`
- `MAX_SINGLE_POSITION_PCT`
- `MAX_TOTAL_EXPOSURE_PCT`
- `DAILY_LOSS_LIMIT_PCT`
- `MIN_CASH_RESERVE`

## 8. 依赖和 optional extra

后端核心依赖在 `pyproject.toml`。

Webull SDK 是 optional extra：

```bash
pip install ".[webull]"
```

如果运行 Webull 实盘/模拟 API 路径但没装 SDK，`SdkWebullClient` 会在运行时失败。

前端使用 pnpm：

```bash
cd web
pnpm install
```

## 9. 测试

pytest 配置在 `pyproject.toml`：

```bash
pytest
```

常用局部测试：

```bash
pytest tests/api/test_broker_router.py
pytest tests/api/test_broker_oauth.py
pytest tests/test_webull_broker.py
pytest tests/test_webull_client.py
pytest tests/worker/test_dispatcher.py
pytest tests/worker/test_sweeper.py
pytest tests/graph/test_cancellable_nodes.py
```

前端逻辑测试：

```bash
cd web
node scripts/proposalEligibility.test.mjs
node scripts/manualTradeFlow.test.mjs
```

测试环境会设置 SQLite memory DB、dummy API keys，并关闭 Secure cookie。

## 10. 常见问题

### 10.1 页面登录后仍跳回登录

检查：

- API 是否跑在 HTTP。
- `TRADINGAGENTS_API_COOKIE_SECURE=false` 是否设置。
- 浏览器 devtools 里是否保存了 `tradingagents_session`。
- 前端请求是否带 `withCredentials`。

### 10.2 创建分析后一直 queued

说明 API 已写入 run，但 worker 调度链没工作。

检查：

- Celery beat 是否启动。
- Celery worker 是否启动。
- Redis 是否可用。
- `./start.sh api-status`。
- `analysis_runs.status` 是否有 dispatching/running。

### 10.3 生成交易建议提示 Hold no action

说明最终 `decision` 是 `HOLD` 或无法识别信号被 fail-safe 当成 HOLD。当前设计不为 HOLD 创建交易建议。

### 10.4 生成交易建议提示 price unavailable

说明当前 active broker 报价不可用。

检查：

- `/broker/status` 当前 active broker 是 Webull 还是 IBKR。
- Webull 是否 connected 且 account_id 存在。
- IBKR 是否有行情权限或 delayed data 设置。
- ticker 是否在 broker 支持范围内。
- 服务端日志中的 broker/SDK 原始异常。

### 10.5 computed quantity < 1 share

常见原因：

- 买入：配置仓位比例太小、现金太少、股价太高。
- 卖出：没有该 ticker 持仓，或持仓按比例卖出后不足 1 股。
- 风控把数量调整到不足 1 股。

当前 proposal builder 最终按整股取 `int(qty)`。

### 10.6 Webull preview 报错

优先检查：

- Webull SDK 是否安装。
- 用户 API key/OAuth token 是否有效。
- account_id 是否正确。
- region/paper/endpoint 是否和凭据环境一致。
- instrument_id 是否能解析。
- 服务端日志是否有 Webull SDK 原始响应。

### 10.7 Electron 进来显示 IBKR 连接面板，但我想走 Webull

正常情况下，只要 server `/broker/status` 是 connected Webull，`BrokerGate` 会放行，并且交易建议/快速下单优先走 Webull。若没有放行，检查：

- `GET /broker/oauth/webull/status`
- `GET /broker/status`
- 当前登录用户是否就是绑定 Webull 的用户。
- Webull credential 是否 `status=connected`。

### 10.8 IBKR 本地连接失败

检查：

- TWS/IB Gateway 是否已登录。
- API socket 是否启用。
- 端口是否正确：paper TWS 7497，paper Gateway 4002。
- client id 是否冲突。
- Electron ConnectPanel 的 discover 是否能扫到端口。

## 11. 当前工作区注意

运行 `git status --short` 可以看到当前工作区已有多处未提交改动，包括 Webull、broker、前端交易流、worker、测试和启动脚本。本文档按当前工作区文件状态编写，没有回滚这些改动。

文档只新增 `docs/current-system/` 下的文件。
