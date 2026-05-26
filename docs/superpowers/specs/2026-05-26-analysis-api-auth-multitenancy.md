# 分析 API 鉴权与多租户设计

日期：2026-05-26

分支：`phase/6-login-page`

依赖前置：`2026-05-26-analysis-http-api-design.md`（v1 基础 API）必须先落地。

## 目标

为分析 HTTP API 增加应用层身份系统，把第一版"裸跑"升级为：

- 每个请求都对应一个已认证用户。
- 每个 `analysis_runs` 行归属一个用户，所有 `GET /runs/*` 默认只能看自己的。
- 引入三种角色，作为后续页面级权限与 admin endpoint 的基础。
- **重新设计**一套常规登录系统，**不复用** `tradingbot/auth/`（Streamlit 端的实现保持不动，两者各管各的）。

## 已确认决策

- 用户存储：**新建**独立的用户表，放在分析 API 自己的 PostgreSQL 里（与 `analysis_runs` 同库），不沿用 `tradingbot/auth/users.db`。
- 凭证形态：**仅浏览器 cookie session**。
  - 标准 username + password 登录。
  - 密码哈希算法：scrypt（参数与业界推荐对齐，`n=2**14, r=8, p=1`），随机 16 字节 salt。
  - 服务端 session：opaque session id（`sid_<32 字节随机 base64url>`）存 cookie，服务端 `sessions` 表记账。Cookie 属性 `HttpOnly; Secure; SameSite=Lax; Path=/`。
  - 不暴露 `Authorization: Bearer` token 通道；外部程序化客户端不在第一版考虑。
- 角色数量：三种。具体名称与职责暂定，见下文"角色（待最终确认）"。
- 权限模型：第一版只做**所有权过滤**（user_id 等于当前用户）+ **角色门**（路由级允许/拒绝）。**不做**字段级、行级 ACL。
- 页面级展示/隐藏：暂留 TODO，后续与前端一起设计，见"页面权限（TODO）"。

## 非目标

- 第一版不实现 SSO / OAuth / OIDC。
- 不实现密码找回 / 邮箱验证 / 双因素。
- 不实现程序化 API token / Bearer 鉴权（外部脚本暂不支持，需要时由后续版本补）。
- 不实现组织 / 团队 / 共享 run 的概念。
- 不实现审计日志表（接入点保留，落库表延后到 P2-2 可观测性一起做）。
- 不与 `tradingbot/auth/`（Streamlit 登录系统）做账号同步；两套用户数据相互独立。

## 角色（待最终确认）

第一版引入三个角色。命名只是占位，实际名称在实现前与产品对齐：

| role key      | 占位中文名 | 当前预期能力                                                   |
|---------------|-----------|----------------------------------------------------------------|
| `admin`       | 管理员     | 看所有用户的 run；可访问 `/admin/*`；可创建/吊销任意用户的 token |
| `operator`    | 操作员     | 创建并查看自己的 run；可执行后续 P1-2 的交易审批动作            |
| `viewer`      | 观察员     | 只能查看自己的 run 与 result，不能 `POST /runs`                 |

> **TODO（角色定稿前需要明确）**
> - 三个角色的最终名称（admin / operator / viewer 仅为占位）。
> - operator 与 viewer 的区分是只读 vs 读写，还是按业务面（如"分析使用者"vs"交易审批人"）切分？
> - 是否允许一个用户拥有多个角色（数组）？第一版假设**单角色**，落库 `users.role text`。
> - admin 角色由谁初始化？第一版假设：当 `users` 表为空时，**第一个注册者自动获得 admin**，后续注册默认 `viewer`，由 admin 在 dashboard 手工提升。

## 高层架构

```text
Browser
  └─ Cookie: session_id=sid_xxx (HttpOnly, Secure, SameSite=Lax)
                                  │
                                  ▼
                        FastAPI dependency:
                        get_current_user() -> User
                          ├─ 读 cookie 拿 sid
                          ├─ 查 sessions 表（未过期、未 revoke）
                          └─ join users 表拿 role/enabled
                                  │
                                  ▼
                        require_role("operator")     (路由级)
                                  │
                                  ▼
                        get_scoped_repository(user)  (查询级)
                                  │
                                  ▼
                        PostgreSQL: analysis_runs.user_id 过滤
```

