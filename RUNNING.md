# 运行手册

适用分支：`phase/4-dashboard`（含分析框架 + 自动交易机器人 + Streamlit 仪表盘）。

本仓库提供四种入口，按需选用：

| 入口 | 文件 | 用途 |
|---|---|---|
| 交互式 CLI | `cli/main.py`（命令 `tradingagents`） | 选 ticker / 日期 / 模型，跑一次完整分析，结果落到 `reports/` |
| Python API | `main.py` | 在脚本里直接调 `TradingAgentsGraph.propagate()` |
| 自动交易机器人 | `run_bot.py` | 一次性或定时执行：分析 → 风控 → 下单 → 复盘 |
| Streamlit 仪表盘 | `run_dashboard.py` | 浏览器查看持仓 / 业绩 / 风险 / 智能体推理 |

---

## 1. 准备环境

### 1.1 Python

要求 Python ≥ 3.10，推荐 3.13。

```bash
# 任选其一
conda create -n tradingagents python=3.13 && conda activate tradingagents
# 或
uv sync --python /usr/local/bin/python3.13
# 或
python3.13 -m venv .venv && source .venv/bin/activate
```

### 1.2 安装依赖

```bash
pip install .          # 从 pyproject.toml 安装，含 alpaca-py / apscheduler / streamlit / plotly
# 或
uv sync                # 若用 uv
```

安装完成后会注册控制台命令 `tradingagents`（等价于 `python -m cli.main`）。

### 1.3 配置 API 密钥

复制示例文件并填写：

```bash
cp .env.example .env
```

`.env` 至少要给你打算用的一个 LLM provider 配密钥：

```
OPENAI_API_KEY=sk-...
# 二选其一即可，CLI 会按 llm_provider 选择
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
# 数据源
ALPHA_VANTAGE_API_KEY=...   # 可选；缺失时 yfinance 兜底
```

支持的 provider 见 README "Required APIs"。`Ollama` 本地模型不需要密钥，配 `OLLAMA_BASE_URL` 即可。

如果要通过 API 页面保存“用户自己的模型 API key”，还必须配置密钥加密用的 Fernet key：

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

把输出写入 `.env`：

```bash
MODEL_API_KEY_ENCRYPTION_KEY=生成出来的值
```

当前模型密钥优先级：用户保存的加密密钥优先；用户没有保存时，worker 回退使用服务端 `.env` 里的 provider 环境变量。

### 1.4 可选：调默认配置

`.env` 里加 `TRADINGAGENTS_*` 直接覆盖 `tradingagents/default_config.py`：

```
TRADINGAGENTS_LLM_PROVIDER=anthropic
TRADINGAGENTS_DEEP_THINK_LLM=claude-opus-4-7
TRADINGAGENTS_QUICK_THINK_LLM=claude-haiku-4-5-20251001
TRADINGAGENTS_MAX_DEBATE_ROUNDS=2
TRADINGAGENTS_OUTPUT_LANGUAGE=Chinese
TRADINGAGENTS_CHECKPOINT_ENABLED=true
```

值会按默认类型自动 coerce（bool / int / str）。新增字段：在 `default_config.py` 的 `_ENV_OVERRIDES` 加一行即可。

---

## 2. 入口一：交互式 CLI

最常用的方式。一次完整的多智能体分析。

```bash
tradingagents
# 或
python -m cli.main
```

交互流程会问：

1. Ticker（如 `NVDA`、`SPY`、`BTC-USD`、`9988.HK`）
2. 分析日期
3. LLM provider + 模型档位（deep / quick）
4. Analyst 选择（默认全开）
5. 辩论轮次 / 风险讨论轮次
6. 缺失的密钥会现场询问并写回 `.env`

运行时实时打印每个 agent 的进度，最终结果写到：

```
reports/<TICKER>_<YYYYMMDD_HHMMSS>/
├── 1_analysts/{market,sentiment,news,fundamentals}.md
├── 2_research/{bull,bear,manager}.md
├── 3_trading/trader.md
├── 4_risk/{aggressive,conservative,neutral}.md
├── 5_portfolio/decision.md
└── complete_report.md
```

