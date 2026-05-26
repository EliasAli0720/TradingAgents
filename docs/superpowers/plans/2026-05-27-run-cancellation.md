# 取消分析任务实现计划

> **给 agentic workers：** 必须使用子技能 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务执行本计划。步骤使用 checkbox（`- [ ]`）记录进度。

**目标：** 为分析任务增加已鉴权的取消接口：`POST /runs/{run_id}/cancel`。

**架构：** PostgreSQL 仍是任务状态的唯一权威数据源。取消被建模为 `analysis_runs.status = "cancelled"` 终态，并写入持久化事件 `run_cancelled`；Celery revoke 只作为队列/进程层的 best-effort 控制，不能替代数据库状态机。worker 在 executor 返回后必须重新检查数据库状态，避免把已经取消的任务覆盖成成功。

**技术栈：** FastAPI、SQLAlchemy、Celery、pytest、FastAPI `TestClient`。

---

## 实现状态

已完成：

- [x] `tradingagents/api/schemas.py`：`RunStatus` 已增加 `cancelled`。
- [x] `tradingagents/api/schemas.py`：已增加 `CancelRunResponse`。
- [x] `tradingagents/api/repositories.py`：已增加 `cancel_run(...)`。
- [x] `tradingagents/api/repositories.py`：`mark_running`、`store_success`、`store_failure` 已把 `cancelled` 当作终态保护。
- [x] `tradingagents/api/deps.py`：已增加可注入的 Celery revoke 依赖。
- [x] `tradingagents/api/routers/runs.py`：已增加 `POST /runs/{run_id}/cancel`。
- [x] `tradingagents/api/routers/runs.py`：SSE 已把 `run_cancelled` 当作终止事件。
- [x] `tradingagents/worker/jobs.py`：executor 返回后已重新检查 run 是否已被取消。
- [x] `tests/api/test_repositories.py`：已增加取消状态机测试。
- [x] `tests/api/test_runs_routes.py`：已增加 cancel endpoint 的鉴权、CSRF、状态码和 revoke 测试。
- [x] `tests/api/test_sse_events.py`：已增加 `run_cancelled` 事件流测试。
- [x] `tests/worker/test_jobs.py`：已增加 worker 不覆盖 cancelled run 的竞态测试。
- [x] `docs/integration-api-rpc.md`：已把取消接口写成已实现 API 文档。

仍未完成的后续增强：

- [ ] graph 内协作式取消：已经进入 `TradingAgentsGraph.propagate()` 的任务仍不保证立即停止当前 LLM 或数据供应商调用。
- [ ] 单任务超时策略。
- [ ] 供应商重试策略。
- [ ] 部分进度保留和恢复语义。
- [ ] 结合 checkpoint resume 的取消后续处理。

## 当前代码定位

- `tradingagents/api/schemas.py`：定义 API 请求/响应 schema，目前 `RunStatus = Literal["queued", "running", "succeeded", "failed"]`。
- `tradingagents/api/repositories.py`：封装 run 状态转换，目前只有创建、领取 queued、标记 running、成功、失败、查询事件。
- `tradingagents/api/routers/runs.py`：提供 `POST /runs`、`GET /runs/{run_id}`、`GET /runs/{run_id}/result`、`GET /runs/{run_id}/events`。
- `tradingagents/worker/jobs.py`：Celery task 执行入口，目前领取 queued 后调用 executor，随后直接写成功或失败。
- `tradingagents/graph/trading_graph.py`：核心 graph 目前主要通过 `graph.invoke(...)` 一次执行；本计划不改 graph 内部协作式中断。

## 文件变更范围

- 修改：`tradingagents/api/schemas.py`
  - 给 `RunStatus` 增加 `cancelled`。
  - 增加 `CancelRunResponse`。
- 修改：`tradingagents/api/repositories.py`
  - 增加终态常量和 `cancel_run`。
  - 让 `mark_running`、`store_success`、`store_failure` 拒绝覆盖 cancelled run。
- 修改：`tradingagents/api/deps.py`
  - 增加可注入的 task revoke 依赖，方便测试替换。
