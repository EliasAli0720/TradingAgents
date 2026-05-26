# TradingAgents 项目深度学习笔记

适用分支：`phase/6-login-page`

更新时间：2026-05-26

本文档记录当前仓库的工程结构、核心运行链路、主要模块职责和已知注意点，方便后续开发、排障或接入其它系统时快速建立上下文。

## 1. 项目定位

TradingAgents 是一个多智能体 LLM 金融投研与交易决策框架。核心目标是把真实交易团队的角色拆成多个 LLM agent，由分析师团队、研究员团队、交易员、风险管理团队和组合经理协作，最终产出交易评级和完整推理报告。

当前分支在原有 TradingAgents 分析框架之上，新增了 `tradingbot/` 自动交易机器人与 Streamlit 仪表盘：

- `tradingagents/`：多智能体分析引擎。
- `cli/`：交互式命令行入口。
- `tradingbot/`：自动交易、Broker 抽象、风控、组合数据库、Dashboard、登录注册。
- `docs/`：集成方案、UI 规范和本文档。
- `tests/`：核心配置、LLM provider、checkpoint、memory log、信号解析等单元测试。

## 2. 核心架构

### 2.1 TradingAgents 分析引擎

核心类是 `tradingagents.graph.trading_graph.TradingAgentsGraph`。

一次 `propagate(ticker, trade_date, asset_type="stock")` 大致流程：

1. 读取配置并初始化 LLM client。
2. 初始化数据工具节点。
3. 构建 LangGraph workflow。
4. 注入初始 state，包括 ticker、交易日期、资产类型和历史 memory context。
5. 依次执行分析师、研究员、交易员、风险辩论员、组合经理节点。
6. 保存完整状态 JSON。
7. 写入 persistent decision log。
8. 从 Portfolio Manager 输出中解析最终 5 档评级。

主要文件：

- `tradingagents/graph/trading_graph.py`：顶层编排、配置、日志、memory log、checkpoint。
- `tradingagents/graph/setup.py`：LangGraph 节点和边。
- `tradingagents/graph/conditional_logic.py`：工具调用循环、研究辩论轮次、风险辩论轮次。
- `tradingagents/graph/propagation.py`：初始 state 和 graph invoke 参数。
- `tradingagents/graph/signal_processing.py`：从 Portfolio Manager markdown 中解析评级。
- `tradingagents/graph/checkpointer.py`：LangGraph SQLite checkpoint/resume。

### 2.2 Agent 角色

Agent state 定义在 `tradingagents/agents/utils/agent_states.py`。核心字段包括：

- `market_report`
- `sentiment_report`
- `news_report`
- `fundamentals_report`
- `investment_debate_state`
- `investment_plan`
- `trader_investment_plan`
- `risk_debate_state`
- `final_trade_decision`
- `past_context`

角色分布：

- 分析师团队：
  - `market_analyst.py`：价格、技术指标、趋势。
  - `sentiment_analyst.py`：新闻、StockTwits、Reddit 等情绪数据。
  - `news_analyst.py`：公司新闻、宏观新闻、内幕交易。
  - `fundamentals_analyst.py`：财务与基本面。
- 研究员团队：
  - `bull_researcher.py`
  - `bear_researcher.py`
  - `research_manager.py`
- 交易员：
  - `tradingagents/agents/trader/trader.py`
- 风险管理团队：
  - `aggressive_debator.py`
  - `conservative_debator.py`
  - `neutral_debator.py`
- 组合经理：
  - `portfolio_manager.py`

`research_manager`、`trader`、`portfolio_manager` 使用 `tradingagents/agents/schemas.py` 中的 Pydantic schema 做结构化输出，然后再渲染回 markdown，保证 CLI、报告、memory log 和解析器继续消费同一种文本形态。

最终组合评级是 5 档：

- `Buy`
- `Overweight`
- `Hold`
- `Underweight`
- `Sell`

Trader 自身仍使用 3 档交易动作：

