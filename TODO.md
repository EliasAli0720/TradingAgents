# TODO

更新时间：2026-05-27

本文档集中记录当前项目里仍有价值的后续工作。其他设计文档保留上下文说明，但不再作为待办入口。

## P0 / P1

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
