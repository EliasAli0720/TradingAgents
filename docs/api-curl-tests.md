# API curl 测试手册

本文档为 `tradingagents/api` 中所有接口提供可直接复制运行的 curl 命令，便于在终端或 Postman（Import → Raw text → 粘贴 curl）中使用。

## 0. 通用准备

### 0.1 公共变量

```bash
# 基础地址
export BASE_URL="http://127.0.0.1:8000"

# Cookie jar：保存 session 和 csrf cookie
export COOKIE_JAR="/tmp/tradingagents.cookies"
rm -f "$COOKIE_JAR"

# 测试账号
export TA_USER="admin"
export TA_PASS="Password123!"
```

### 0.2 从 cookie jar 提取 CSRF Token 的辅助函数

> 写操作必须带 `X-CSRF-Token` 请求头，值是 `tradingagents_csrf` cookie 的值。

```bash
csrf() {
  awk '$6=="tradingagents_csrf"{print $7}' "$COOKIE_JAR" | tail -n 1
}
```

> Postman 用户：在 Postman 里登录后，会自动管理 cookie。把 `tradingagents_csrf` 的值复制到环境变量 `csrf`，然后在写请求的 Headers 里加 `X-CSRF-Token: {{csrf}}` 即可。

---

## 1. 健康检查

### 1.1 GET /health（无需登录）

```bash
curl -i "$BASE_URL/health"
```

---

## 2. 认证接口

### 2.1 POST /auth/register（无需登录）

> 系统中第一个注册的用户自动成为 `admin`，后续用户默认为 `viewer`。

```bash
curl -i -X POST "$BASE_URL/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "Password123!"
  }'
```

### 2.2 POST /auth/login（无需登录，写入 cookie）

```bash
curl -i -X POST "$BASE_URL/auth/login" \
  -H "Content-Type: application/json" \
  -c "$COOKIE_JAR" \
  -d "{
    \"username\": \"$TA_USER\",
    \"password\": \"$TA_PASS\"
  }"
```

### 2.3 GET /auth/me（需登录）

```bash
curl -i "$BASE_URL/auth/me" \
  -b "$COOKIE_JAR"
```

### 2.4 POST /auth/change-password（需登录 + CSRF）

```bash
curl -i -X POST "$BASE_URL/auth/change-password" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $(csrf)" \
  -b "$COOKIE_JAR" -c "$COOKIE_JAR" \
  -d '{
    "current_password": "Password123!",
    "new_password": "Password456!"
  }'
```

### 2.5 POST /auth/logout（需登录 + CSRF）

```bash
curl -i -X POST "$BASE_URL/auth/logout" \
  -H "X-CSRF-Token: $(csrf)" \
  -b "$COOKIE_JAR" -c "$COOKIE_JAR"
```

---

## 3. 模型设置接口

### 3.1 GET /settings/model/options（需登录）

```bash
curl -i "$BASE_URL/settings/model/options" \
  -b "$COOKIE_JAR"
```

### 3.2 GET /settings/model（需登录）

```bash
curl -i "$BASE_URL/settings/model" \
  -b "$COOKIE_JAR"
```

### 3.3 PUT /settings/model（需登录 + CSRF）

```bash
curl -i -X PUT "$BASE_URL/settings/model" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $(csrf)" \
  -b "$COOKIE_JAR" \
  -d '{
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    "backend_url": null,
    "api_key": "sk-test-abcdef123456"
  }'
```

> 不想覆盖已有 api_key 时，省略 `api_key` 字段或传 `null`。

### 3.4 DELETE /settings/model/api-key（需登录 + CSRF）

```bash
curl -i -X DELETE "$BASE_URL/settings/model/api-key" \
  -H "X-CSRF-Token: $(csrf)" \
  -b "$COOKIE_JAR"
```

### 3.5 POST /settings/model/validate（需登录 + CSRF）

```bash
curl -i -X POST "$BASE_URL/settings/model/validate" \
  -H "X-CSRF-Token: $(csrf)" \
  -b "$COOKIE_JAR"
```

---

## 4. 分析任务接口

### 4.1 POST /runs（需登录 + CSRF；admin / operator）

```bash
curl -i -X POST "$BASE_URL/runs" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $(csrf)" \
  -b "$COOKIE_JAR" \
  -d '{
    "ticker": "AAPL",
    "trade_date": "2026-05-27",
    "asset_type": "stock",
    "analysts": ["market", "social", "news", "fundamentals"]
  }'
```

把响应里的 `run_id` 导出，方便后面调用：

