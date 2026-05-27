# 当前版本 API 接口列表

本文档记录当前代码实现中的 API 接口，基于 `tradingagents/api` 下的 FastAPI 路由整理。

## 基础信息

- 默认本地地址：`http://127.0.0.1:8000`
- OpenAPI 文档：`GET /docs`
- OpenAPI JSON：`GET /openapi.json`
- ReDoc 文档：`GET /redoc`

## 认证约定

- 登录成功后服务端写入两个 Cookie：
  - `tradingagents_session`：会话 Cookie，`HttpOnly`
  - `tradingagents_csrf`：CSRF Cookie，前端需要读取后放入请求头
- 除 `GET`、`HEAD`、`OPTIONS`、`POST /auth/login`、`POST /auth/register` 外，携带登录态的写操作都需要请求头：
  - `X-CSRF-Token: <tradingagents_csrf cookie 的值>`
- 用户角色：
  - `admin`：管理员，可查看和管理所有用户、所有分析任务
  - `operator`：操作员，可创建、取消自己的分析任务
  - `viewer`：只读用户
- 非管理员访问分析任务时只允许访问自己的任务；无权限或不存在统一返回 `404`。

## 健康检查

### GET /health

无需登录。用于检查 API 服务是否可访问。

响应：

```json
{
  "status": "ok",
  "postgres": "ok",
  "redis": "ok"
}
```

## 认证接口

### POST /auth/register

无需登录。注册用户。系统中第一个用户自动成为 `admin`，后续用户默认为 `viewer`。

请求体：

```json
{
  "username": "admin",
  "password": "password"
}
```

成功响应：`201`

```json
{
  "user_id": "uuid",
  "username": "admin",
  "role": "admin"
}
```

常见错误：

- `409`：用户名已存在
- `422`：用户名不合法或密码强度不足

### POST /auth/login

无需登录。登录成功后写入会话 Cookie 和 CSRF Cookie。

请求体：

```json
{
  "username": "admin",
  "password": "password"
}
```

成功响应：`200`

```json
{
  "user_id": "uuid",
  "username": "admin",
  "role": "admin"
}
```

常见错误：

- `401`：用户名或密码错误
- `429`：登录尝试过于频繁

### POST /auth/logout

需要登录和 CSRF。注销当前会话并清除认证 Cookie。

成功响应：`204`

### GET /auth/me

需要登录。获取当前登录用户信息。

成功响应：`200`

```json
{
  "user_id": "uuid",
  "username": "admin",
  "role": "admin"
}
```

### POST /auth/change-password

需要登录和 CSRF。修改当前用户密码，并撤销当前会话以外的其它会话。

请求体：

```json
{
  "current_password": "old-password",
  "new_password": "new-password"
}
```

成功响应：`204`

常见错误：

- `401`：当前密码错误
- `422`：新密码强度不足

## 模型设置接口

当前模型设置接口支持两类密钥来源：

- 用户自己的 API key：通过 `PUT /settings/model` 的 `api_key` 字段保存，服务端使用 `MODEL_API_KEY_ENCRYPTION_KEY` 加密落库；查询接口只返回是否已配置和掩码，不返回明文。
- 服务端统一 API key：用户未保存自己的 key 时，worker 会根据 `llm_provider` 回退读取服务端进程环境变量。

密钥优先级：用户自己的加密 API key 优先，服务端 `.env` 里的统一密钥兜底。`ollama` 不需要 API key。

常用 provider 对应的环境变量：