- 修改：`tradingagents/api/routers/runs.py`
  - 增加 `POST /runs/{run_id}/cancel`，只允许 `admin` 和 `operator`。
  - SSE 终态事件增加 `run_cancelled`。
- 修改：`tradingagents/worker/jobs.py`
  - executor 返回后刷新 run 状态；如果已经取消，直接返回，不写 success result。
- 修改：`tests/api/test_repositories.py`
  - 覆盖 queued/running 取消和终态保护。
- 修改：`tests/api/test_runs_routes.py`
  - 覆盖 cancel endpoint 的鉴权、owner scope、CSRF、状态码和 Celery revoke。
- 修改：`tests/api/test_sse_events.py`
  - 覆盖 `run_cancelled` 能关闭 SSE stream。
- 修改：`tests/worker/test_jobs.py`
  - 覆盖 worker 不覆盖 cancelled run。

## Task 0：执行前工作区检查

- [ ] **Step 1：检查当前工作区状态**

运行：

```bash
git status --short
git diff -- tests/worker/test_jobs.py
```

预期：记录已有本地改动。不要覆盖用户已有改动。

- [ ] **Step 2：先处理当前 worker/model-settings 测试缺口**

如果 `tests/worker/test_jobs.py` 已经被本地改动为期望 executor 接收 `llm_config`，必须先完成对应实现，或确认该改动是误改后再处理。不能在取消任务实现里静默覆盖它。

运行：

```bash
python -m pytest tests/worker/test_jobs.py -q
```

预期：如果当前 worker 已经同步支持 `llm_config`，测试应通过；如果失败，先修这个失败，再继续 Task 1。

## Task 1：Repository 取消状态机

**文件：**
- 修改：`tradingagents/api/schemas.py`
- 修改：`tradingagents/api/repositories.py`
- 测试：`tests/api/test_repositories.py`

- [ ] **Step 1：先写失败测试**

在 `tests/api/test_repositories.py` 增加：

```python
def test_repository_cancels_queued_run():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])

    cancelled = repo.cancel_run(run.run_id, "user requested cancellation")
    session.commit()

    assert cancelled.status == "cancelled"
    assert cancelled.finished_at is not None
    assert cancelled.current_step == "Cancelled"
    assert cancelled.error == "user requested cancellation"
    assert repo.list_events(run.run_id)[-1].event_type == "run_cancelled"


def test_repository_cancels_running_run():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
    repo.mark_running(run.run_id)

    repo.cancel_run(run.run_id, "user requested cancellation")
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "cancelled"
    assert saved.current_step == "Cancelled"
    assert [event.event_type for event in repo.list_events(run.run_id)] == [
        "run_queued",
        "run_started",
        "run_cancelled",
    ]


def test_cancelled_run_cannot_be_marked_successful_or_failed_or_running():
    session = _session()
    repo = AnalysisRunRepository(session)
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
    repo.cancel_run(run.run_id, "user requested cancellation")

    with pytest.raises(ValueError, match="cancelled"):
        repo.mark_running(run.run_id)
    with pytest.raises(ValueError, match="cancelled"):
        repo.store_success(run.run_id, "Hold", {}, {})
    with pytest.raises(ValueError, match="cancelled"):
        repo.store_failure(run.run_id, "provider failed")
```

- [ ] **Step 2：运行测试确认 RED**

运行：

```bash
python -m pytest tests/api/test_repositories.py::test_repository_cancels_queued_run tests/api/test_repositories.py::test_repository_cancels_running_run tests/api/test_repositories.py::test_cancelled_run_cannot_be_marked_successful_or_failed_or_running -q
```

预期：失败，原因是 `cancel_run` 和 `cancelled` 状态尚不存在。

- [ ] **Step 3：实现最小状态机**

把 `tradingagents/api/schemas.py` 中的 `RunStatus` 改为：

```python
RunStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
```

在 `tradingagents/api/repositories.py` 顶层增加：

```python
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
```

把 `mark_running` 的终态判断改成：

```python
if run.status == "running":
    return run
if run.status in TERMINAL_STATUSES:
    raise ValueError(f"Cannot mark terminal run {run_id} as running")
```

把 `store_success` 的失败保护改成：

```python
if run.status in {"failed", "cancelled"}:
    raise ValueError(f"Cannot mark {run.status} run {run_id} as succeeded")
```

