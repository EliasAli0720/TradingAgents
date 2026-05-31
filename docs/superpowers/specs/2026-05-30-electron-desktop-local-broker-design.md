# Electron 桌面端 + 本地 IBKR 交易通道 — 前端改造设计

日期：2026-05-30
分支：`phase/9-broker-integration`(沿用)
状态：**设计待评审**——三个架构岔路口已拍板，本文给出落地方案与分期。

## 目标与约束

把现有 Web 前端(`web/`，React + Vite + TS)用 **Electron** 包一层在桌面运行：

- **登录 + 分析** 继续走现在的远程服务端(FastAPI `/api/*`)，行为不变。
- **交易平台相关** 走**本地**连接：桌面端连本机的 IBKR 软件(经典版 Trader Workstation / IB Gateway 的 socket)。
- **所有交易功能必须先"检测 + 连接"成功后才可用**(连接门禁)。
- **不删除现有服务端能力**：`/broker/*` 路由、services、Redis-connector 路径全部保留，将来云经纪(Webull 等)/ headless / API 接入继续用。
- "不要碰现在的后端" = 不破坏、不删现有逻辑；**允许纯增量、不改动现有行为的新增端点**(见 §6 的诚实说明)。

## 已拍板的三个决策

1. **本地交易通道 = Python sidecar(复用现有代码)。** Electron 启动一个打包进去的 Python 进程，直接复用 `tradingbot/broker` 的本地栈 `build_broker(config, mode="local")` → `LocalIBKRConnection`(`ib_async`，直连 socket，不走 Redis)，在 `127.0.0.1` 暴露 HTTP/WS。最大化复用已验证的 broker/风控/信号/服务层。
2. **流程归属 = 服务端出建议+风控、本地执行。** 服务端继续用 `/broker/approvals` 生成建议与风控判定并落 Postgres(集中审计)；本地 sidecar 只对已批准建议做 whatif 预览 + 下单 + 回报成交。账户/持仓数据现在在本地 → 需把账户快照回传服务端(§6)。
3. **通道范围 = 可切换双通道。** 前端 broker 客户端做成可插拔：`localBrokerClient`(本地 sidecar)/ `serverBrokerClient`(现有 `/broker/*`)。Electron 默认本地 IBKR，将来可在同一桌面端切到服务端路由的云经纪(Webull)。

> 现成可复用的关键事实：`tradingbot/broker/factory.py:build_broker(config, mode="local")` 已经构造 `LocalIBKRConnection(host, port, client_id, market_data_type)` 直连本地 TWS、**不依赖 Redis**——sidecar 几乎是对它包一层 HTTP。

## 1. 拓扑

```
┌──────────────────────── 用户本机(桌面) ────────────────────────┐
│  Electron 应用                                                   │
│  ┌─────────────────────┐        ┌──────────────────────────────┐ │
│  │ Renderer (React SPA)│  IPC   │ Main 进程 (Node)              │ │
│  │  - 复用现有 web/     │◄──────►│  - 生命周期/窗口/自动更新     │ │
│  │  - brokerClient 可插拔│       │  - 拉起并守护 sidecar         │ │
│  │     • serverBroker   │        │  - 安全存连接偏好 + sidecar    │ │
│  │     • localBroker    │        │    token(electron-store/keytar)│ │
│  └───┬─────────────┬────┘        └──────────────┬───────────────┘ │
│      │ https        │ http 127.0.0.1            │ spawn            │
│      │ 登录/分析     │ 交易(本地)               ▼                  │
│      │ /建议+审批     │             ┌────────────────────────────┐ │
│      │              └────────────►│ Python broker sidecar       │ │
│      │                            │ (PyInstaller 打包)          │ │
│      │                            │ FastAPI @127.0.0.1:<port>   │ │
│      │                            │ token 鉴权、仅回环           │ │
│      │                            │ build_broker(mode="local")  │ │
│      │                            │  → LocalIBKRConnection       │ │
│      │                            └──────────────┬─────────────┘ │
│      │                                           │ TCP 7497/7496   │
│      │                            ┌──────────────▼─────────────┐ │
│      │                            │ TWS / IB Gateway (用户 GUI) │ │
│      │                            └────────────────────────────┘ │
└──────┼───────────────────────────────────────────────────────────┘
       │ https
       ▼
┌──────────────────── 远程服务端(核心不动) ─────────────────────┐
│ FastAPI /api/* : auth、runs(分析)、settings、admin            │
│ Broker         : /broker/*(现有，服务端 connector 路径)——保留 │
│                  供云经纪/headless/API。另加纯增量桥接端点(§6) │
│ Worker(Redis) : 分析任务                                       │
│ Postgres       : users / runs / trade_approvals / broker_orders │
└──────────────────────────────────────────────────────────────────┘
```