- `Buy`
- `Hold`
- `Sell`

### 2.3 数据流

Agent 不直接调用 yfinance 或 Alpha Vantage。工具调用路径是：

```text
agent prompt
  -> langchain tool
  -> tradingagents/agents/utils/*_tools.py
  -> tradingagents/dataflows/interface.py
  -> vendor implementation
```

数据源路由配置在 `DEFAULT_CONFIG["data_vendors"]` 和 `DEFAULT_CONFIG["tool_vendors"]`。

支持的数据 vendor：

- `yfinance`
- `alpha_vantage`

`dataflows/interface.py` 会按工具方法找到所属 category，再按配置选择 vendor。Alpha Vantage 限流时可 fallback 到其它可用 vendor。

### 2.4 LLM provider

LLM client 工厂在 `tradingagents/llm_clients/factory.py`。

支持的 provider 包括：

- `openai`
- `google`
- `anthropic`
- `xai`
- `deepseek`
- `qwen`
- `qwen-cn`
- `glm`
- `glm-cn`
- `minimax`
- `minimax-cn`
- `openrouter`
- `ollama`
- `azure`

OpenAI-compatible provider 共用 `OpenAIClient`，但用 capability table 处理模型差异：

- `DeepSeekChatOpenAI`：处理 `reasoning_content` roundtrip。
- `MinimaxChatOpenAI`：处理 `reasoning_split=True`。
- `NormalizedChatOpenAI`：统一 normalize content，并根据 `capabilities.py` 决定 structured output 方法和是否发送 `tool_choice`。

模型列表在 `tradingagents/llm_clients/model_catalog.py`，同时供 CLI 选择和模型校验使用。

## 3. 配置模型

默认配置在 `tradingagents/default_config.py`。

重要配置：

- `llm_provider`
- `deep_think_llm`
- `quick_think_llm`
- `backend_url`
- `output_language`
- `max_debate_rounds`
- `max_risk_discuss_rounds`
- `max_recur_limit`
- `analyst_concurrency_limit`
- `checkpoint_enabled`
- `results_dir`
- `data_cache_dir`
- `memory_log_path`
- `data_vendors`
- `tool_vendors`
- `benchmark_ticker`
- `benchmark_map`

`TRADINGAGENTS_*` 环境变量会在 import `DEFAULT_CONFIG` 时覆盖默认值，并按默认值类型做简单 coercion。当前本机环境中实际读到的默认 provider 是：

```text
llm_provider = minimax-cn
deep_think_llm = MiniMax-M2.7
quick_think_llm = MiniMax-M2.7-highspeed
```

因此排查运行行为时，不应只看源码里的字面默认值。

## 4. 运行入口

### 4.1 交互式 CLI

入口：

```bash
tradingagents
python -m cli.main
```

实现文件：`cli/main.py`

CLI 会交互选择：

- ticker
- 分析日期
- 输出语言
- 分析师团队
- 研究深度
- LLM provider
- quick/deep 模型
- provider-specific thinking 参数

CLI 使用 `debug=True` 流式执行 graph，并用 Rich 实时展示 agent 状态、tool 调用和报告片段。

注意：CLI 当前是直接 stream `graph.graph`，而不是直接调用 `TradingAgentsGraph.propagate()`。因此 CLI 的报告保存、状态合并、进度展示逻辑主要在 `cli/main.py` 内部完成。

### 4.2 Python API

入口示例：`main.py`

```python
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

config = DEFAULT_CONFIG.copy()
ta = TradingAgentsGraph(debug=True, config=config)
state, decision = ta.propagate("NVDA", "2024-05-10")
print(decision)
```

Python API 走 `propagate()`，会自动：

- 解析 pending memory log。
- 写 full-state JSON。
- 存储本次决策。
- 成功后清理 checkpoint。
- 返回完整 state 和最终评级。

### 4.3 自动交易机器人

入口：

```bash
python run_bot.py --ticker AAPL --once
python run_bot.py --once
python run_bot.py
```

