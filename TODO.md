# TODO

更新时间：2026-05-31

本文档集中记录当前项目里仍有价值的后续工作。其他设计文档保留上下文说明，但不再作为待办入口。

## P0 / P1

### 0. Webull 接入 — W3 交易链路（阻塞中：等 Webull UAT 凭证）

> 设计：`docs/superpowers/specs/2026-05-31-webull-server-broker-design.md`
> 决策：服务端云经纪 + Connect API 多租户（每用户 OAuth token 加密落库）。
> 已完成 W1（适配器+只读）/ W2（凭证表+OAuth+per-user provider）/ W4（前端连接卡片）；全套 623 测试绿、前端 build 绿。
> **W3 唯一阻塞 = 没有 Webull UAT 凭证。** 拿到后按下面顺序做（SDK/OAuth 的真实字段都已隔离在单一文件，只改那里）：

- [ ] **阶段 0 — 申请凭证**：邮件 `connect.api@webull-us.com`（公司名 + redirect_uri）申请 Connect App，或先用 UAT 共享测试账户。拿到 `client_id / client_secret / scope / app_key / app_secret`，填入环境变量 `WEBULL_CLIENT_ID / WEBULL_CLIENT_SECRET / WEBULL_REDIRECT_URI / WEBULL_APP_KEY / WEBULL_APP_SECRET`（见 `tradingbot/config.py` 的 `webull_*`）。`pip install ".[webull]"` 装 SDK。
- [ ] **核对 OAuth 端点**：对照 Connect API authentication 文档，校准 `tradingbot/broker/webull_oauth.py` 的 `_AUTHORIZE_PATH / _TOKEN_PATH / scope / base URL`（现为推断值，已隔离常量）。先确认 token 端点是否真返回 `refresh_token`（有二手文档称早期未实装；无则 access_token 过期即需重新授权，代码已兜底）。
- [ ] **核对 SDK 字段**：用真凭证连 UAT，校准 `tradingbot/broker/webull_client.py` 里 `SdkWebullClient` 的方法名/字段（account_balance / positions / resolve_instrument / get_quote / preview_order / place_order / cancel_order / get_order / list_orders / get_account_list）和 token 注入方式（`set_access_token` vs header）。**这是唯一碰真 SDK 的文件**，字段映射已归一，只改这里。
- [ ] **下单字段**：`place_order` 的 `client_order_id / instrument_id / side / tif / order_type / limit_price / qty` 对齐；确认 symbol→instrument_id 解析端点 + 加客户端限流（account 2/2s、place 600/60s、preview 150/10s、instrument 10/30s）。
- [ ] **接审批执行链路**（基本 0 改动）：Webull 用户走现有 `POST /broker/approvals`（build）→ `/approvals/{id}/approve`（execute → `WebullBroker.submit_order`）；验证 `broker_orders` 镜像写入 `account_id = cred.account_id`。
- [ ] **成交回写**：`get_order` 轮询把 pending→filled 更新回 `broker_orders`（首版轮询，或 `POST /broker/orders/{id}/status`）。
- [ ] **真机走通**：浏览器登录 → broker 页「连接 Webull」→ OAuth 授权 → 回调存 token → 生成建议 → 批准 → Webull UAT 下单 → 订单/持仓刷新。
- [ ] **混币种检查**：美区账户多为 USD，较简单；仍确认 RiskGate/盈亏不硬编码 USD（参考 IBKR 的 HKD 坑）。
- [ ] **W5（可选，后续）**：gRPC 实时订单回报替代轮询；多 broker 并存时前端显式切换 UI；期权/组合单。

### 1. Session 表清理

API 的 `sessions` 表会持续增长。需要增加 cron、Celery beat 或同等机制，周期性删除：

```sql
expires_at < now() - interval '30 days'
```

清理策略应与后续 run/result/event 保留策略保持一致。

### 2. Dashboard 页面级权限矩阵

后端已经落地 `admin` / `operator` / `viewer` 的路由级权限，Dashboard 还需要定义页面与控件层面的展示规则：

- viewer 是否隐藏“新建分析”按钮，还是显示 disabled 状态并给 tooltip。
- 侧边栏 `Risk` / `Trades` 是否仅 `operator` + `admin` 可见。
- `Agent Reasoning` 页是否允许 viewer 查看完整 reports，还是只看 final decision。
- `Admin` 入口放顶层导航还是设置页。
- 用户管理页先放在 Streamlit 内，还是等真正前端。
- 未登录态直接跳 `/login`，还是允许匿名公共首页。
- 角色提升使用 role 下拉框，还是 invite 流程。

### 3. 角色语义定稿

当前代码使用单角色模型：`admin` / `operator` / `viewer`。仍需要产品层确认：

- 三个角色的最终名称。
- `operator` 与 `viewer` 是按读写权限区分，还是按业务职责区分。
- 第一版继续保持单角色，还是升级为多角色数组。
- 首位注册用户自动成为 `admin` 的初始化方式是否满足生产部署。

## P2

### 4. Graph 内协作式取消

当前 `POST /runs/{run_id}/cancel` 已实现 API/状态机层取消：能标记 run 为 `cancelled`，并阻止 worker 覆盖结果。

但如果任务已经进入 `TradingAgentsGraph.propagate()`，当前 graph 不保证立即停止正在进行的 LLM 或数据供应商调用。后续如果要降低运行中成本，需要单独设计协作式取消：

- 从一次性 `graph.invoke(...)` 调整为可在节点或 streamed chunk 边界检查取消信号的执行方式。
- 在执行边界查询数据库状态。
- 发现 `status == "cancelled"` 后停止后续节点。
- 保留已完成节点的部分进度。
- 明确 checkpoint resume 与取消后的恢复语义。

同一方向还包括：

- 单任务超时策略
- 供应商重试策略
- 部分进度保留和恢复语义

### 5. AutoTrader reflection 逻辑对齐

`tradingbot/scheduler/runner.py` 的 SELL 后流程仍调用旧 reflection 接口：

```python
self._graph.reflect_and_remember(realized_pnl)
```

当前主线已经改为 persistent decision log。需要决定是移除该调用，还是改成显式写入当前 memory log / decision log 机制。

### 6. CLI 与 API side effect 对齐

`TradingAgentsGraph.propagate()` 会处理 memory log 和 checkpoint lifecycle。CLI 当前直接 stream `graph.graph`，没有完全复用 `propagate()` 的副作用。

如果后续依赖这些副作用，需要补齐 CLI 路径，或把相关生命周期逻辑下沉到 CLI/API 共用层。

### 7. Streamlit auth 生产化

`AuthService.send_sms_code()` 目前是开发 stub，只打印验证码。生产前需要接入真实短信通道，并避免在 UI 或日志中泄露验证码。

Dashboard cookie 写入依赖 `components.html()` 注入，调整 auth flow 时还要保留当前 render 时序约束，避免 `st.rerun()` 或 `st.switch_page()` 过早打断 cookie 写入。

## 文档清理

以下历史文档里的事项已经完成，后续不再作为待办追踪：

- 模型配置 live probe 已在 `POST /settings/model/validate` 落地，会用当前配置发起短超时低成本探测，并返回稳定的 `probe_status`。
- LLM client 的未知模型 warning 已在 `BaseLLMClient.warn_if_unknown_model()` 落地，并有 `tests/test_model_validation.py` 覆盖。
- `pyproject.toml` 已包含 `tradingbot*` package include。
- `pytest` 已写入项目依赖。
