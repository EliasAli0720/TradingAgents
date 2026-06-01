# 01 API、认证与数据层

## 1. FastAPI 入口

API 入口在 `tradingagents/api/app.py`。

启动后的主要动作：

1. 创建 `FastAPI(title="TradingAgents Analysis API")`。
2. 加载 `CsrfMiddleware`。
3. 注册 router：
   - health
   - auth
   - settings
   - runs
   - admin
   - capacity
   - broker
   - recommendations
   - broker_oauth
4. startup 时调用 `init_db()`。

典型启动方式：

```bash
uvicorn tradingagents.api.app:app --host 127.0.0.1 --port 8000
```

项目脚本里一般用：

```bash
./start.sh api
```

`/health` 当前返回静态 `{"status":"ok","postgres":"ok","redis":"ok"}`，它不实际探测 PostgreSQL 或 Redis。

## 2. API 配置

配置读取在 `tradingagents/api/config.py`。

硬依赖：

- `DATABASE_URL`：必须存在，否则 import API config 时会抛错。

常用配置：

| 环境变量 | 默认 | 作用 |
| --- | --- | --- |
| `DATABASE_URL` | 无 | API 主库 URL，生产通常 PostgreSQL |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker/backend、SSE pubsub、IBKR connector |
| `MODEL_API_KEY_ENCRYPTION_KEY` | 无 | Fernet key，用于加密用户 LLM key 和 Webull secret |
| `TRADINGAGENTS_API_COOKIE_SECURE` | `true` | cookie 是否带 Secure |
| `TRADINGAGENTS_API_SESSION_TTL_DAYS` | `14` | session 有效天数 |
| `TRADINGAGENTS_MAX_RUNNING_SYSTEM` | `100` | dispatcher 系统级运行容量 |
| `TRADINGAGENTS_MAX_RUNNING_PER_USER` | `5` | dispatcher 用户级运行容量 |
| `TRADINGAGENTS_MAX_QUEUED_PER_USER` | `50` | 用户 backlog 限制 |
| `TRADINGAGENTS_RUN_LEASE_SECONDS` | `600` | dispatching lease |
| `TRADINGAGENTS_WORKER_HEARTBEAT_SECONDS` | `10` | worker 心跳间隔 |
| `TRADINGAGENTS_WORKER_STALE_AFTER_SECONDS` | `90` | sweeper 判定 stale running 的阈值 |

本地 HTTP 调试时，如果浏览器无法保存 session cookie，优先检查 `TRADINGAGENTS_API_COOKIE_SECURE=false` 是否设置。测试 fixture 也是这样关掉 secure cookie。

## 3. 数据库初始化

数据库层在 `tradingagents/api/db.py`。

初始化逻辑：

```text
init_db()
  -> import models
  -> Base.metadata.create_all(engine)
  -> ensure_additive_schema(engine)
  -> seed LLM model catalog
```

需要注意：

- 当前不是 Alembic 迁移体系。
- `ensure_additive_schema()` 只做一些追加字段和修补，不保证复杂 schema 变更可逆或可审计。
- 测试环境可用 SQLite memory，并会打开 foreign keys。
- 生产/开发主路径是 SQLAlchemy ORM + PostgreSQL。

## 4. 认证机制

认证不是 JWT，而是服务端 session cookie。

登录成功时，`tradingagents/api/routers/auth.py` 写两个 cookie：

- `tradingagents_session`
  - HttpOnly
  - 存 session id
  - 后端用它查 `sessions` 表
- `tradingagents_csrf`
  - 非 HttpOnly
  - 前端 JS 读取后放进 `X-CSRF-Token`

CSRF 规则：

- `GET/HEAD/OPTIONS` 跳过。
- `/auth/login` 和 `/auth/register` 豁免，因为登录前没有 CSRF cookie。
- 其他 state-changing 请求如果带 session cookie，就必须同时带同值 `X-CSRF-Token`。