| Provider | API key 环境变量 |
| --- | --- |
| `openai` | `OPENAI_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `google` | `GOOGLE_API_KEY` |
| `azure` | `AZURE_OPENAI_API_KEY` |
| `xai` | `XAI_API_KEY` |
| `deepseek` | `DEEPSEEK_API_KEY` |
| `qwen` | `DASHSCOPE_API_KEY` |
| `qwen-cn` | `DASHSCOPE_CN_API_KEY` |
| `glm` | `ZHIPU_API_KEY` |
| `glm-cn` | `ZHIPU_CN_API_KEY` |
| `minimax` | `MINIMAX_API_KEY` |
| `minimax-cn` | `MINIMAX_CN_API_KEY` |
| `openrouter` | `OPENROUTER_API_KEY` |
| `ollama` | 不需要 API key |

### GET /settings/model/options

需要登录。获取服务端数据库中当前可选的模型供应商和模型目录，前端应使用这个接口渲染 provider、quick/deep 模型下拉框和高级 endpoint 配置，而不是硬编码或让用户任意输入。

成功响应：`200`

```json
{
  "providers": [
    {
      "id": "openai",
      "label": "OpenAI",
      "required_env_var": "OPENAI_API_KEY",
      "default_backend_url": null,
      "backend_url_editable": false,
      "supports_custom_model": false,
      "quick_models": [
        {
          "id": "gpt-5.4-mini",
          "label": "GPT-5.4 Mini - Fast, strong coding and tool use"
        }
      ],
      "deep_models": [
        {
          "id": "gpt-5.4",
          "label": "GPT-5.4 - Previous-gen frontier, 1M context, cost-effective"
        }
      ]
    }
  ]
}
```

字段说明：

- `required_env_var`：服务端兜底密钥对应的环境变量；`ollama` 为 `null`
- `default_backend_url`：该 provider 的默认兼容 endpoint；为空时由底层 SDK 使用默认地址
- `backend_url_editable`：前端是否应该展示 endpoint 编辑入口
- `supports_custom_model`：是否允许用户输入不在 `quick_models` / `deep_models` 中的自定义模型 ID
- `quick_models` / `deep_models`：当前数据库中允许选择的 quick/deep 模型

说明：服务启动时会把内置模型目录初始化到数据库的 `llm_provider_options` 和 `llm_model_options` 表；之后接口和保存校验都从数据库读取。

### GET /settings/model

需要登录。获取当前用户的模型配置。

成功响应：`200`

```json
{
  "llm_provider": "openai",
  "deep_think_llm": "gpt-5.4",
  "quick_think_llm": "gpt-5.4-mini",
  "backend_url": null,
  "has_api_key": true,
  "api_key_masked": "sk-t...3456"
}
```

常见错误：

- `404`：当前用户尚未配置模型

### PUT /settings/model

需要登录和 CSRF。创建或更新当前用户的模型配置。

请求体：

```json
{
  "llm_provider": "openai",
  "deep_think_llm": "gpt-5.4",
  "quick_think_llm": "gpt-5.4-mini",
  "backend_url": null,
  "api_key": "sk-test-abcdef123456"
}
```

字段说明：

- `llm_provider`：支持 `anthropic`、`azure`、`deepseek`、`glm`、`glm-cn`、`google`、`minimax`、`minimax-cn`、`ollama`、`openai`、`openrouter`、`qwen`、`qwen-cn`、`xai`
- `deep_think_llm`：深度思考模型 ID，不能为空；对不支持自定义模型的 provider，必须存在于 `/settings/model/options` 的 `deep_models`
- `quick_think_llm`：快速思考模型 ID，不能为空；对不支持自定义模型的 provider，必须存在于 `/settings/model/options` 的 `quick_models`
- `backend_url`：可选；如果填写，必须以 `http://` 或 `https://` 开头
- `api_key`：可选；传入非空值时替换当前用户保存的 API key；不传或传 `null` 时保留旧 key

成功响应：`200`

```json
{
  "llm_provider": "openai",
  "deep_think_llm": "gpt-5.4",
  "quick_think_llm": "gpt-5.4-mini",
  "backend_url": null,
  "has_api_key": true,
  "api_key_masked": "sk-t...3456"
}
```

常见错误：

- `422`：provider、模型 ID 或 backend URL 不合法
- `500`：传入 `api_key` 但服务端未配置 `MODEL_API_KEY_ENCRYPTION_KEY`

### DELETE /settings/model/api-key

需要登录和 CSRF。清空当前用户保存的模型 API key。清空后仍可回退使用服务端统一环境变量。

成功响应：`204`

常见错误：