把 `store_failure` 的成功保护改成：

```python
if run.status == "failed":
    return
if run.status in {"succeeded", "cancelled"}:
    raise ValueError(f"Cannot mark {run.status} run {run_id} as failed")
```

在 `AnalysisRunRepository` 增加：

```python
def cancel_run(self, run_id: str, reason: str = "run cancelled") -> AnalysisRun:
    run = self.require_run(run_id)
    if run.status == "cancelled":
        return run
    if run.status in {"succeeded", "failed"}:
        raise ValueError(f"Cannot cancel terminal run {run_id}")

    run.status = "cancelled"
    run.finished_at = utcnow()
    run.current_step = "Cancelled"
    run.error = reason
    self.add_event(run_id, "run_cancelled", {"run_id": run_id, "reason": reason})
    return run
```

- [ ] **Step 4：运行 repository 测试**

运行：

```bash
python -m pytest tests/api/test_repositories.py -q
```

预期：通过。

- [ ] **Step 5：提交**

```bash
git add tradingagents/api/schemas.py tradingagents/api/repositories.py tests/api/test_repositories.py
git commit -m "feat(api): add run cancellation state"
```

## Task 2：取消路由和 Celery revoke

**文件：**
- 修改：`tradingagents/api/schemas.py`
- 修改：`tradingagents/api/deps.py`
- 修改：`tradingagents/api/routers/runs.py`
- 测试：`tests/api/test_runs_routes.py`

- [ ] **Step 1：先写失败测试**

在 `tests/api/test_runs_routes.py` 的 imports 中增加：

```python
from tradingagents.api.deps import get_task_revoke
```

增加测试：

```python
def test_post_cancel_queued_run_marks_cancelled_and_revokes_task():
    client, Session, _ = _client()
    revoked = []
    client.app.dependency_overrides[get_task_revoke] = lambda: revoked.append

    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        repo.set_celery_task_id(run.run_id, "celery-test-id")
        run_id = run.run_id
        session.commit()

    response = client.post(f"/runs/{run_id}/cancel")

    assert response.status_code == 200
    assert response.json() == {"run_id": run_id, "status": "cancelled"}
    assert revoked == ["celery-test-id"]
    with Session() as session:
        saved = AnalysisRunRepository(session).get_run(run_id)
        assert saved.status == "cancelled"


def test_post_cancel_missing_run_returns_404():
    client, _Session, _ = _client()

    response = client.post("/runs/run_missing/cancel")

    assert response.status_code == 404


def test_post_cancel_succeeded_run_returns_409():
    client, Session, _ = _client()
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        repo.store_success(run.run_id, "Hold", {}, {})
        run_id = run.run_id
        session.commit()

    response = client.post(f"/runs/{run_id}/cancel")

    assert response.status_code == 409


def test_post_cancel_requires_authentication():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    client = TestClient(app)

    response = client.post("/runs/run_any/cancel")

    assert response.status_code == 401


def test_post_cancel_missing_csrf_returns_403():
    client, Session, _ = _client()
    client.headers.pop("X-CSRF-Token", None)
    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        run_id = run.run_id
        session.commit()

    response = client.post(f"/runs/{run_id}/cancel")

    assert response.status_code == 403
```

如果项目已有 viewer 测试 helper，把 viewer 不能取消的断言放到 `tests/api/test_runs_authz.py`，预期 `403`。

- [ ] **Step 2：运行测试确认 RED**

运行：

```bash
python -m pytest tests/api/test_runs_routes.py -q
```

预期：失败，原因是 `get_task_revoke` 和 `POST /runs/{run_id}/cancel` 不存在。

- [ ] **Step 3：实现 schema、依赖和路由**

在 `tradingagents/api/schemas.py` 增加：

```python
class CancelRunResponse(BaseModel):
    run_id: str
    status: Literal["cancelled"]
```

在 `tradingagents/api/deps.py` 增加：

```python
def revoke_analysis_task(task_id: str) -> None:
    run_analysis_task.app.control.revoke(task_id)


def get_task_revoke() -> Callable[[str], None]:
    return revoke_analysis_task
```