核心链路在 `tradingbot/scheduler/runner.py`：

```text
TradingAgentsGraph.propagate()
  -> SignalMapper.map()
  -> RiskGate.validate()
  -> BrokerAdapter.submit_order()
  -> PortfolioManager.record_trade()
  -> PortfolioDatabase
```

相关模块：

- `tradingbot/broker/base.py`：Broker 抽象和共享数据模型。
- `tradingbot/broker/mock.py`：本地模拟 broker，使用 yfinance 获取价格，立即成交。
- `tradingbot/broker/alpaca.py`：Alpaca broker。
- `tradingbot/broker/signal_mapper.py`：5 档评级转订单意图。
- `tradingbot/risk/gate.py`：程序化硬风控。
- `tradingbot/portfolio/database.py`：SQLite 持仓、交易、快照、已平仓记录。
- `tradingbot/portfolio/manager.py`：组合记录与绩效计算。
- `tradingbot/scheduler/scheduler.py`：定时任务。

Signal 到订单的映射：

- `Buy`：用 `full_position_pct` 买入。
- `Overweight`：用 `partial_position_pct` 买入。
- `Hold`：不交易。
- `Underweight`：卖出 `partial_exit_pct` 仓位。
- `Sell`：全部卖出。

RiskGate 是硬约束，LLM 不能绕过。主要规则：

- 市场是否开放。
- 日内亏损熔断。
- 最低现金保留。
- 总仓位敞口上限。
- 单票仓位上限。
- 买入重复加仓保护。
- 卖出不能超过实际持仓。

### 4.4 Streamlit Dashboard

入口：

```bash
python run_dashboard.py
streamlit run tradingbot/dashboard/app.py
```

当前 dashboard 使用 `st.navigation` 路由：

- `/login`：登录/注册页。
- `/`：主 dashboard。

主页面包括：

- Portfolio
- Performance
- Trade History
- Agent Reasoning
- Risk Monitor

Dashboard 共享 `tradingbot.db`，读取机器人写入的交易、持仓和快照。

### 4.5 Auth 页面

入口：

```bash
python run_auth.py
streamlit run tradingbot/dashboard/auth_app.py
```

认证相关文件：

- `tradingbot/auth/database.py`：`users.db` SQLite 用户表。
- `tradingbot/auth/service.py`：注册、密码登录、短信验证码登录。
- `tradingbot/auth/session.py`：HMAC token、cookie session、刷新恢复。
- `tradingbot/dashboard/auth_app.py`：Streamlit 登录/注册 UI。

密码使用 stdlib `hashlib.scrypt` 加盐哈希。短信验证码目前是开发 stub：验证码打印到终端，并在页面上显示。生产部署前需要接入真实 SMS provider。

## 5. 持久化与文件位置

默认用户目录：

```text
~/.tradingagents/
```

常见文件：

- `~/.tradingagents/logs/`：TradingAgents full-state logs。
- `~/.tradingagents/cache/`：数据缓存和 checkpoint。
- `~/.tradingagents/memory/trading_memory.md`：决策记忆日志。
- `~/.tradingagents/tradingbot.db`：自动交易组合数据库。
- `~/.tradingagents/users.db`：Dashboard 用户数据库。
- `~/.tradingagents/session_secret`：Dashboard cookie session HMAC secret。

CLI 另可保存报告到仓库下 `reports/<TICKER>_<timestamp>/`。

## 6. Memory 与 Reflection

v0.2.4 之后，旧的 per-agent BM25 memory 被 persistent decision log 取代。

运行结束时，`TradingMemoryLog.store_decision()` 追加 pending 决策。下一次运行同 ticker 时：

1. 查找该 ticker 的 pending entry。
2. 用 yfinance 拉取交易后若干日收益。
3. 计算 raw return 和 alpha return。
4. 生成一段 reflection。
5. 更新 markdown log。
6. 把同 ticker 历史和 cross-ticker lesson 注入 Portfolio Manager prompt。