身份解析集中在 `tradingagents/api/auth.py`，路由层声明所需角色，Repository 层只接受已绑定 user 的查询。Worker 进程不参与身份解析；run 表里的 `user_id` 由 API 进程在创建时写入，worker 只透传。

## 用户与会话数据模型

全部建在 PostgreSQL（与 `analysis_runs` 同库），由 SQLAlchemy 管理。

### `users` 表（新建）

```sql
CREATE TABLE users (
    user_id        text PRIMARY KEY,          -- "usr_<ulid>"
    username       text NOT NULL UNIQUE,      -- 大小写不敏感，落库前 lower()
    password_hash  text NOT NULL,             -- scrypt 派生，含参数与 salt 的自描述字符串
    role           text NOT NULL,             -- admin / operator / viewer
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL,
    last_login_at  timestamptz
);

CREATE INDEX idx_users_username_lower ON users(lower(username));
```

- `username`：3-32 字符，仅允许 `[a-zA-Z0-9_.-]`，落库时统一 lower()，登录比较时也 lower()。
- `password_hash`：使用 `hashlib.scrypt` 派生，序列化成自描述字符串 `scrypt$n=16384,r=8,p=1$<salt_b64>$<hash_b64>`，未来调参可平滑兼容。
- `is_active=false`：登录直接拒绝，但保留历史 run 归属关系。

### `sessions` 表（新建）

```sql
CREATE TABLE sessions (
    session_id    text PRIMARY KEY,        -- 客户端持有的完整 sid，存 cookie
    user_id       text NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at    timestamptz NOT NULL,
    last_seen_at  timestamptz NOT NULL,
    expires_at    timestamptz NOT NULL,
    revoked_at    timestamptz,
    user_agent    text,                    -- 仅用于"会话列表"页面，截断 512 字符
    ip_inet       inet                     -- 同上
);

CREATE INDEX idx_sessions_user_id ON sessions(user_id);
CREATE INDEX idx_sessions_expires_at ON sessions(expires_at);
```

- 会话默认 14 天**滑动过期**：每次请求把 `last_seen_at = now()`、`expires_at = now() + 14d`，但只在距上次更新超过 1 分钟时实际写库，避免每请求一写。
- 主动 logout 写 `revoked_at`；revoke 后的 sid 直接 401。
- 定期清理：`expires_at < now() - 30d` 的行由 Celery beat 任务批量删（与后续 P1-3 保留策略共用）。
- `session_id` 直接是 opaque 随机串，**不签 HMAC**——服务端表查得到即有效，查不到即无效，比 HMAC 更简单且支持服务端立即吊销。

## 身份解析依赖

新文件 `tradingagents/api/auth.py`，导出三个 FastAPI 依赖：

- `get_current_user(request, db) -> User`
  - 1. 从 cookie 读 `session_id`。缺失 → `401`。
  - 2. 查 `sessions` 表：不存在 / `revoked_at IS NOT NULL` / `expires_at < now()` → `401`。
  - 3. JOIN `users`：`is_active=false` → `401`。
  - 4. 命中后异步更新 `last_seen_at`/`expires_at`（受 1 分钟节流；记录 user_agent/ip 仅在首次或变更时写）。
  - 5. 返回 `User(user_id, username, role)`。

- `require_role(*roles)` → 返回一个依赖。命中即放行，否则 `403 Forbidden`。

- `get_scoped_repository(session, user) -> AnalysisRunRepository`
  - 对 `admin` 返回不带过滤的全局 repo（用于 `/admin/*` 路由）。
  - 其他角色返回 `user_id` 已绑定的 scoped repo（所有 `get_run` / `list_events` / `get_result` 自动加 `WHERE user_id = ?`）。

### CSRF 防护

