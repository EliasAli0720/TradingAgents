# TradingAgents 当前系统说明

生成时间：2026-06-02
范围：当前工作区代码，不是上游 README 的通用介绍。本文档按功能维度拆分，目标是让没有接触过本项目的人能快速理解系统有哪些功能、每个功能的调用链、数据存储和边界条件。

## 一句话定位

这个项目已经不只是原始的 TradingAgents 多智能体分析框架。当前系统包含三层：

1. **投研分析层**：LangGraph 多智能体分析股票或 crypto，输出 5 档评级和分阶段报告。
2. **Web/API 队列层**：FastAPI + PostgreSQL + Redis + Celery，把分析任务变成多用户、可排队、可取消、可追踪进度的 run。
3. **交易执行层**：把分析结果转成交易建议，经过风控和人工审批后走 Webull 或 IBKR 下单；也支持手动快速下单。

最重要的心智模型：

```text
用户登录 Web/Electron
  -> 配置模型 API key
  -> 创建分析 run 或生成推荐
  -> Celery worker 执行 TradingAgentsGraph
  -> 保存报告、结果、事件、翻译
  -> 如果最终信号可交易，生成 trade approval
  -> 人工批准后走当前 broker 下单
```

交易接入必须分清三条路径：

```text
Webull server broker
  当前登录用户自己的 Webull 凭据 -> FastAPI -> Webull REST SDK

IBKR server broker
  平台共享 IBKR connector -> Redis 命令队列 -> 单例 TWS/IB Gateway socket

IBKR desktop local broker
  Electron -> 本机 sidecar -> 用户本机 TWS/IB Gateway
  服务端仍记录 approval/order mirror
```

## 文档目录

- [00 功能地图](./00-feature-map.md)：系统有哪些功能、用户能看到什么、背后由哪些模块支撑。
- [01 API、认证与数据层](./01-api-auth-data.md)：FastAPI 入口、cookie session、CSRF、权限、数据库、Repository 和主要路由。
- [02 分析、推荐与 worker](./02-analysis-recommendations-worker.md)：分析 run 生命周期、Celery 调度、LangGraph 执行、推荐批次、报告和翻译。
- [03 Broker 与交易逻辑](./03-broker-trading-webull-ibkr.md)：Webull/IBKR/sidecar 三套交易路径、凭据、交易建议、审批、风控和手动下单。
- [04 前端与桌面端](./04-frontend-desktop.md)：React 路由、API client、BrokerGate、交易 UI、Electron sidecar 通信。
- [05 运行、配置与排障](./05-runtime-config-ops.md)：怎么跑起来、环境变量、端口、测试、常见问题。
- [06 数据模型与状态参考](./06-data-models-reference.md)：核心表、状态机、Repository 职责和关键字段。

## 当前代码里的关键事实

- API 鉴权是 **cookie session + double-submit CSRF**，不是 JWT。
- 第一位注册用户自动是 `admin`，后续用户默认 `viewer`。
- `POST /runs` 只创建 `queued` run，不直接触发 Celery；实际执行依赖 Celery beat 的 dispatcher。
- 分析结果最终是 `BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL` 五档。只有除 `HOLD` 外的四档会尝试生成交易建议。
- 用户有 `connected` Webull credential 时，`/broker/*` 会优先走该用户的 Webull broker；没有 Webull 时才回落 IBKR server connector。
- Webull 是云 REST per-user broker，不需要 TWS、Redis connector 或本地 sidecar。
- IBKR 有两套路径：server 共享 connector 和 desktop 本地 sidecar，不能混为一谈。
- 订单列表、审批、业绩统计主要读服务端 DB mirror，不等价于实时 broker 原始订单列表。
- DB 初始化是 `create_all + additive schema patch`，没有 Alembic 迁移体系。
- 当前工作区已有多处未提交改动，文档按当前文件状态描述。