在 `tradingagents/api/routers/runs.py` 的 schema imports 增加 `CancelRunResponse`，deps imports 增加 `get_task_revoke`，并增加路由：

```python
@router.post("/{run_id}/cancel", response_model=CancelRunResponse)
def cancel_run(
    run_id: str,
    repo: AnalysisRunRepository = Depends(get_scoped_repository),
    revoke=Depends(get_task_revoke),
    _user: User = Depends(require_role("admin", "operator")),
):
    run = repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status in {"succeeded", "failed"}:
        raise HTTPException(status_code=409, detail=f"run is already {run.status}")

    task_id = run.celery_task_id
    try:
        cancelled = repo.cancel_run(run_id, "user requested cancellation")
        repo.session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if task_id:
        revoke(task_id)
    return CancelRunResponse(run_id=cancelled.run_id, status="cancelled")
```

- [ ] **Step 4：运行路由测试**

运行：

```bash
python -m pytest tests/api/test_runs_routes.py tests/api/test_runs_authz.py -q
```

预期：通过。

- [ ] **Step 5：提交**

```bash
git add tradingagents/api/schemas.py tradingagents/api/deps.py tradingagents/api/routers/runs.py tests/api/test_runs_routes.py tests/api/test_runs_authz.py
git commit -m "feat(api): expose run cancellation endpoint"
```

## Task 3：worker 竞态保护

**文件：**
- 修改：`tradingagents/worker/jobs.py`
- 测试：`tests/worker/test_jobs.py`

- [ ] **Step 1：先写失败测试**

在 `tests/worker/test_jobs.py` 增加：

```python
def test_execute_analysis_run_does_not_overwrite_cancelled_run_after_executor_returns():
    session, repo = _repo()
    run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
    session.commit()

    def fake_executor(ticker, trade_date, asset_type, analysts):
        repo.cancel_run(run.run_id, "user requested cancellation")
        session.commit()
        return {
            "decision": "Hold",
            "reports": {"final_trade_decision": "Rating: Hold"},
            "final_state": {"company_of_interest": ticker},
        }

    execute_analysis_run(repo, run.run_id, fake_executor)
    session.commit()

    saved = repo.get_run(run.run_id)
    assert saved.status == "cancelled"
    assert repo.get_result(run.run_id) is None
    assert [event.event_type for event in repo.list_events(run.run_id)] == [
        "run_queued",
        "run_started",
        "run_cancelled",
    ]
```

如果 Task 0 已经把 worker executor 改成接收 `llm_config`，则这个测试里的 fake executor 签名同步改为五参，并保留同样的函数体：

```python
def fake_executor(ticker, trade_date, asset_type, analysts, llm_config):
    repo.cancel_run(run.run_id, "user requested cancellation")
    session.commit()
    return {
        "decision": "Hold",
        "reports": {"final_trade_decision": "Rating: Hold"},
        "final_state": {"company_of_interest": ticker},
    }
```

- [ ] **Step 2：运行测试确认 RED**

运行：

```bash
python -m pytest tests/worker/test_jobs.py::test_execute_analysis_run_does_not_overwrite_cancelled_run_after_executor_returns -q
```

预期：失败，原因是 worker 在 executor 返回后仍调用 `store_success`。

- [ ] **Step 3：实现 executor 后状态检查**

在 `tradingagents/worker/jobs.py` 中，executor 返回后、`store_success` 前增加：

```python
repo.session.refresh(run)
if run.status == "cancelled":
    repo.session.commit()
    return
```

如果 Task 0 已经引入 `llm_config` executor 参数，保留该参数，不要退回四参签名。

- [ ] **Step 4：运行 worker 测试**

运行：

```bash
python -m pytest tests/worker/test_jobs.py -q
```

预期：通过。

- [ ] **Step 5：提交**

```bash
git add tradingagents/worker/jobs.py tests/worker/test_jobs.py
git commit -m "fix(worker): do not overwrite cancelled runs"
```

## Task 4：SSE 取消终态事件

**文件：**
- 修改：`tradingagents/api/routers/runs.py`
- 测试：`tests/api/test_sse_events.py`

- [ ] **Step 1：先写失败测试**

在 `tests/api/test_sse_events.py` 增加：