两条信任域：服务端用 **cookie 会话 + CSRF**(`web/src/api/client.ts` 现状)；sidecar 用 **回环 + Bearer token**。交易的"审批审计"在服务端，"执行权限"由本地连接是否就绪决定。

## 2. Electron 外壳(新增，建议 `web/electron/` 或 `apps/desktop/`)

- `main.ts`：应用生命周期、`BrowserWindow`、加载 renderer(dev 指向 vite，prod 加载 `dist`)。
- **sidecar 守护**：`app.ready` 时选一个空闲回环端口 + 生成随机 per-session token，spawn 打包的 sidecar(`--host 127.0.0.1 --port <p> --token <t>`)；轮询 `/health` 就绪；崩溃自动重启；退出时 kill。
- `preload.ts`：`contextBridge` 暴露最小 `window.desktop`：`{ isDesktop:true, sidecarBaseUrl, sidecarToken, platform }`。`contextIsolation:true`、`nodeIntegration:false`、`sandbox:true`（安全基线）。
- 偏好与密钥：IBKR 连接偏好(host/port/clientId/paper/marketDataType)存 `electron-store`；sidecar token 只在内存(每次启动新生成)。renderer 不接触 Node `fs`/`child_process`。

## 3. Python broker sidecar(新增薄壳，复用现有库)

独立的小 FastAPI(**不是**服务端那个 app)，由 `build_broker(local_config, mode="local")` 支撑。仅回环 + Bearer token。

端点：
- `GET  /health` → `{sidecar_up, gateway_online, brokerage_session, account_id, paper, last_error}`
- `POST /connect` `{host,port,client_id,paper,market_data_type}` → 重建 broker + `ensure_connected`
- `POST /disconnect`
- `GET  /account` `GET /positions` `GET /orders`
- `POST /preview`(whatif)`{ticker,qty,side,order_type,limit_price,tif}`
- `POST /execute` `{approval payload}` → whatif + `placeOrder` → 返回 `broker_order_id` + status
- `POST /orders/{id}/cancel`
- `GET  /stream`(SSE/WS，可选)→ `ib_async` 的订单/成交事件回调推给 renderer

复用清单(0 改动)：`broker/base.py` 模型、`broker/ibkr.py`、`broker/ibkr_connection.LocalIBKRConnection`、`broker/signal_mapper.py`、`risk/gate.py`、`services/TradeExecutionService`。

打包：PyInstaller 按 OS 分别构建(macOS/Windows)，作为 electron-builder 的 `extraResources` 一起打。pin `ib_async`。文档注明：必须先开 TWS/Gateway 且启用 API。

安全：只 bind `127.0.0.1`；每个写操作校验 `Authorization: Bearer <token>` == Electron 注入的 token，缺失即拒。**防止本机其它进程 / 任意网页 POST 下单到这个交易端口。**

## 4. Renderer — 可插拔 broker 客户端

- 定义接口 `BrokerChannel`，形状对齐现有 `web/src/api/broker.ts`(status/account/positions/orders/preview/execute/cancel + 建议/审批读取)。
- `serverBrokerClient`：现有 `web/src/api/broker.ts`(走 `http` → `/broker/*`)。
- `localBrokerClient`：打 `window.desktop.sidecarBaseUrl`，带 Bearer token，映射成同一套类型。
- **通道选择器**(Zustand store + context)：`window.desktop?.isDesktop` 为真时默认 `local`，否则 `server`；用户可切(将来 Webull → server)。持久化选择。
- 现有三个 broker 页面(`routes/broker/{status,approvals,orders}.tsx`)与 `portfolio` 改为消费 `BrokerChannel` 而非直接 import `brokerApi` → 浏览器构建仍走服务端、桌面构建走本地，**同一套页面两用**。