同时追加决策到 `~/.tradingagents/memory/trading_memory.md`，下次跑同 ticker 时自动注入历史教训。

---

## 3. 入口二：Python API

直接在脚本里调用：

```bash
python main.py
```

`main.py` 当前固定跑 `NVDA / 2024-05-10`，按需改：

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
config["max_debate_rounds"] = 2
ta = TradingAgentsGraph(debug=True, config=config)
_, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)

# 落地后复盘（参数是实际收益）
# ta.reflect_and_remember(1000)
```

---

## 4. 入口三：自动交易机器人

在分析之上加 SignalMapper → RiskGate → Broker → Portfolio 的完整执行链。**强烈建议先用 mock broker**：

```bash
export TRADINGBOT_BROKER=mock     # 默认就是 mock，无需密钥
```

### 4.1 一次性运行

```bash
# 跑单个 ticker
python run_bot.py --ticker AAPL --once

# 跑历史日期（回测分析）
python run_bot.py --ticker NVDA --date 2024-05-10 --once

# 跑整个 watchlist（默认 AAPL,MSFT,NVDA,GOOGL,AMZN）
python run_bot.py --once
```

### 4.2 人工审批

下单前停下来等 y/n：

```bash
python run_bot.py --once --approval
```

### 4.3 定时运行（每个工作日跑三班）

```bash
python run_bot.py        # Ctrl-C 退出
```

时间默认（US/Eastern）：
- `08:00` 盘前分析
- `09:35` 提交订单
- `16:30` 盘后复盘（含 `reflect_and_remember` 学习闭环）

调整：`.env` 设 `PRE_MARKET_TIME` / `ORDER_SUBMISSION_TIME` / `POST_MARKET_TIME`。

### 4.4 切到 Alpaca 模拟盘

```bash
export TRADINGBOT_BROKER=alpaca
export ALPACA_API_KEY=...
export ALPACA_API_SECRET=...
export ALPACA_PAPER=true        # 切勿在未验证前设 false
python run_bot.py --ticker AAPL --once
```

### 4.5 风险参数（`.env`）

| 变量 | 默认 | 说明 |
|---|---|---|
| `FULL_POSITION_PCT` | 0.05 | BUY 信号下注比例 |
| `PARTIAL_POSITION_PCT` | 0.03 | OVERWEIGHT 信号下注比例 |
| `PARTIAL_EXIT_PCT` | 0.50 | UNDERWEIGHT 信号减仓比例 |
| `MAX_SINGLE_POSITION_PCT` | 0.10 | 单票最大仓位占比 |
| `MAX_TOTAL_EXPOSURE_PCT` | 0.80 | 总仓位上限 |
| `DAILY_LOSS_LIMIT_PCT` | -0.02 | 日内亏损熔断阈值 |
| `MIN_CASH_RESERVE` | 1000.0 | 永远保留的现金（USD） |

RiskGate 的限制是硬约束，LLM 不能绕过。

---

## 5. 入口四：Streamlit 仪表盘（含登录页）

```bash
python run_dashboard.py
# 或
streamlit run tradingbot/dashboard/app.py
```

打开 `http://localhost:8501`：未登录会先看到 **登录 / 注册** 页（账号密码 + 手机验证码两种登录方式），登录成功后进入五个页面：

- **Portfolio** — 实时持仓 / 资金分布
- **Performance** — 净值曲线 / 回撤 / Sharpe / 胜率
- **Trade History** — 交易明细 + 每笔背后的 agent 推理
- **Agent Reasoning** — 12 个 tab 拆开看每个 agent 的输出；也可现场触发新分析
- **Risk Monitor** — 熔断状态 / 总敞口 / 单票集中度

仪表盘和机器人共享 `~/.tradingagents/tradingbot.db`，机器人是否在运行都能看。侧边栏的 Quick Trade 可以从 UI 直接手动下单。侧边栏顶部显示当前登录用户，"退出登录" 清除会话并回到登录页。