- `404`：当前用户尚未配置模型

### POST /settings/model/validate

需要登录和 CSRF。校验当前用户模型配置是否具备可用密钥来源，并在密钥来源可用时执行一次低成本 live probe。

成功响应：`200`

```json
{
  "valid": true,
  "provider": "openai",
  "required_env_var": "OPENAI_API_KEY",
  "api_key_source": "user",
  "message": "user API key configured for provider openai",
  "probe_status": "success",
  "probe_message": "probe returned pong"
}
```

字段说明：

- `valid`：当前模型配置是否通过密钥来源校验与 live probe
- `required_env_var`：服务端兜底密钥对应的环境变量；`ollama` 为 `null`
- `api_key_source`：`user`、`service`、`none` 或 `not_required`
- `probe_status`：live probe 结果；可能为 `success`、`invalid_api_key`、`model_not_found`、`endpoint_unreachable`、`permission_denied`、`timeout`、`provider_error`
- `probe_message`：live probe 的简短说明

常见错误：

- `404`：当前用户尚未配置模型

说明：live probe 只能证明“模型可调用”，不能证明模型后续回答内容真实可靠。回答真实性需要业务层补充数据源引用、交叉验证、置信度标记和人工审核机制。

## 分析任务接口

### POST /runs

需要登录、CSRF，且角色为 `admin` 或 `operator`。创建分析任务并投递到 Celery worker。

请求体：

```json
{
  "ticker": "AAPL",
  "trade_date": "2026-05-27",
  "asset_type": "stock",
  "analysts": ["market", "social", "news", "fundamentals"]
}
```

字段说明：

- `ticker`：会自动转大写；支持 `A-Z`、`0-9`、`.`、`_`、`-`、`^`，长度 1 到 32
- `trade_date`：交易日期，不能是未来日期
- `asset_type`：`stock` 或 `crypto`，默认 `stock`
- `analysts`：至少一个且不能重复；支持 `market`、`social`、`news`、`fundamentals`
- 当 `asset_type=crypto` 时，不支持 `fundamentals`

成功响应：`202`

```json
{
  "run_id": "uuid",
  "status": "queued"
}
```

常见错误：

- `403`：角色无权限
- `409`：当前用户尚未配置模型
- `422`：请求参数不合法
- `503`：任务投递失败

### POST /runs/{run_id}/cancel

需要登录、CSRF，且角色为 `admin` 或 `operator`。取消排队中或运行中的分析任务。

成功响应：`200`

```json
{
  "run_id": "uuid",
  "status": "cancelled"
}
```

常见错误：

- `403`：角色无权限
- `404`：任务不存在或无权访问
- `409`：任务已经成功或失败，不能取消

### GET /runs/{run_id}

需要登录。获取分析任务状态。

成功响应：`200`

```json
{
  "run_id": "uuid",
  "status": "running",
  "ticker": "AAPL",
  "trade_date": "2026-05-27",
  "asset_type": "stock",
  "analysts": ["market", "social", "news", "fundamentals"],
  "current_step": "market",
  "created_at": "2026-05-27T10:00:00Z",
  "started_at": "2026-05-27T10:00:01Z",
  "finished_at": null,
  "error": null
}
```

状态取值：

- `queued`
- `running`
- `succeeded`
- `failed`
- `cancelled`

常见错误：

- `404`：任务不存在或无权访问

### GET /runs/{run_id}/result

需要登录。获取已完成任务的分析结果。

成功响应：`200`

```json
{
  "run_id": "uuid",
  "status": "succeeded",
  "decision": "BUY",
  "reports": {},
  "final_state": {},
  "created_at": "2026-05-27T10:30:00Z"
}
```

常见错误：

- `404`：任务不存在或无权访问
- `409`：任务失败、尚未完成或结果不可用

### GET /runs/{run_id}/events

需要登录。以 SSE 方式订阅分析任务事件，响应类型为 `text/event-stream`。

事件格式：

```text
event: run_started
data: {"run_id":"uuid"}
```

说明：