这个机制在 `TradingAgentsGraph.propagate()` 内自动发生。

## 7. Checkpoint Resume

checkpoint 是 opt-in：

```bash
tradingagents analyze --checkpoint
```

核心实现：

- `tradingagents/graph/checkpointer.py`
- `langgraph-checkpoint-sqlite`
- per ticker/date thread id

成功完成后会清理对应 checkpoint，避免下次误恢复旧 state。

## 8. 测试与验证

测试目录：`tests/`

覆盖主题：

- API key env 映射。
- provider capability。
- DeepSeek reasoning roundtrip。
- MiniMax reasoning split。
- Google key。
- Ollama base URL。
- env overrides。
- dataflows config merge。
- checkpoint resume。
- memory log。
- signal processing。
- ticker path safety。
- analyst execution plan。
- crypto asset mode。
- structured agents。

当前本地验证结果：

- `python -m compileall -q tradingagents cli tests`：通过。
- `python -m compileall -q tradingbot`：通过。
- `python -m pytest -q`：未运行成功，本地环境缺少 `pytest` 模块。
- `uv run pytest -q`：未运行成功，环境中没有可 spawn 的 `pytest` 可执行文件。

注意：当前 `pyproject.toml` 没有声明测试依赖，因此新环境中不会自动安装 pytest。

## 9. 当前分支的工程注意点

### 9.1 `tradingbot` 可能未被打包

当前 `pyproject.toml` 的 setuptools package include 是：

```toml
[tool.setuptools.packages.find]
include = ["tradingagents*", "cli*"]
```

这没有包含 `tradingbot*`。如果用户通过 `pip install .` 安装后运行 `run_bot.py` 或 dashboard，可能无法 import `tradingbot`。

建议改为：

```toml
include = ["tradingagents*", "tradingbot*", "cli*"]
```

### 9.2 `AutoTrader` 仍调用旧 reflection 接口

`tradingbot/scheduler/runner.py` 中 SELL 后调用：

```python
self._graph.reflect_and_remember(realized_pnl)
```

但当前 `TradingAgentsGraph` 主线已改为 persistent decision log，没有看到该旧接口实现。现在这段被 `try/except` 捕获，只会 warning，不会中断交易，但 reflection 语义需要重新对齐。

建议后续移除该调用，或改成显式写入当前 memory log 机制。

### 9.3 CLI 与 API 的 side effect 不一致

`TradingAgentsGraph.propagate()` 会处理 memory log 和 checkpoint lifecycle。CLI 当前直接 stream `graph.graph`，因此如果后续依赖 `propagate()` 的 side effect，需要确认 CLI 是否也要补齐。

### 9.4 Auth SMS 是开发 stub

`AuthService.send_sms_code()` 只打印验证码。生产前必须接入真实短信通道，并避免在 UI 中显示验证码。

### 9.5 Dashboard cookie 依赖 JS 注入

`tradingbot/auth/session.py` 通过 `components.html()` 写 cookie。`st.rerun()` 或 `st.switch_page()` 可能丢弃待输出 iframe，因此当前实现把 cookie 写入安排在能正常完成 render 的页面上。修改 auth flow 时要保留这个约束。

## 10. 推荐后续工作

优先级建议：

1. 修复 packaging：把 `tradingbot*` 纳入 setuptools include。
2. 增加测试依赖声明，例如 `pytest`，并建立可重复的测试命令。
3. 为 `tradingbot` 补单元测试：
   - `SignalMapper`
   - `RiskGate`
   - `MockBroker`
   - `PortfolioDatabase`
   - `AuthService`
   - `session.verify_token`
4. 对齐 `AutoTrader` 的 reflection 逻辑与 persistent memory log。
5. 给 Dashboard/auth 增加最小 smoke test 或 import test。
6. 如果要生产化服务接入，优先参考 `docs/integration-api-rpc.md`，做异步 API + worker，而不是同步 HTTP 等完整分析结束。