**用户存储**：独立 sqlite 文件 `~/.tradingagents/users.db`（用 `TRADINGBOT_USERS_DB` 覆盖路径）。
**手机验证码**：仓库尚未接入短信通道；开发期间验证码会打印到运行 streamlit 的终端，并在登录页 `st.info` 显示。生产部署前请改 `tradingbot/auth/service.py::send_sms_code` 接入真实 SMS provider。

只想单跑登录/注册页（不进 dashboard）：

```bash
python run_auth.py
# 或
streamlit run tradingbot/dashboard/auth_app.py
```

---

## 6. Docker

```bash
cp .env.example .env  # 先填密钥
docker compose run --rm tradingagents
```

### 6.1 用 Docker 跑分析 API 队列栈

```bash
docker compose up -d postgres redis api worker beat
docker compose logs -f api worker beat
```

默认暴露 API：`http://localhost:8000`。`api` 容器启动前会执行一次 `init_db()`，`beat` 负责周期性调度 queued run，`worker` 负责实际执行分析任务。

调 worker 并发：

```bash
TRADINGAGENTS_WORKER_CONCURRENCY=10 docker compose up -d --scale worker=10 worker
```

上面表示 10 个 worker 容器、每个容器 10 个执行槽，总槽位 100。只有在 provider quota、数据库连接池和机器资源都准备好时才这样配置；否则保持单容器 5 并发更稳。

本地 Ollama 模型：

```bash
docker compose --profile ollama run --rm tradingagents-ollama
```

数据卷 `tradingagents_data` 挂在容器内 `/home/appuser/.tradingagents`，跨容器保留 memory log、checkpoint **以及 users.db**。

### 6.2 用 Docker 跑仪表盘（含登录页）

当前 `Dockerfile` 的 `ENTRYPOINT` 是 CLI (`tradingagents`)，跑 dashboard 时覆盖一下即可：

```bash
docker compose run --rm --service-ports \
  -p 8501:8501 \
  --entrypoint "" tradingagents \
  python -m streamlit run tradingbot/dashboard/app.py \
    --server.address 0.0.0.0 \
    --server.port 8501 \
    --server.headless true
```

打开宿主机 `http://localhost:8501`，先注册再登录。`users.db` 写到 `tradingagents_data` 卷，容器重启不丢用户。

如果要把 dashboard 做成长驻服务，建议在 `docker-compose.yml` 新增一个 service：

```yaml
  dashboard:
    build: .
    entrypoint: ""
    command: >
      python -m streamlit run tradingbot/dashboard/app.py
      --server.address 0.0.0.0
      --server.port 8501
      --server.headless true
    env_file: [.env]
    ports: ["8501:8501"]
    volumes:
      - tradingagents_data:/home/appuser/.tradingagents
    restart: unless-stopped
```

启动：`docker compose up -d dashboard`。

---

## 6A. 服务器部署（裸机 / VM）

```bash
# 1. 同步代码
git clone <repo> && cd TradingAgents
git checkout phase/6-login-page

# 2. Python 环境
uv sync                              # 或 python3.13 -m venv .venv && pip install .

# 3. 配置
cp .env.example .env && vi .env       # 填 LLM / broker / 风控 / TRADINGBOT_USERS_DB

# 4. 启动（前台）
./start.sh dashboard
# 或后台 systemd / pm2 / supervisord（见下）
```

最小 systemd unit：

```ini
# /etc/systemd/system/tradingagents-dashboard.service
[Unit]
Description=TradingAgents Dashboard (Streamlit, with login gate)
After=network.target

[Service]
WorkingDirectory=/opt/TradingAgents
EnvironmentFile=/opt/TradingAgents/.env
ExecStart=/opt/TradingAgents/.venv/bin/python -m streamlit run \
  /opt/TradingAgents/tradingbot/dashboard/app.py \
  --server.address 0.0.0.0 --server.port 8501 --server.headless true
Restart=on-failure
User=tradingagents

[Install]
WantedBy=multi-user.target
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tradingagents-dashboard
```

### Nginx 反向代理（推荐放公网用）

Streamlit 走 WebSocket，必须开 `Upgrade` 头：