- 会先回放历史事件，再继续轮询新事件
- 终止事件包括 `run_succeeded`、`run_failed`、`run_cancelled`
- 如果任务不存在或无权访问，握手阶段返回 `404`

## 管理员接口

### GET /admin/users

需要登录，且角色为 `admin`。获取用户列表。

成功响应：`200`

```json
[
  {
    "user_id": "uuid",
    "username": "admin",
    "role": "admin",
    "is_active": true
  }
]
```

### PATCH /admin/users/{user_id}

需要登录、CSRF，且角色为 `admin`。修改用户角色或启停状态。

请求体：

```json
{
  "role": "operator",
  "is_active": true
}
```

字段说明：

- `role`：可选，`admin`、`operator` 或 `viewer`
- `is_active`：可选，是否启用用户

成功响应：`200`

```json
{
  "user_id": "uuid",
  "username": "operator",
  "role": "operator",
  "is_active": true
}
```

常见错误：

- `404`：用户不存在

### POST /admin/users/{user_id}/sessions:revoke-all

需要登录、CSRF，且角色为 `admin`。撤销指定用户的所有会话。

成功响应：`204`

常见错误：

- `404`：用户不存在

### GET /admin/runs

需要登录，且角色为 `admin`。获取分析任务列表。

查询参数：

- `user_id`：可选，按用户 ID 过滤
- `status_filter`：可选，按任务状态过滤

成功响应：`200`

```json
[
  {
    "run_id": "uuid",
    "status": "succeeded",
    "ticker": "AAPL",
    "trade_date": "2026-05-27",
    "asset_type": "stock",
    "analysts": ["market", "social", "news", "fundamentals"],
    "current_step": null,
    "created_at": "2026-05-27T10:00:00Z",
    "started_at": "2026-05-27T10:00:01Z",
    "finished_at": "2026-05-27T10:30:00Z",
    "error": null
  }
]
```

## 当前业务接口汇总

| 方法 | 路径 | 登录 | CSRF | 角色 | 说明 |
| --- | --- | --- | --- | --- | --- |
| GET | `/health` | 否 | 否 | 无 | 健康检查 |
| POST | `/auth/register` | 否 | 否 | 无 | 注册用户 |
| POST | `/auth/login` | 否 | 否 | 无 | 登录 |
| POST | `/auth/logout` | 是 | 是 | 任意登录用户 | 注销 |
| GET | `/auth/me` | 是 | 否 | 任意登录用户 | 当前用户信息 |
| POST | `/auth/change-password` | 是 | 是 | 任意登录用户 | 修改密码 |
| GET | `/settings/model/options` | 是 | 否 | 任意登录用户 | 获取可选模型目录 |
| GET | `/settings/model` | 是 | 否 | 任意登录用户 | 获取模型配置 |
| PUT | `/settings/model` | 是 | 是 | 任意登录用户 | 保存模型配置 |
| DELETE | `/settings/model/api-key` | 是 | 是 | 任意登录用户 | 清空用户模型 API key |
| POST | `/settings/model/validate` | 是 | 是 | 任意登录用户 | 校验模型密钥来源 |
| POST | `/runs` | 是 | 是 | `admin`、`operator` | 创建分析任务 |
| POST | `/runs/{run_id}/cancel` | 是 | 是 | `admin`、`operator` | 取消分析任务 |
| GET | `/runs/{run_id}` | 是 | 否 | 任意登录用户 | 获取任务状态 |
| GET | `/runs/{run_id}/result` | 是 | 否 | 任意登录用户 | 获取任务结果 |
| GET | `/runs/{run_id}/events` | 是 | 否 | 任意登录用户 | 订阅任务事件 |
| GET | `/admin/users` | 是 | 否 | `admin` | 用户列表 |
| PATCH | `/admin/users/{user_id}` | 是 | 是 | `admin` | 修改用户 |
| POST | `/admin/users/{user_id}/sessions:revoke-all` | 是 | 是 | `admin` | 撤销用户全部会话 |
| GET | `/admin/runs` | 是 | 否 | `admin` | 任务列表 |