```python
def test_events_stream_closes_after_cancelled_event():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    def override_session():
        with Session() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    app.dependency_overrides[get_stream_session_factory] = lambda: Session

    client = TestClient(app)
    client.post("/auth/register", json={"username": "alice", "password": "hunter22a"})
    client.post("/auth/login", json={"username": "alice", "password": "hunter22a"})

    with Session() as session:
        repo = AnalysisRunRepository(session)
        run = repo.create_run("NVDA", date(2026, 1, 15), "stock", ["market"])
        run_id = run.run_id
        repo.cancel_run(run_id, "user requested cancellation")
        session.commit()

    with client.stream("GET", f"/runs/{run_id}/events") as response:
        assert response.status_code == 200
        text = "".join(response.iter_text())

    assert "event: run_queued" in text
    assert "event: run_cancelled" in text
    assert text.index("run_queued") < text.index("run_cancelled")
```

- [ ] **Step 2：运行测试确认 RED**

运行：

```bash
python -m pytest tests/api/test_sse_events.py::test_events_stream_closes_after_cancelled_event -q
```

预期：失败或卡住，原因是 SSE 循环只把 `run_succeeded` 和 `run_failed` 当终态。

- [ ] **Step 3：把 `run_cancelled` 加入 SSE 终态集合**

在 `tradingagents/api/routers/runs.py` 中把：

```python
if event.event_type in {"run_succeeded", "run_failed"}:
```

改为：

```python
if event.event_type in {"run_succeeded", "run_failed", "run_cancelled"}:
```

- [ ] **Step 4：运行 SSE 测试**

运行：

```bash
python -m pytest tests/api/test_sse_events.py -q
```

预期：通过。

- [ ] **Step 5：提交**

```bash
git add tradingagents/api/routers/runs.py tests/api/test_sse_events.py
git commit -m "feat(api): stream run cancellation events"
```

## Task 5：文档和最终验证

**文件：**
- 修改：`docs/integration-api-rpc.md`

- [ ] **Step 1：运行聚焦测试**

运行：

```bash
python -m pytest tests/api/test_repositories.py tests/api/test_runs_routes.py tests/api/test_runs_authz.py tests/api/test_sse_events.py tests/worker/test_jobs.py -q
```

预期：通过。

- [ ] **Step 2：运行完整测试**

运行：

```bash
python -m pytest -q
```

预期：通过。

- [ ] **Step 3：更新中文集成文档**

修改 `docs/integration-api-rpc.md`，把 `POST /runs/{run_id}/cancel` 从“生产 API 集成应该支持”调整为已实现接口，写清：

- `POST /runs/{run_id}/cancel`：取消 queued 或 running run。
- 成功响应：`200`，body 示例为 `{"run_id": "run_abc123", "status": "cancelled"}`。
- 未登录：`401`。
- 角色不是 `admin` 或 `operator`：`403`。
- CSRF 校验失败：`403`。
- run 不存在或无权访问：`404`。
- run 已经 `succeeded` 或 `failed`：`409`。
- SSE 会产生 `run_cancelled` 事件并关闭连接。
- queued Celery task 会 best-effort revoke；已经进入 graph 执行的任务通过数据库状态防止结果覆盖，但不保证立即停止当前 LLM 调用。

- [ ] **Step 4：提交文档**

```bash
git add docs/integration-api-rpc.md
git commit -m "docs: document run cancellation api"
```

## 后续增强：graph 内协作式取消

本计划只实现“API/状态机层取消”：它能阻止结果覆盖，并尝试撤销 queued Celery task。对于已经进入 `TradingAgentsGraph.propagate()` 的 running 任务，当前 graph 可能会继续跑到本次 `invoke` 结束。

后续如果要降低运行中 LLM 成本，需要单独设计“协作式取消”：

- 改 `tradingagents/graph/trading_graph.py`，从一次性 `graph.invoke(...)` 调整为可检查取消信号的执行方式。
- 在节点或 streamed chunk 边界查询数据库状态。
- 发现 `status == "cancelled"` 后停止后续节点，并保留已完成节点的部分进度。
- 这会影响核心图执行路径，应单独写计划、单独测试，不和本次 API 状态机取消混在一起。
