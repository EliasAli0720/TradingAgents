# TradingAgents 集成与 API/RPC 服务设计

## 目的

本文档说明如何把当前 TradingAgents 项目集成到另一个系统中，作为可复用的分析能力使用。

核心目标是：让外部项目可以请求市场分析和交易决策，而不依赖当前交互式 CLI。

## 当前状态

当前 `main` 分支已经通过 Python API 暴露了核心能力：

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

graph = TradingAgentsGraph(config=DEFAULT_CONFIG.copy())
state, decision = graph.propagate("NVDA", "2026-01-15")
```

CLI 入口同样使用这个核心引擎，但它是交互式、prompt 驱动的入口，不适合作为另一个服务的稳定集成接口。

在本文档编写时，当前被 `main` 分支跟踪的源码中没有可运行的 FastAPI、REST、gRPC 或 RPC 服务实现。本地可能能看到 `tradingagents/api`、`tradingagents/worker`、`tradingbot` 等目录，这是缓存文件或历史分支造成的现象，它们不是当前主线源码的一部分。

## 集成方式

### 方案一：直接作为 Python 包集成

在宿主项目中把 TradingAgents 当作 Python 库直接使用。

如果宿主项目也是 Python 项目，并且可以共享同一个运行时、依赖、环境变量、API key、缓存目录和进程资源，这是最快的方式。

优点：

- 实现成本最低。
- 可以直接访问 `TradingAgentsGraph`、完整状态和决策输出。
- 没有网络边界，也不需要额外的序列化层。

缺点：

- 宿主项目会继承 TradingAgents 的依赖和运行成本。
- 长耗时的 LLM 调用会在宿主服务进程内执行。
- 失败、内存占用、限流、供应商配置都会和宿主项目耦合。
- 后续隔离升级或运行多个版本会更困难。

适合原型、内部脚本或 Python 单体应用。

### 方案二：非交互式 CLI 包装

新增一个适合机器调用的命令，例如：

```bash
tradingagents run --ticker NVDA --date 2026-01-15 --json
```

宿主项目通过子进程调用该命令，并解析 JSON 输出。

优点：

- 运行边界简单。
- 不需要长期运行一个服务。
- 方便手动测试。

缺点：

- 对长任务来说，子进程编排比较脆弱。
- 流式进度、取消、重试和结构化错误处理都比较别扭。
- 每次进程启动都会重复初始化 graph 和客户端。
- 不适合高频或生产场景。

只建议用于临时自动化或低频内部任务。

### 方案三：独立 TradingAgents Service

把 TradingAgents 作为独立服务运行，宿主项目通过 HTTP、gRPC 或其他 RPC 协议调用它。

这是推荐的生产集成方式。

优点：

- 宿主项目和 TradingAgents 之间有清晰边界。
- 更容易独立扩缩容、监控、限流和部署。
- 长耗时分析可以异步执行。
- API key、模型配置、缓存、checkpoint 和 memory log 都可以隔离在 TradingAgents 服务内。
- 宿主项目可以使用任何语言。

缺点：

- 需要新增服务层。
- 需要持久化运行状态和结果。
- 需要为 worker、队列、日志和密钥制定运行方案。

适合生产环境或任何多服务架构。

## 推荐架构

建议使用异步 API 服务，而不是用一个同步 RPC 调用等待完整分析结束。

TradingAgents 分析过程可能包含多次 LLM 调用、外部数据供应商请求、重试、checkpoint 和报告生成。单次请求可能超过常见 HTTP 超时时间。因此服务应该先创建一次运行任务，返回 `run_id`，再让宿主项目查询进度或订阅事件。

```text
宿主项目
  |
  | POST /runs
  v
TradingAgents API 服务
  |
  | 入队分析任务
  v
Worker
  |
  | TradingAgentsGraph.propagate(...)
  v
LLM 供应商 / 市场数据供应商

宿主项目
  |
  | GET /runs/{run_id}
  | GET /runs/{run_id}/events
  | GET /runs/{run_id}/report
  v
