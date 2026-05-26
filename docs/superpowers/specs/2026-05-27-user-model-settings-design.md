# 用户模型配置 API 设计

日期：2026-05-27

## 目标

登录功能已落地后，将分析 API 使用的 LLM provider 和模型配置从服务端内置默认值迁移到数据库，让每个登录用户可以自行设置。创建分析任务时必须使用当前用户的模型配置，并把配置快照固化到 run 上，避免用户后续修改配置影响已排队任务。

## 范围

本次只实现模型运行配置：

- `llm_provider`
- `deep_think_llm`
- `quick_think_llm`
- `backend_url`

不在数据库中保存 provider API key。API key 仍由服务端环境变量或 provider SDK 的既有机制读取，避免把敏感凭据引入第一版用户配置表。

## API

### `GET /settings/model`

返回当前登录用户的模型配置。

- 未登录：`401`
- 未配置：`404`
- 已配置：`200`

响应：

```json
{
  "llm_provider": "openai",
  "deep_think_llm": "gpt-5.4",
  "quick_think_llm": "gpt-5.4-mini",
  "backend_url": null
}
```

### `PUT /settings/model`

创建或更新当前登录用户的模型配置。

请求：

```json
{
  "llm_provider": "openai",
  "deep_think_llm": "gpt-5.4",
  "quick_think_llm": "gpt-5.4-mini",
  "backend_url": null
}
```

行为：

- 需要登录。
- 因为是状态变更接口，沿用现有 cookie session + CSRF 保护。
- `llm_provider` 必须是当前项目 `create_llm_client()` 支持的 provider。
- 模型 ID 允许用户输入任意非空字符串，兼容自定义模型和私有网关部署。
- `backend_url` 允许为 `null`；非空时必须是 `http://` 或 `https://` URL。

## 创建 Run 的行为

`POST /runs` 不再使用 `DEFAULT_CONFIG` 中的内置 LLM 默认值。

创建 run 时：

1. 根据当前登录用户读取 `user_model_settings`。
2. 如果未配置，返回 `409 Conflict`，提示用户先设置模型配置。
3. 把模型配置快照写入 `analysis_runs.llm_config`。
4. worker 从 run 快照读取配置执行分析。

快照格式：

```json
{
  "llm_provider": "openai",
  "deep_think_llm": "gpt-5.4",
  "quick_think_llm": "gpt-5.4-mini",
  "backend_url": null
}
```

## 数据模型

新增 `user_model_settings`：

- `user_id`：主键，外键到 `users.user_id`
- `llm_provider`
- `deep_think_llm`
- `quick_think_llm`
- `backend_url`
- `created_at`
- `updated_at`

修改 `analysis_runs`：

- 新增 `llm_config` JSON 字段，保存创建 run 时的配置快照。

为了兼容现有测试和旧数据，`llm_config` 在数据库层允许为空；但新创建的 run 必须写入非空快照。

## Worker 行为

worker 领取 run 后，从 `run.llm_config` 构造运行配置：

- 非 LLM 相关配置继续来自 `DEFAULT_CONFIG`，例如缓存目录、数据 vendor、轮次限制等。
- LLM 相关字段必须来自 `run.llm_config`。
- 如果旧 run 缺少 `llm_config`，worker 将该 run 标记失败，不回退到内置模型默认值。

## 权限

- `viewer`、`operator`、`admin` 都可以查看和修改自己的模型配置。
- 创建 run 仍保持现有权限：`admin` 和 `operator` 可创建，`viewer` 不可创建。
- admin 不默认替其他用户设置模型配置，本次不做跨用户模型配置管理。

## 测试

最低覆盖：

- 未登录访问设置接口返回 `401`。
- 已登录但未配置时 `GET /settings/model` 返回 `404`。
- `PUT /settings/model` 可以创建配置，`GET` 可以读回。
- 非法 provider 被拒绝。
- 非法 `backend_url` 被拒绝。
- 未配置模型时 `POST /runs` 返回 `409`。
- 配置后创建 run 会写入 `analysis_runs.llm_config` 快照。
- worker 调用分析 executor 时传入 run 的 `llm_config`。
- worker 遇到缺失 `llm_config` 的旧 run 会写入失败状态。
