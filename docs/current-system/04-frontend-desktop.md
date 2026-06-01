# 04 前端与桌面端

## 1. 技术栈和入口

前端在 `web/`，技术栈：

- Vite
- React 18
- TypeScript
- React Router
- TanStack Query
- Axios
- react-hook-form
- Tailwind
- Electron

关键脚本在 `web/package.json` 和 `scripts/start_frontend_dev.sh`。

开发模式：

```bash
./start.sh api
./scripts/start_frontend_dev.sh
```

默认会跑 Electron。只跑浏览器：

```bash
FRONTEND_TARGET=browser ./scripts/start_frontend_dev.sh
```

Vite 端口默认 5173，`/api` 代理到 `http://127.0.0.1:8000`。

## 2. React 路由

路由集中在 `web/src/router.tsx`。

公开路由：

- `/login`

登录后主布局：

- `/` -> `/analysis`
- `/recommendations`
- `/analysis`
- `/analysis/new`
- `/analysis/:runId`
- `/broker`
- `/broker/approvals`
- `/broker/orders`
- `/portfolio`
- `/performance`
- `/trades`
- `/risk`
- `/settings/model`
- `/settings/translation`
- `/settings/account`
- `/admin/users`
- `/admin/runs`

权限门禁：

- `RequireAuth`：未登录跳 `/login?next=...`。
- `RequireRole`：admin 页面只允许 admin。
- `BrokerGate`：交易相关页面在 desktop local 模式下要求连接本地 broker；server/Webull 模式放行，让页面展示自己的状态。

## 3. API client

`web/src/api/client.ts` 创建 axios 实例：

- baseURL = `VITE_API_BASE ?? /api`
- `withCredentials=true`
- 默认 `Content-Type=application/json`
- state-changing 请求自动加 `X-CSRF-Token`
- 401 自动跳登录页
- 错误统一转成 `{ status, detail }`

这意味着前端业务代码通常只处理 `detail`，不用重复处理 CSRF 和 401。

## 4. React Query 习惯

全局配置在 `web/src/main.tsx`：

- retry 1 次。
- window focus 不自动 refetch。

页面局部轮询：

- run live 状态每 3 秒。
- broker local status 5 到 15 秒。
- server broker status 30 秒。
- recommendations 有活跃 run 时 4 秒轮询 batch。
- 翻译未完成时 4 秒轮询 result。

## 5. 主要页面逻辑

### 5.1 登录页

`/login` 支持登录/注册。登录成功后跳 `next` 或默认页面。

后端第一位注册用户自动 admin，前端不做这个判断。

### 5.2 模型设置

`/settings/model`：

- 读取 provider/model options。
- 保存用户模型设置。
- 可保存用户 API key。
- 可点击 validate 测试当前配置。

如果没配置模型，创建 run 和生成推荐会被后端拒绝。

`/settings/translation` 是翻译模型设置，独立于分析模型。

### 5.3 新建分析

`/analysis/new`：

- 输入 ticker。
- 选择 trade_date。
- 选择 asset_type。
- 勾选 analysts。
- crypto 时禁用 fundamentals。
- 提交 `POST /runs`。
- 成功后跳转 `/analysis/{run_id}`。

### 5.4 分析详情

`/analysis/:runId`：

- `GET /runs/:id` 读取状态。
- live 状态时轮询。
- `useRunEvents()` 打开 SSE。
- succeeded 后 `GET /runs/:id/result`。
- 非英文且翻译未完成时继续轮询 result。
- 可取消 queued/dispatching/running run。
- 可生成交易建议。

交易建议按钮状态由 `proposalEligibility()` 决定：

- 非 operator/admin：隐藏。
- run 未 succeeded：隐藏。
- decision 为空：loading。
- decision 是可交易信号但 broker 还在加载：loading。
- decision 是可交易信号但没有可用 broker account：显示连接账户提示和跳转按钮。
- decision 是可交易信号且 broker 可用：显示生成按钮。
- decision 是 HOLD 或未知：显示无动作提示。

生成建议时按钮会进入 loading，避免重复提交。

### 5.5 推荐页

`/recommendations`：

- 读/写 watchlist。
- 点击生成推荐 -> `POST /recommendations/generate`。
- 展示推荐批次和推荐项。
- 用户选择推荐项后点击分析。
- 有推荐项关联 run 处于 queued/dispatching/running 时，批次详情会轮询刷新。
- 失败或终态后的 item 可重试。

### 5.6 Broker 状态页

`/broker`：

- 浏览器/server channel：读 server status。
- Electron：同时看 server status 和 local status。
- 如果 server 是 connected Webull，则优先显示 Webull server broker。
- 非 Webull 时显示 IBKR gateway/session 状态。
- 显示 account KPI。
- 展示 `WebullConnectCard`。

### 5.7 审批和订单页

`/broker/approvals`：

- 轮询 pending approvals。
- approve 调 `approveProposal()`，该函数会根据 Webull/server/local 选择执行路径。
- reject 直接调服务端 reject。

`/broker/orders`：

- 读取服务端 order mirror。
- open order 可取消。