TradingAgents API 服务
```

## 最小 API 面

### 创建分析任务

```http
POST /runs
Content-Type: application/json
```

请求：

```json
{
  "ticker": "NVDA",
  "trade_date": "2026-01-15",
  "asset_type": "stock",
  "analysts": ["market", "social", "news", "fundamentals"],
  "config": {
    "llm_provider": "openai",
    "deep_think_llm": "gpt-5.4",
    "quick_think_llm": "gpt-5.4-mini",
    "output_language": "Chinese",
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1
  }
}
```

响应：

```json
{
  "run_id": "run_01J...",
  "status": "queued"
}
```

### 查询任务状态

```http
GET /runs/{run_id}
```

响应：

```json
{
  "run_id": "run_01J...",
  "status": "running",
  "ticker": "NVDA",
  "trade_date": "2026-01-15",
  "current_step": "News Analyst",
  "created_at": "2026-05-25T10:00:00Z",
  "started_at": "2026-05-25T10:00:03Z",
  "finished_at": null,
  "error": null
}
```

### 流式任务事件

```http
GET /runs/{run_id}/events
```

使用 Server-Sent Events 或 WebSocket 返回进度更新。

事件 payload 示例：

```json
{"type":"run_started","run_id":"run_01J..."}
{"type":"node_started","node":"Market Analyst"}
{"type":"node_finished","node":"Market Analyst"}
{"type":"run_finished","run_id":"run_01J..."}
```

### 获取最终结果

```http
GET /runs/{run_id}/result
```

响应：

```json
{
  "run_id": "run_01J...",
  "status": "completed",
  "decision": "BUY",
  "confidence": null,
  "reasoning": "...",
  "reports": {
    "market_report": "...",
    "sentiment_report": "...",
    "news_report": "...",
    "fundamentals_report": "...",
    "investment_plan": "...",
    "trader_investment_plan": "...",
    "final_trade_decision": "..."
  }
}
```

### 取消分析任务

```http
POST /runs/{run_id}/cancel
```

取消仍处于 `queued` 或 `running` 的分析任务。取消成功后，任务进入终态 `cancelled`，不会再被 worker 覆盖为 `succeeded` 或 `failed`。

成功响应：

```json
{
  "run_id": "run_01J...",
  "status": "cancelled"
}
```

状态码：

- `200`：取消成功，或任务已经处于 `cancelled`。
- `401`：未登录。
- `403`：当前用户角色不是 `admin` / `operator`，或 CSRF 校验失败。
- `404`：run 不存在，或当前用户无权访问该 run。
- `409`：run 已经 `succeeded` 或 `failed`，不能再取消。

取消事件会通过 `GET /runs/{run_id}/events` 输出：

```text
event: run_cancelled
data: {"run_id":"run_01J...","reason":"user requested cancellation"}
```

实现语义：

- queued Celery task 会 best-effort revoke。
- running run 会先在 PostgreSQL 中标记为 `cancelled`。
- worker 在 executor 返回后会重新读取 run 状态；如果已经取消，不写入 success result。
- 已经进入 `TradingAgentsGraph.propagate()` 的任务不保证立即停止当前 LLM 或数据供应商调用；这需要后续 graph 内协作式取消。

### 读取可选模型目录

```http
GET /settings/model/options
```

宿主项目应该通过该接口读取 TradingAgents 服务端数据库中的 provider、quick 模型、deep 模型、默认 endpoint、是否允许自定义模型、以及所需 API key 环境变量。前端配置表单应优先使用这个目录生成选择项，再通过 `PUT /settings/model` 保存用户选择。

模型目录由服务启动时初始化到 `llm_provider_options` 和 `llm_model_options` 表；保存模型设置时也会从这两张表校验 provider/model 组合。

### 校验设置

```http
POST /settings/model/validate
```

当前实现中的 `POST /settings/model/validate` 会先校验当前用户模型配置是否具备可用密钥来源：用户加密密钥、服务端统一环境变量，或 provider 不需要密钥。密钥来源可用时，接口会使用当前配置初始化 LLM client，发起短超时、低成本 live probe。

live probe 结果会归类为：

- `success`
- `invalid_api_key`
- `model_not_found`
- `endpoint_unreachable`
- `permission_denied`
- `timeout`
- `provider_error`

说明：

- live probe 只能证明“模型可调用”，不能证明模型回答内容真实可靠。回答真实性需要业务层补充数据源引用、交叉验证、置信度标记和人工审核机制。

## 运行组件

### API 层

API 层负责接收请求、校验输入、创建任务记录、返回状态并暴露结果。它不应该在请求处理函数中直接执行长耗时分析。

推荐实现：FastAPI。

### Worker 层

Worker 层负责执行 `TradingAgentsGraph.propagate()`，并把进度、最终状态和错误写入存储。

第一版推荐实现：

- 本地开发使用进程内 background task。
- 生产环境使用 Redis Queue、Celery、Dramatiq 或其他持久化 worker 队列。

### 存储层

服务需要存储任务元数据和结果。

最小字段：

- `run_id`
- `ticker`
- `trade_date`
- `asset_type`
- `status`
- `request_config`
- `current_step`
- `decision`
- `final_state`
- `error`
- `created_at`
- `started_at`
- `finished_at`

分析 API 的业务状态应使用 PostgreSQL。API/worker 运行时必须通过 `DATABASE_URL` 显式连接 PostgreSQL；SQLite 只保留给单元测试夹具和非 API 子系统的本地状态。

本地开发推荐使用 Docker Compose 启动 PostgreSQL 和 Redis：

```bash
docker compose up -d postgres redis
```

宿主机直接运行 `uvicorn` / `celery` 时使用：

```bash
TRADINGAGENTS_API_ENV=development
DATABASE_URL=postgresql+psycopg://tradingagents:tradingagents@localhost:5432/tradingagents
REDIS_URL=redis://localhost:6379/0
```

Docker Compose 内部容器使用服务名连接：

```bash
DOCKER_DATABASE_URL=postgresql+psycopg://tradingagents:tradingagents@postgres:5432/tradingagents
DOCKER_REDIS_URL=redis://redis:6379/0
```

生产环境必须显式提供托管服务连接：

```bash
TRADINGAGENTS_API_ENV=production
DATABASE_URL=postgresql+psycopg://prod_user:prod_password@prod-postgres.example.com:5432/tradingagents
REDIS_URL=redis://prod-redis.example.com:6379/0
```

### 配置和密钥

供应商 API key 支持两种来源：

- 服务端统一密钥：放在 TradingAgents 服务环境中，适合内部部署和统一计费。
- 用户自己的密钥：通过模型设置接口保存，服务端用 `MODEL_API_KEY_ENCRYPTION_KEY` 加密落库，查询时只返回掩码。

运行时优先使用用户自己的密钥；用户未配置时，回退使用服务端统一密钥。

宿主项目可以选择经过校验的安全选项，例如 ticker、日期、输出语言、分析师集合和允许的模型 profile。除非是内部可信部署，否则宿主项目不应该传入任意 backend URL。

## 错误处理

服务应该返回结构化错误：

```json
{
  "code": "LLM_PROVIDER_AUTH_FAILED",
  "message": "OpenAI API key is missing or invalid.",
  "retryable": false
}
```

推荐错误分类：

- `INVALID_REQUEST`
- `UNSUPPORTED_PROVIDER`
- `UNSUPPORTED_MODEL`
- `MISSING_API_KEY`
- `DATA_PROVIDER_ERROR`
- `LLM_PROVIDER_ERROR`
- `RUN_TIMEOUT`
- `RUN_CANCELLED`
- `INTERNAL_ERROR`

## 取消和超时

当前 API 已支持：

- `POST /runs/{run_id}/cancel`

后续生产加固还应继续补：

- 单任务超时
- 供应商重试策略
- 保留部分进度
- 在适用时使用 checkpoint resume

取消能力很重要，因为基于 LLM 的图执行可能既昂贵又耗时。当前实现先保证状态一致性和结果不覆盖；运行中的即时中断应作为后续 graph 内协作式取消能力继续推进。

## 安全说明

服务应该对来自宿主项目的请求进行认证。

最低控制项：

- API key 或服务间 token。
- 请求大小限制。
- 允许的 ticker/date 校验。
- 允许的供应商/模型白名单。
- 按调用方限流。
- 对分析请求和交易相关决策记录审计日志。

如果结果可能被用于真实交易，API 应该明确区分“分析”和“执行”。交易执行接口应该要求显式审批或风险闸门。

## 推荐实施阶段

### 阶段一：库适配层

围绕 `TradingAgentsGraph` 创建一个小型内部适配层：

```python
def run_analysis(request: AnalysisRequest) -> AnalysisResult:
    ...
```

该适配层用于隔离服务其他部分和原始 graph API，并定义稳定的领域契约。

### 阶段二：最小 HTTP API

新增：

- `POST /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/result`

第一版使用 PostgreSQL 存储 run/event/result，并通过 worker 异步执行分析。

### 阶段三：进度事件

新增：

- `GET /runs/{run_id}/events`
- 结构化节点进度事件
- 持久化事件日志

### 阶段四：生产加固

新增：

- 队列驱动的 worker
- 认证
- 限流
- graph 内协作式取消
- 重试
- 可观测性
- 部署配置

## 建议

如果要把 TradingAgents 真正集成到另一个项目中，建议使用独立的 TradingAgents 服务，并采用异步 API。

只有当宿主项目也是 Python、使用量较低，并且不需要进程隔离时，才建议直接 Python 集成。CLI 集成应该被视为临时自动化方式，而不是长期服务边界。