## 5. 连接门禁(对应"先检测+连接才可用")

- 全局 `brokerConnection` store：轮询当前通道的 `health()`/`status()`，导出 `tradingEnabled = connected && brokerage_session`。
- `<BrokerGate>` 包裹需要实时 broker 的路由(`/broker`、`/broker/approvals`、`/broker/orders`、`/portfolio`、`/trades` 等)：
  - 未连接 → 展示**连接面板**:填 host/port/clientId/paper → `POST /connect`；实时三段勾选清单(sidecar 起 ✓ / gateway 在线 ✓ / brokerage session ✓)。
  - 交易动作(approve/execute/cancel/preview)在未到绿灯前 disabled + tooltip 提示。
- 侧边栏放一个 broker 状态 pill(通道 + 连接态)。
- **登录、分析永不门禁**(始终走服务端)。

## 6. 交易流程(决策 ② 的拆分)与后端桥接(纯增量)

流程:
1. 分析在服务端跑(不变)。用户打开分析详情。
2. 「生成建议」→ `POST` 服务端 `/broker/approvals {run_id}`。服务端据分析决策 + **账户快照**(下文)出订单意图 + 风控判定 → 落 `TradeApproval`(审计)。
3. whatif 保证金/手续费:桌面端调 `localBrokerClient.preview()` 展示并(可选)回写。
4. 审批列表读服务端数据。Operator 点 Approve。
5. 批准后:通道=local → 调 `localBrokerClient.execute(approval)` → sidecar whatif + `placeOrder` 到本地 TWS → 回 `broker_order_id`。
6. 桌面端把执行回执 POST 回服务端 → 标记 approval submitted + 写 `broker_order` 镜像。
7. 成交:sidecar 推订单/成交事件 → 桌面端更新本地订单视图 + 回写服务端镜像。

### 后端桥接(ADDITIVE only — 不改/不删现有)

> 这是决策 ② 的**唯一诚实代价**:服务端要出建议+风控，就得拿到账户数据，而账户现在只在本地。需新增(纯增量、不改现有行为、可用 feature flag/role 隔离):
- `POST /broker/account-snapshot` — sidecar 周期推 `{account, positions}`，存 DB 镜像；proposal builder / risk gate 在无服务端 live connector 时读快照。
- `POST /broker/approvals/{id}/executed` — 桌面端本地下单后回执 `{broker_order_id,status,filled...}` → 标记 submitted + upsert `broker_order`。
- `POST /broker/orders/{id}/status` — 成交/状态更新 → 镜像。

现有所有 `/broker/*`、services、Redis-connector 路径**全部保留**，给云经纪/headless/API 用，不动一行。

### 若要"现在就零后端改动"的退路

把建议+风控也放进 sidecar(sidecar 是 Python，可直接 import `services`/`risk`/`signal_mapper`)，服务端只读分析决策。代价:审批审计落本地 SQLite 而非服务端 Postgres，与决策 ② 的"集中审计"相悖。**建议**:先按本退路做 P3，把后端桥接端点留到能改后端时补——这样前端改造期间真正零后端改动，后续平滑升级到 ② 的集中审计。

## 7. 构建与运行(已落地命令)