前端实现：

- `web/src/api/client.ts` 创建 axios client。
- `withCredentials=true`。
- request interceptor 对 `post/put/patch/delete` 自动读 `tradingagents_csrf` 并加 header。
- response interceptor 遇到 401 会跳到 `/login?next=...`。

## 5. 用户和角色

注册逻辑：

- 第一位用户自动是 `admin`。
- 后续用户默认是 `viewer`。
- 用户名会转小写并校验 3 到 32 位。
- 密码至少 8 位，且需要包含字母和数字。
- 密码用 `hashlib.scrypt` 生成 hash。

角色：

| 角色 | 能力 |
| --- | --- |
| `admin` | 管理用户、跨用户 run、交易操作 |
| `operator` | 创建/取消分析、交易预览、下单、审批 |
| `viewer` | 登录和查看允许访问的数据 |

`require_role()` 不满足时返回 403。

admin 和普通用户的隔离方式也要注意：

- 多数 repository 对 admin 传 `user_id=None`，表示不加用户 scope。
- 普通用户传自己的 `user_id`，查不到别人的资源通常表现为 404，而不是 403。

## 6. 主要 API 路由

### Auth

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/auth/register` | 注册用户 |
| `POST` | `/auth/login` | 登录并设置 session/csrf cookie |
| `POST` | `/auth/logout` | revoke 当前 session，清 cookie |
| `GET` | `/auth/me` | 当前用户 |
| `POST` | `/auth/change-password` | 修改密码，并 revoke 其他 session |

登录有进程内限流，默认同 IP + username 每分钟 5 次。生产多副本时这不是全局限流。

### Settings

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `PUT` | `/settings/preferences` | 保存用户语言 |
| `GET` | `/settings/model/options` | LLM provider/model catalog |
| `GET` | `/settings/model` | 当前用户模型设置 |
| `PUT` | `/settings/model` | 保存模型设置和可选 API key |
| `DELETE` | `/settings/model/api-key` | 清除用户模型 API key |
| `POST` | `/settings/model/validate` | 校验当前模型设置是否可用 |
| `GET` | `/settings/translation/options` | 翻译模型选项 |
| `GET` | `/settings/translation` | 当前翻译设置 |
| `PUT` | `/settings/translation` | 保存翻译设置 |
| `DELETE` | `/settings/translation/api-key` | 清除翻译 API key |
| `POST` | `/settings/translation/validate` | 校验翻译模型 |

API key 优先级：

```text
用户 DB 加密 key
  -> provider 不需要 key
  -> 服务端环境变量 key
  -> missing
```

### Runs

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/runs` | 创建 queued run，返回 202 |
| `POST` | `/runs/{run_id}/cancel` | 取消 run |
| `GET` | `/runs/{run_id}` | run 状态 |
| `GET` | `/runs/{run_id}/result` | 成功后的结果 |
| `GET` | `/runs/{run_id}/artifacts` | artifact 元数据列表 |
| `GET` | `/runs/{run_id}/artifacts/{artifact_id}` | 单个 artifact 元数据 |
| `GET` | `/runs/{run_id}/events` | SSE 事件流 |

`POST /runs` 只入库排队，不直接 Celery enqueue。