因为 cookie 是 `SameSite=Lax`，跨站第三方 POST 不会带 cookie，已经覆盖了主要 CSRF 面。对 state-changing 路由（`POST/PATCH/DELETE`）额外加一道：

- 登录成功时下发第二个 cookie `csrf_token`（**不**带 `HttpOnly`，前端 JS 可读）。
- 状态变更请求必须带请求头 `X-CSRF-Token`，与 cookie 中的 `csrf_token` 字符串相等（double-submit cookie 模式）。
- 不一致 → `403`。
- `GET` 请求不校验 CSRF。

## Repository 改动

`AnalysisRunRepository` 增加 `user_id` 可选参数，默认 `None`（= 系统/无过滤视图）：

```python
class AnalysisRunRepository:
    def __init__(self, session: Session, user_id: str | None = None):
        # user_id is None 表示系统视图（worker / admin 全局查询）
        ...

    def create_run(self, ticker, trade_date, asset_type, analysts) -> AnalysisRun:
        # 必须 user_id 非空；写库时落 self.user_id
        ...

    def get_run(self, run_id) -> AnalysisRun | None:
        # 自动加 WHERE user_id = self.user_id；user_id is None 时跳过过滤
        ...
```

**实现注意（针对当前 v1 代码）**：

- 现 `get_run` / `get_result` 使用 `session.get(Model, pk)` 主键查询，加 owner 过滤后必须改写为 `select(Model).where(Model.run_id == run_id, Model.user_id == self.user_id)` 形式。`mark_running` / `store_success` / `store_failure` / `set_celery_task_id` 内部已经 `require_run`，会自动继承过滤。
- `__init__` 的 `user_id` 必须**有默认值 `None`**：worker 的 `jobs.py` 和现有所有测试现在都用 `AnalysisRunRepository(session)` 单参构造，加默认值后无需 mass-edit；只有路由层显式传入用户身份即可启用过滤。
- 不引入第二个类（如 `SystemRepository`）。"系统视图" 由 `user_id=None` 单一状态表示，避免双类型造成调用方分裂。
- worker 的 `claim_queued_run`（原子领取 queued run）保持不变，与 owner 过滤无关 —— worker 是系统身份，按 `run_id` 直接领取；row 上的 `user_id` 是数据归属，不影响 worker 调度。
- 越权访问他人 run：scoped repo 的 `get_run` 返回 `None` → 路由层走原有 `404`，无需额外分支。

## API 面

### 注册 / 登录 / 登出

- `POST /auth/register`
  - 请求体 `{ "username": "...", "password": "..." }`。
  - 校验：username 正则、密码长度 ≥ 8、复杂度规则（≥ 1 字母 + ≥ 1 数字；其他强度策略后续再加）。
  - 副作用：写 `users`。第一个注册者获得 `admin`，后续默认 `viewer`（见"角色（待最终确认）"）。
  - 返回 `201`，不自动登录（避免注册接口同时返回会话引发的滥用）。

- `POST /auth/login`
  - 请求体 `{ "username": "...", "password": "..." }`。
  - 失败：恒定耗时返回 `401`，**不区分**用户名不存在 vs 密码错（防枚举）。
  - 失败计数：同一 IP / username 一分钟超过 5 次 → 临时 429（基于内存 + Redis 滑动窗口，实现细节延后）。
  - 成功：插入 `sessions` 行，下发 `session_id` 与 `csrf_token` 两个 cookie，更新 `users.last_login_at`。
  - 返回 `{ "user_id", "username", "role" }`。

- `POST /auth/logout`
  - 设置当前 session 的 `revoked_at`，清空两个 cookie（`Set-Cookie: ...; Max-Age=0`）。
  - 始终返回 `204`，即使本来就未登录。

- `GET /auth/me`
  - 鉴权后返回 `{ "user_id", "username", "role" }`，未登录返回 `401`。
  - 前端启动时调一次用来判断登录态。

- `POST /auth/change-password`
  - 请求体 `{ "current_password", "new_password" }`。
  - 成功后**吊销当前用户的其他所有 session**（保留当前会话），强制其他终端重登。

### 现有 runs 路由的改动