### 5.8 Portfolio/Performance/Trades/Risk

这些页面现在在 `web/src/routes/placeholder/*`，但已经有实际数据逻辑：

- portfolio/risk：读取当前 broker channel 的 account/positions。
- performance/trades：读取服务端 `/broker/performance` 和 `/broker/trades`。

## 6. Broker channel 抽象

`web/src/api/brokerChannel.ts` 定义 `BrokerLiveChannel`。

server channel：

- 浏览器默认使用。
- 调服务端 `/broker/*`。
- `supportsConnect=false`。

local channel：

- Electron 环境使用。
- 通过 `window.desktop.broker.*` IPC 调 main process。
- 支持 discover/connect/account/positions/orders/quote/preview/execute/cancel。

`isDesktop()` 判断 `window.desktop?.isDesktop && window.desktop.broker`。

## 7. BrokerGate

`BrokerGate` 的设计目标是：不要让 desktop local IBKR 未连接时进入依赖本地 broker 的交易页面，但也不要挡住 server/Webull。

逻辑：

```text
如果 channel.kind === server
    放行
如果 desktop 且 server status 是可用 Webull
    放行
如果 local 正在 loading
    显示 loading
如果 local tradingEnabled
    放行
否则
    显示 ConnectPanel
```

这保证了用户在 Electron 中绑定 Webull 后，不会被本地 IBKR 连接面板挡住。

## 8. Webull 连接卡

`WebullConnectCard` 支持两种模式：

- API key：用户输入 app_key/app_secret/account_id。
- OAuth：跳转授权 URL。

API key 模式：

- 输入 app_key/app_secret 后按钮可用。
- 提交 `brokerApi.webull.connectApiKey()`。
- 成功后清空 app_secret，刷新 broker query。

OAuth 模式：

- 请求 authorize URL。
- `window.location.assign(url)` 离开 SPA。
- callback 回来后 URL 有 `connected=webull` 或 `error=...`。
- 组件显示一次 banner 后清理 URL query。

连接后显示：

- account_id
- auth_type
- disconnect 按钮

## 9. 生成交易建议的前端分流

`web/src/api/tradeFlow.ts`：

```text
createProposal(runId, ticker):
  serverStatus = brokerApi.status()
  如果 serverStatus 是可用 Webull
      brokerApi.createProposal(runId)
  否则如果当前是 server channel
      brokerApi.createProposal(runId)
  否则 desktop local:
      检查 local status
      并行读取 account/positions/quote
      brokerApi.createLocalProposal(snapshot)
```

批准：

```text
approveProposal(approval):
  如果 serverStatus 是可用 Webull
      brokerApi.approve()
  否则如果 server channel
      brokerApi.approve()
  否则 desktop local:
      local sidecar execute
      brokerApi.recordExecuted()
```

重点：approval audit 始终在服务端，local 只负责本地下单。

## 10. 手动快速下单前端分流

`QuickTrade` 的路由由 `manualTradeRoute()` 决定：

- Webull server 可用：server。
- Electron local IBKR 可用：local。
- 其他：不可下单。

server：

- preview -> `brokerApi.previewOrder`
- submit -> `brokerApi.placeOrder`

local：

- preview -> `channel.preview`
- submit -> `channel.execute`
- mirror -> `brokerApi.recordManualOrder`

提交前会 `window.confirm()` 二次确认。

## 11. Electron 主进程

`web/electron/main.cjs`：

- 创建 BrowserWindow。
- dev 加载 Vite dev server。
- prod 用 `app://local/` 自定义协议加载 `dist/`。
- 外部链接用系统浏览器打开。
- 注册 broker IPC handler。
- app ready 后后台启动 sidecar。

IPC handler 映射：

- `broker:status` -> sidecar `/health`
- `broker:discover` -> `/discover`
- `broker:connect` -> `/connect`
- `broker:disconnect` -> `/disconnect`
- `broker:account` -> `/account`
- `broker:positions` -> `/positions`
- `broker:orders` -> `/orders`
- `broker:quote` -> `/quote`
- `broker:preview` -> `/preview`
- `broker:execute` -> `/execute`
- `broker:cancel` -> `/orders/{id}/cancel`

## 12. Sidecar 启动

`web/electron/sidecar.cjs`：

- 找一个随机 loopback 端口。
- 生成 24 bytes hex token。
- dev 模式运行 `.venv/bin/python3 run_sidecar.py`。
- packaged 模式运行 PyInstaller 打包的 sidecar binary。
- 等 `/ping` ready，最长 45 秒。
- `call()` 给每个 sidecar 请求加 bearer token。

`run_sidecar.py`：

- 强制 host 是 `127.0.0.1` 或 localhost。
- 设置 `SIDECAR_TOKEN`。
- 启动 `tradingbot.sidecar.app:app`。

## 13. 前端测试脚本

目前前端有两个轻量 Node 脚本测试：

- `web/scripts/proposalEligibility.test.mjs`
- `web/scripts/manualTradeFlow.test.mjs`

它们直接验证交易建议按钮状态和手动下单路由，不需要浏览器。