```nginx
server {
    listen 443 ssl http2;
    server_name dashboard.example.com;

    ssl_certificate     /etc/letsencrypt/live/dashboard.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/dashboard.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade           $http_upgrade;
        proxy_set_header Connection        "upgrade";
        proxy_read_timeout 86400;
    }
}
```

### 部署前必做的安全清单

1. **HTTPS 必须开启**——登录走明文密码，没有 TLS 等于裸奔。
2. **修改默认密码哈希参数前先评估**：当前 `service.py` 用 `scrypt(n=2**14, r=8, p=1)`，单次 ~50ms，CPU 受限机器要注意。
3. **接真实 SMS provider**：替换 `tradingbot/auth/service.py::send_sms_code`，目前是 `print + logger.warning` 桩。
4. **users.db 备份**：和 `tradingbot.db` 一起放在 `~/.tradingagents/`，定期备份卷或单独 `sqlite3 .backup`。
5. **Streamlit 没有内置 CSRF/速率限制**：公网部署建议 Nginx 加 `limit_req`，或前置 Cloudflare。
6. **会话存储**：当前 `auth_user` 存在 `st.session_state`，重启 streamlit 即失效；如果要"记住我"必须自己加 cookie/token 层。
7. **`.env` 不要提交**，并确保 systemd 单元里 `EnvironmentFile` 文件权限 `chmod 600`。

### 分析 HTTP API 部署补充（`tradingagents.api`）

- **环境区分**：本地开发使用 `TRADINGAGENTS_API_ENV=development`，宿主机进程连接 `DATABASE_URL=postgresql+psycopg://tradingagents:tradingagents@localhost:5432/tradingagents` 和 `REDIS_URL=redis://localhost:6379/0`；Docker Compose 容器内通过 `DOCKER_DATABASE_URL` / `DOCKER_REDIS_URL` 连接服务名 `postgres` / `redis`；生产使用 `TRADINGAGENTS_API_ENV=production` 并显式提供生产 PostgreSQL/Redis 连接。
- **安全敏感部署参数**：本地 HTTP 开发使用 `TRADINGAGENTS_API_ENV=development` 或 `TRADINGAGENTS_API_COOKIE_SECURE=false`；生产 HTTPS 保持 `TRADINGAGENTS_API_COOKIE_SECURE=true`。多租户生产部署保持 `TRADINGAGENTS_API_ALLOW_PRIVATE_BACKEND_URLS=false`；可信本地 LLM/Ollama 部署可设为 `true`。如果修改 `TRADINGAGENTS_API_CSRF_COOKIE_NAME`，构建前端时必须同步设置 `VITE_CSRF_COOKIE_NAME`。
- **本地一键启动**：运行 `./start.sh api` 会启动 Docker PostgreSQL/Redis、初始化 PostgreSQL 表，并启动 FastAPI、Celery worker、Celery beat。脚本保持前台运行；按 `Ctrl-C` 会停止 API/worker/beat，保留数据库容器。另一个终端可运行 `./start.sh api-status` 查看状态，或 `./start.sh api-stop` 停止 API/worker/beat。
- **队列调度**：`POST /runs` 只入库为 `queued`，Celery beat 每 `TRADINGAGENTS_DISPATCH_INTERVAL_SECONDS` 秒触发 dispatcher，把任务从 `queued` 迁到 `dispatching` 并投递给 worker。worker 开始执行后状态变为 `running`，完成后变为 `succeeded/failed/cancelled`。
- **并发容量**：默认 `TRADINGAGENTS_MAX_RUNNING_SYSTEM=100`、`TRADINGAGENTS_MAX_RUNNING_PER_USER=5`、`TRADINGAGENTS_MAX_QUEUED_PER_USER=50`。系统容量按 `dispatching + running` 计数，单用户超过 5 个 active run 后继续创建的 run 会排队；超过 backlog 上限会返回 `429`。
- **worker 并发**：本地 `./start.sh api` 默认 `TRADINGAGENTS_WORKER_CONCURRENCY=5`，且 `prefetch=1`，避免单个 worker 预取太多任务导致用户间不公平。生产要支撑 100 个系统并发时，不建议单机单 worker 开到 100；按机器资源横向扩多个 worker，使所有 worker 的 concurrency 总和约等于系统容量，并持续观察 provider 限流、CPU、内存、数据库连接数。
- **provider 限流**：worker 并发只是本地执行槽位；外部模型 provider 还有单独并发门控，避免 100 个 run 同时打爆同一个 provider。调大系统并发前先确认 provider quota、API key 额度和失败重试策略。
- **租约与心跳**：dispatcher 给 `dispatching` run 设置 lease；worker 执行中定期写 heartbeat。Celery beat 会周期运行 sweeper，过期的 `dispatching` 会回到 `queued`，心跳过期的 `running` 会按剩余 attempts 重排或标记失败。
- **必须走 HTTPS**：API 下发的 `tradingagents_session` cookie 在生产默认 `Secure`，明文 HTTP 下浏览器会丢弃；本地开发通过 `TRADINGAGENTS_API_ENV=development` 自动关闭 Secure cookie，生产**禁止关闭**。
- **CSRF**：状态变更（`POST/PATCH/DELETE`）必须同时携带 cookie `tradingagents_csrf` 与请求头 `X-CSRF-Token`，二者字符串相等。前端 JS 可读 csrf cookie，session cookie 是 `HttpOnly` 拿不到。
- **首位注册即 admin**：表内零用户时 `POST /auth/register` 自动赋 `admin`，其后默认 `viewer`，需 admin 通过 `PATCH /admin/users/{id}` 提升。
- **限流**：`/auth/login` 默认每分钟 5 次（按 IP+username 滑动窗口）。多实例部署需要把 `tradingagents/api/rate_limit.py:RedisBackend` 接进 `get_login_rate_limiter()`，否则各实例计数独立。
- **session 表清理**：`sessions` 永久增长，需要 cron / Celery beat 周期删 `expires_at < now() - 30d` 的行（后续 P1-3 保留策略统一做）。
- **与 Streamlit auth 独立**：API 用自己 PostgreSQL 的 `users` 表，跟 `tradingbot/auth/users.db` 没有任何同步；两边账号需要分别建。