所有 `POST /runs`、`GET /runs/*` 路由：

- 增加 `Depends(get_current_user)` 与 `Depends(require_role("admin","operator"))`（写）或 `require_role("admin","operator","viewer")`（读）。
- 使用 `get_scoped_repository`，自动按 owner 过滤；非 owner 访问别人 run 一律 `404`（不是 `403`，避免泄露 run_id 存在性）。

### SSE 鉴权时序（`GET /runs/{run_id}/events`）

当前 `stream_events` 使用 `get_stream_session_factory()` 每次轮询打开独立 session，避免长连接持有同一个 dependency-injected session。鉴权改造必须保留这个结构：

- **鉴权 + owner 绑定只在握手时校验一次**：handler 入口 `Depends(get_current_user)` + `Depends(require_role(...))` 通过后，`current_user.user_id` 闭包进 `event_generator`。
- **初始 404 检查走 scoped repo**：`stream_session_factory()` 开 session，构造 `AnalysisRunRepository(stream_session, user_id=current_user.user_id)`，`get_run` 拿不到（run 不存在 / 非 owner）→ 抛 `404`，两种情况返回同一响应。
- **轮询循环内继续 scoped**：generator 每次 `stream_session_factory()` 重开 session 后，构造的 repo 必须同样带 `user_id=current_user.user_id`，避免长流途中读到他人事件。
- **会话过期不强制断流**：SSE 一旦建立，认证状态以"握手时刻"为准（与 EventSource 协议无心跳鉴权一致）。如需"实时吊销"，列入后续事项：generator 每 N 轮额外查 `sessions` 表 ping 当前 sid，发现 `revoked_at` 非空则关闭流。
- **CSRF 不适用于 SSE**：与全局一致，GET 一律不校验 CSRF。

### Admin 接口（预留骨架）

- `GET /admin/users` — 列出所有用户与角色。
- `PATCH /admin/users/{user_id}` — 修改 `role` / `is_active`。
- `POST /admin/users/{user_id}/sessions:revoke-all` — 强制吊销该用户所有会话（含自己）。
- `GET /admin/runs?status=&user_id=` — 全局 run 视图。

所有 `/admin/*` 路由统一挂 `require_role("admin")`。

## 页面权限（TODO）

> 角色与页面的对应矩阵需要等 dashboard 改造一起定，这里只列出已识别的待决问题：

- [ ] **新建分析按钮**：viewer 是否隐藏，还是显示但 disabled + tooltip？
- [ ] **侧边栏 "Risk" / "Trades" 页面**：是否仅 operator + admin 可见？
- [ ] **"Agent Reasoning" 页**：viewer 看不看得到完整 reports？还是只看 final decision？
- [ ] **"Admin" 入口**：是否做成独立顶层导航项，还是塞进设置面板？
- [ ] **用户管理页**：admin 专属页面，UI 是否在 Streamlit 内做（最快）还是延后到真正前端？
- [ ] **未登录态**：是直接重定向 `/login`，还是允许 anonymous 看公共首页？
- [ ] **角色提升的 UX**：admin 在用户列表上点 role 下拉框？还是单独的 invite 流程？

实现时这一块**全部留 TODO，不在本 spec 的第一轮交付里做**。第一轮只保证后端路由权限正确，前端页面照旧渲染（即所有页面都显示，无权限的按钮点击后由后端返回 403）。

## 数据库 schema 变更（PostgreSQL 侧）

`analysis_runs` 增加：

```sql
ALTER TABLE analysis_runs ADD COLUMN user_id text NOT NULL DEFAULT '__system__';
ALTER TABLE analysis_runs ALTER COLUMN user_id DROP DEFAULT;
CREATE INDEX idx_analysis_runs_user_id_created_at
    ON analysis_runs(user_id, created_at DESC);
```

历史数据：v1 上线时 `user_id` 全为 `__system__`，由 admin 后续手动归属或保留为系统级。

## 配置

新增环境变量：