- **Dev**:`cd web && pnpm electron:dev` —— `concurrently` 起 vite(:5173)+ Electron 指向 vite;Electron 主进程 spawn `.venv/bin/python3 run_sidecar.py`。`/api` 经 vite 代理打 :8000(登录/分析需服务端在跑)。
- **Sidecar 打包**:`cd web && pnpm sidecar:build` → `.venv/bin/pyinstaller --noconfirm --distpath dist-sidecar --workpath build-sidecar packaging/sidecar.spec` → `dist-sidecar/sidecar/`(onedir,含 ib_async)。pyinstaller 用 `uv pip install pyinstaller`(.venv 无 pip)。
- **App 打包**:`cd web && pnpm electron:pack`(--dir,出 `release/mac/TradingAgents.app`)或 `pnpm electron:dist`(出 .dmg)。**勿用 `pnpm pack`**(pnpm 内置命令,会做 npm tarball)。
- 配置:`web/electron-builder.yml`(appId `com.tradingagents.desktop`,`extraResources: ../dist-sidecar/sidecar → sidecar`,mac dmg / win nsis / linux AppImage)。打包态 `sidecar.cjs` spawn `process.resourcesPath/sidecar/sidecar`;dev 态用 `.venv` python。
- 依赖:`electron`、`electron-builder`、`concurrently`、`wait-on`、`cross-env`(均 web devDeps);Python 侧 `ib_async`(pyproject)+ `pyinstaller`(venv)。
- **坑(已踩)**:① frozen sidecar 冷启动 ~9s(解包 242MB,含 pandas)→ `_waitReady` 调到 45s;② `run_sidecar.py` 必须传 app 对象而非 `"module:app"` 字符串,否则 frozen 找不到模块;③ `.app` ~562MB,后续可缩(去 pandas / onefile / 双架构)。
- **仍待(需用户 Apple 凭证/决策)**:Developer ID 签名 + 公证(`electron-builder.yml` 现 `identity:null` 不签名)、出正式 .dmg / Win / Linux。

## 8. 分期

- **P1**:Electron 外壳 + 直接加载现有 SPA(全走服务端)→ 桌面能跑，登录+分析可用。**零 broker 改动。**
- **P2**:Python sidecar + `localBrokerClient` + 连接门禁 + 通道选择器 → 本地 IBKR status/account/positions 只读跑通。
- **P3**:本地执行链路(approve→execute→fills)+(按退路)本地建议/风控，或(可改后端时)§6 桥接端点。
- **P4**:打包(PyInstaller + electron-builder)、签名/公证、自动更新。
- **P5(将来)**:服务端通道接云经纪(Webull)，桌面端可切换。

## 9. 风险 / 坑

- **打包 Python**:按 OS 分别 PyInstaller;macOS 需签名+公证;Windows 易被杀软误报;体积(ib_async + 依赖)。
- **TWS 单 brokerage session / clientId**:sidecar 用 master clientId;若用户同时让服务端 connector 连同一 TWS 会争用——桌面本地模式下只让 sidecar 连。
- **HKD 本位币 vs USD 标的**(见 `[[ibkr_integration]]`):敞口/风控/盈亏混币种，无论风控在本地还是服务端都要显式处理。
- **回环安全**:必须 token + 仅 `127.0.0.1` bind，否则任意本机网页可 POST 下单。
- **离线**:分析依赖服务端、交易依赖本地 TWS — UI 两条线各自独立降级。
- **双信任域**:服务端 cookie、sidecar token 各管各;审批审计在服务端，执行授权看本地连接是否就绪。

## 受影响 / 新增文件清单(预估)

新增:
- `web/electron/{main.ts,preload.ts,sidecar.ts}`、`electron-builder.yml`
- `tradingbot/sidecar/app.py`(FastAPI 薄壳)、`run_sidecar.py`
- `web/src/api/broker/{channel.ts,localBrokerClient.ts,serverBrokerClient.ts}`、`web/src/stores/brokerConnection.ts`、`web/src/components/broker/BrokerGate.tsx`、`ConnectPanel.tsx`
- (P3，可改后端时)服务端 `routers/broker.py` 增量端点 + `broker_repository.py` 快照读写

改动(前端，行为兼容):
- `web/package.json`(electron 脚本/依赖)、`web/vite.config.ts`(base/electron 适配)
- `web/src/router.tsx`(BrokerGate 包裹交易路由)
- broker 三页 + `portfolio` 改用 `BrokerChannel`
- `web/src/components/layout/Sidebar.tsx`(broker 状态 pill + 通道切换)

**核心服务端代码:P1–P2 完全不动;P3 仅在选择 ② 时新增端点,不改现有。**