```bash
export RUN_ID="<上一步返回的 run_id>"
```

### 4.2 GET /runs/{run_id}（需登录）

```bash
curl -i "$BASE_URL/runs/$RUN_ID" \
  -b "$COOKIE_JAR"
```

### 4.3 GET /runs/{run_id}/result（需登录）

```bash
curl -i "$BASE_URL/runs/$RUN_ID/result" \
  -b "$COOKIE_JAR"
```

### 4.4 GET /runs/{run_id}/events（需登录，SSE 流）

```bash
curl -N "$BASE_URL/runs/$RUN_ID/events" \
  -H "Accept: text/event-stream" \
  -b "$COOKIE_JAR"
```

> `-N` 关闭缓冲，便于逐行看到 SSE 事件。在 Postman 中需新建 SSE 请求或使用 WebSocket/SSE 视图。

### 4.5 POST /runs/{run_id}/cancel（需登录 + CSRF；admin / operator）

```bash
curl -i -X POST "$BASE_URL/runs/$RUN_ID/cancel" \
  -H "X-CSRF-Token: $(csrf)" \
  -b "$COOKIE_JAR"
```

---

## 5. 管理员接口（仅 admin）

### 5.1 GET /admin/users（需登录）

```bash
curl -i "$BASE_URL/admin/users" \
  -b "$COOKIE_JAR"
```

### 5.2 PATCH /admin/users/{user_id}（需登录 + CSRF）

```bash
export TARGET_USER_ID="<目标用户 uuid>"

curl -i -X PATCH "$BASE_URL/admin/users/$TARGET_USER_ID" \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: $(csrf)" \
  -b "$COOKIE_JAR" \
  -d '{
    "role": "operator",
    "is_active": true
  }'
```

### 5.3 POST /admin/users/{user_id}/sessions:revoke-all（需登录 + CSRF）

```bash
curl -i -X POST "$BASE_URL/admin/users/$TARGET_USER_ID/sessions:revoke-all" \
  -H "X-CSRF-Token: $(csrf)" \
  -b "$COOKIE_JAR"
```

### 5.4 GET /admin/runs（需登录）

```bash
# 不带过滤
curl -i "$BASE_URL/admin/runs" \
  -b "$COOKIE_JAR"

# 按用户 ID 过滤
curl -i "$BASE_URL/admin/runs?user_id=$TARGET_USER_ID" \
  -b "$COOKIE_JAR"

# 按状态过滤：queued / running / succeeded / failed / cancelled
curl -i "$BASE_URL/admin/runs?status_filter=succeeded" \
  -b "$COOKIE_JAR"

# 同时过滤
curl -i "$BASE_URL/admin/runs?user_id=$TARGET_USER_ID&status_filter=running" \
  -b "$COOKIE_JAR"
```

---

## 6. OpenAPI 文档（无需登录）

```bash
curl -i "$BASE_URL/openapi.json"
curl -i "$BASE_URL/docs"
curl -i "$BASE_URL/redoc"
```

---

## 7. 推荐测试顺序（端到端冒烟）

1. `GET /health` 确认服务起来
2. `POST /auth/register` 注册首个 admin
3. `POST /auth/login` 登录（写入 cookie）
4. `GET /auth/me` 验证登录态
5. `GET /settings/model/options` 获取可选 provider / quick 模型 / deep 模型
6. `PUT /settings/model` 配置模型
7. `POST /settings/model/validate` 校验密钥来源
8. `POST /runs` 创建分析任务，记下 `run_id`
9. `GET /runs/{run_id}` 轮询状态，或 `GET /runs/{run_id}/events` 订阅 SSE
10. `GET /runs/{run_id}/result` 任务成功后取结果
11. `GET /admin/runs` 管理员视角查看所有任务
12. `POST /auth/logout` 注销

---

## 8. Postman 使用提示

- **Cookie 自动管理**：Postman 默认开启 Cookie Jar，登录请求成功后即可在后续请求自动携带 `tradingagents_session` 和 `tradingagents_csrf`。
- **CSRF Header**：在 Postman 顶部 → Cookies 弹窗里复制 `tradingagents_csrf` 的值，存到环境变量 `csrf`，写请求 Headers 加一行 `X-CSRF-Token: {{csrf}}`。
- **SSE 接口**（`GET /runs/{run_id}/events`）：Postman v10+ 在请求类型里选择 “Server-Sent Events”。
- **Import curl**：在 Postman → Import → Raw text 粘贴上面的 curl 即可生成请求。