- `TRADINGAGENTS_API_SESSION_TTL_DAYS`：会话滑动过期天数，默认 14。
- `TRADINGAGENTS_API_SESSION_COOKIE_NAME`：默认 `tradingagents_session`。
- `TRADINGAGENTS_API_CSRF_COOKIE_NAME`：默认 `tradingagents_csrf`。
- `TRADINGAGENTS_API_COOKIE_SECURE`：默认 `true`；本地开发可设为 `false`。
- `TRADINGAGENTS_API_COOKIE_DOMAIN`：可选，跨子域部署时设置。
- `TRADINGAGENTS_API_LOGIN_RATE_LIMIT_PER_MIN`：默认 `5`。

不再需要 HMAC 共享密钥——session 是 opaque 服务端表，无需签名。

## 错误处理

- 缺失 / 过期 / 已吊销 session：`401 Unauthorized`，body `{"detail":"authentication required"}`。
- 登录失败（用户名或密码错）：`401`，body `{"detail":"invalid credentials"}`，恒定耗时返回。
- 登录限流命中：`429 Too Many Requests`，附 `Retry-After`。
- 角色不足：`403 Forbidden`，body `{"detail":"role required"}`（不暴露所需具体角色）。
- 越权访问他人 run：返回 `404`（与 run 不存在同响应）。
- CSRF 校验失败：`403`，body `{"detail":"csrf check failed"}`。

## 测试策略

最低测试覆盖：

- `POST /auth/register` 正确写库；用户名重复返回 409；弱密码返回 422。
- `POST /auth/register` 首位用户被赋 admin，第二位为 viewer。
- `POST /auth/login` 成功下发两个 cookie，写入 sessions 行；失败用户名 vs 密码错返回相同响应。
- 登录限流：同一 IP 一分钟 6 次后返回 429。
- `POST /auth/logout` 写 revoked_at 并清 cookie，再次访问受保护路由 → 401。
- `GET /auth/me` 无 session → 401；有 session → 返回当前用户。
- `POST /auth/change-password` 成功后其他 session 全部失效，当前 session 仍可用。
- 未携带 cookie 访问 `POST /runs` → 401。
- viewer 访问 `POST /runs` → 403；operator 访问 → 202，落库 `user_id` 正确。
- 用户 A 不能 `GET` 用户 B 的 run → 404。
- admin 可以 `GET` 任意用户的 run → 200。
- CSRF：合法 cookie 但无 `X-CSRF-Token` 的 POST → 403；GET 不受影响。
- session 过期（构造 `expires_at < now()`）→ 401。
- 滑动过期：连续访问后 `expires_at` 被前移。
- repository scoped 模式自动加 `WHERE user_id =`。
- `__system__` 历史数据对普通用户不可见，对 admin 可见。

测试不能调用真实 LLM 或外部 provider。鉴权测试用 in-memory SQLite，所有 cookie 操作走 FastAPI `TestClient` 的内置 cookie jar。

## 部署与运维说明

- 生产必须走 HTTPS，否则 `Secure` cookie 不下发；本地开发把 `TRADINGAGENTS_API_COOKIE_SECURE=false`。
- cookie 名称与域名通过环境变量配置，多环境（dev/staging/prod）共用浏览器时不会串。
- 日志必须过滤 `Cookie` / `Set-Cookie` 头与请求体中的 `password` / `current_password` / `new_password` 字段；统一在 `tradingagents/api/logging.py` 做。
- `sessions` 表清理：Celery beat 每日删 `expires_at < now() - 30d` 的行，避免无限增长。
- 与 `tradingbot/auth/`（Streamlit）数据完全独立；两边的用户需要分别注册，不要试图做账号同步。

## 第一版之后的后续事项

- 程序化 API token（Bearer）通道，绑定 scope。
- 审计日志表（哪个 user_id 在何时调用了哪个 endpoint）。
- 真正的多角色（数组形态）与权限继承。
- SSO / OIDC 接入；TOTP / WebAuthn 二因素。
- 密码找回 / 邮箱验证。
- 页面级权限矩阵（见上文 TODO）落地。
- 与 `tradingbot/auth/` 的账号统一（迁移工具或共享身份服务）。