---

## 7. 持久化路径

仓库外一律在 `~/.tradingagents/`：

| 路径 | 内容 |
|---|---|
| `memory/trading_memory.md` | 决策日志（永远开启） |
| `cache/checkpoints/<TICKER>.db` | LangGraph 断点恢复（开启 `--checkpoint` / `TRADINGAGENTS_CHECKPOINT_ENABLED=true`） |
| `logs/` | 每次分析的 JSON 全量日志（仪表盘读这里） |
| `tradingbot.db` | 执行层 SQLite：trades / snapshots / closed_positions |

清断点：`tradingagents analyze --clear-checkpoints`。改路径：`TRADINGAGENTS_RESULTS_DIR` / `TRADINGAGENTS_CACHE_DIR` / `TRADINGAGENTS_MEMORY_LOG_PATH` / `TRADINGBOT_DB_PATH`。

---

## 8. 验证安装

```bash
# 跑测试套件
pytest -m unit                 # 快速单测
pytest -m smoke                # 冒烟

# Smoke：结构化输出
python scripts/smoke_structured_output.py

# 端到端最小跑通（mock broker，约 1–2 分钟）
python run_bot.py --ticker AAPL --once
```

---

## 9. 常见问题

- **"Missing API key for provider X"** — CLI 会主动询问并写回 `.env`；脚本入口需手动 `export`。
- **代理 / 网络** — 设 `HTTPS_PROXY` / `HTTP_PROXY`，会被 LLM 客户端和 yfinance 共用。
- **想换 benchmark** — 非美股自动按交易所后缀映射（`.HK→恒生`、`.T→日经` 等）；强制覆盖用 `TRADINGAGENTS_BENCHMARK_TICKER`。
- **跑一半挂了想续跑** — 开启 checkpoint：`tradingagents analyze --checkpoint`，或脚本里 `config["checkpoint_enabled"] = True`。
- **未追踪的 `apps/` / `tradingagents/api/` / `tradingagents/worker/`** — 那些是 `phase/5-frontend-refactor` 的内容，当前分支不需要，可保留或 `git clean -fd` 清掉。