### Recommendations

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/recommendations/watchlist` | 当前 watchlist |
| `PUT` | `/recommendations/watchlist` | 保存 watchlist |
| `POST` | `/recommendations/generate` | 生成推荐批次 |
| `GET` | `/recommendations/batches` | 批次列表 |
| `GET` | `/recommendations/batches/{batch_id}` | 批次详情 |
| `POST` | `/recommendations/batches/{batch_id}/analyze` | 推荐项转分析 run |

### Broker

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/broker/status` | 当前用户 active broker 状态 |
| `GET` | `/broker/account` | 当前 broker 账户 |
| `GET` | `/broker/positions` | 当前 broker 持仓 |
| `GET` | `/broker/orders` | 服务端订单 mirror |
| `GET` | `/broker/orders/{order_id}` | 单个 mirror order |
| `POST` | `/broker/orders/preview` | 预览订单保证金/费用 |
| `POST` | `/broker/orders` | 服务端直接下单并 mirror |
| `POST` | `/broker/orders/{order_id}/cancel` | 取消 broker order |
| `GET` | `/broker/approvals` | 审批列表 |
| `POST` | `/broker/approvals` | 从分析 run 创建交易建议 |
| `POST` | `/broker/approvals/{id}/approve` | 批准并执行 |
| `POST` | `/broker/approvals/{id}/reject` | 拒绝 |
| `POST` | `/broker/local/proposals` | 桌面本地 IBKR 快照生成建议 |
| `POST` | `/broker/approvals/{id}/executed` | 记录本地 sidecar 已执行订单 |
| `POST` | `/broker/orders/manual` | 记录手动本地下单 mirror |
| `POST` | `/broker/orders/{id}/status` | 更新本地订单 mirror 状态 |
| `POST` | `/broker/snapshot` | 推送组合快照 |
| `GET` | `/broker/performance` | 业绩指标 |
| `GET` | `/broker/trades` | 交易历史和已平仓统计 |
| `POST` | `/broker/refresh` | 刷新 broker 状态 |

### Webull OAuth/API key

prefix 是 `/broker/oauth/webull`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/authorize` | 返回 Webull 授权 URL |
| `POST` | `/api-key` | 用户提交 app_key/app_secret 直连 |
| `GET` | `/callback` | OAuth 回调，换 token 并保存 |
| `POST` | `/refresh` | 手动刷新 OAuth token |
| `POST` | `/disconnect` | revoke 本用户 Webull credential |
| `GET` | `/status` | 本用户 Webull 连接状态 |

OAuth callback 用加密 state 绑定 user_id，不依赖当前浏览器登录 cookie。

### Admin

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/admin/users` | 用户列表 |
| `PATCH` | `/admin/users/{user_id}` | 修改用户角色/启用状态等 |
| `POST` | `/admin/users/{user_id}/sessions:revoke-all` | revoke 用户所有 session |
| `GET` | `/admin/runs` | 跨用户 run 列表 |
| `GET` | `/admin/capacity` | 队列容量快照 |

## 7. Repository 职责

| Repository | 责任 |
| --- | --- |
| `AnalysisRunRepository` | run 状态机、事件、进度、artifact、result、translation |
| `UserRepository` | 用户创建、密码 hash、认证、角色基础字段 |
| `SessionRepository` | session 创建、续期、revoke |
| `UserModelSettingsRepository` | 用户分析模型设置、API key 加密存储和快照 |
| `UserTranslationSettingsRepository` | 用户翻译模型设置 |
| `LLMModelCatalogRepository` | provider/model catalog seed 和校验 |
| `RecommendationRepository` | watchlist、推荐批次、推荐项、推荐项和 run 状态同步 |
| `BrokerRepository` | broker status、trade approval 状态机、order mirror |
| `BrokerCredentialRepository` | per-user Webull credential 加密存储、refresh/revoke/expired |
| `PortfolioRepository` | 按 `(user, account, broker)` 聚合订单和快照 |
| `AnalysisMemoryRepository` | Web/API 下的分析记忆和反思记录 |

## 8. 关键错误和边界

- 未登录通常 401。
- 角色不足返回 403。
- CSRF 失败返回 403。
- `POST /runs` 未配置模型返回 409。
- 容量不足返回 429。
- run 不存在返回 404。
- run 未完成读 result 返回 409。
- run failed 读 result 返回 409，detail 是失败原因。
- Webull OAuth state 超时返回 400，TTL 10 分钟。
- Webull API key 多账户但没传 `account_id` 返回 409。
- broker live 调用中参数错误一般 422，broker/SDK 异常一般 502。
