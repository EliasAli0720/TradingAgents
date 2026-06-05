from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "TradingAgents_Web_Platform_Proposal.md"
OUT_EN = ROOT / "TradingAgents_Web_Platform_Proposal_EN.docx"
OUT_ZH = ROOT / "TradingAgents_Web_Platform_Proposal_ZH.docx"

BLUE = RGBColor(46, 116, 181)
DARK_BLUE = RGBColor(31, 77, 120)
INK = RGBColor(11, 37, 69)
GRAY = RGBColor(89, 89, 89)
LIGHT_FILL = "F4F6F9"
HEADER_FILL = "E8EEF5"
BORDER = "B7C9DC"

SECTION_TITLES_EN = [
    "Executive Summary / Project Overview",
    "Project Objectives",
    "Scope of Work",
    "Technical Approach / Solution Architecture",
    "Technology Stack",
    "Non-Functional Requirements (NFRs)",
    "Team Composition & Roles",
    "Project Timeline / Milestones",
    "Deliverables",
    "Assumptions & Dependencies",
    "Risk Analysis & Mitigation Plan",
    "Change Management Process",
    "Communication & Reporting Plan",
    "Testing & Quality Assurance",
    "Deployment & Release Strategy",
    "Maintenance & Support Plan",
    "Cost Estimate / Pricing",
    "Appendices",
]

SECTION_TITLES_ZH = [
    "执行摘要 / 项目概览",
    "项目目标",
    "工作范围",
    "技术方案 / 解决方案架构",
    "技术栈",
    "非功能性需求（NFR）",
    "团队组成与职责",
    "项目时间表 / 里程碑",
    "交付物",
    "假设与依赖",
    "风险分析与缓解计划",
    "变更管理流程",
    "沟通与汇报计划",
    "测试与质量保证",
    "部署与发布策略",
    "维护与支持计划",
    "成本估算 / 报价",
    "附录",
]


ZH_MARKDOWN = r"""
## 1. 执行摘要 / 项目概览

TradingAgents 正在从一个多智能体交易研究框架，演进为面向客户的 Web 平台。本提案说明如何将现有 tradingagents/ 研究框架与 tradingbot/ 执行、认证和券商工具整合为统一产品平台。

平台将支持最终用户：
- 部署并分析多智能体交易策略
- 审查智能体推理与决策过程
- 手动执行交易，或授权券商自动化交易
- 使用基于令牌的认证与分析能力

本次为期 3 周的项目聚焦 MVP 发布所需的核心客户产品能力。

## 2. 项目目标

**主要目标：**
- 交付一个可供客户使用的 Web 平台，连接研究能力与真实交易执行
- 让用户通过直观界面与交易智能体交互
- 通过智能体推理透明化提升信任度与可审计性
- 支持人工监督与自动化交易两类流程

**成功指标（待定，需根据客户优先级确认）：**
- 平台可用性：[待定]
- 用户从注册到首次交易所需时间：[待定]
- 智能体推理透明度：[待定，需定义成功标准]
- 交易执行可靠性：[待定，目标 SLA]

## 3. 工作范围

### A. 功能范围

**用户模块与功能：**

1. **认证与授权**
   - 基于令牌的用户认证（OAuth2 / JWT）
   - 基于角色的访问控制（用户、管理员）
   - 安全存储券商 API 密钥

2. **智能体管理与部署**
   - 用于列出、部署和监控交易智能体的仪表盘
   - 智能体参数配置界面
   - 实时智能体状态与绩效指标

3. **智能体推理与透明化**
   - 展示带有推理链的智能体决策日志
   - 可视化输入数据、模型预测和执行决策
   - 用于合规与学习的历史审计轨迹

4. **交易执行界面**
   - 带执行前预览的手动下单
   - 对智能体推荐交易进行一键批准或拒绝
   - 自动执行设置与风险限制

5. **绩效与分析仪表盘**
   - 投资组合概览与盈亏跟踪
   - 智能体绩效指标（胜率、夏普比率、回撤等）
   - 交易历史与执行日志

6. **券商集成**
   - 抽象化券商 API 层（认证、订单提交、执行）
   - 支持 [待定，需确认具体券商]
   - 实时市场数据流（如适用）

7. **管理后台**
   - 用户管理与账户设置
   - 系统健康与错误监控
   - 审计日志

### B. 当前阶段不包含

- 移动应用（本阶段仅 Web）
- 高级回测或策略优化工具
- 多账户或基金管理能力
- 平台内的机器学习模型训练或优化
- 监管合规报表（例如 Form 4、内幕交易披露等）
- 超出基础图表能力的第三方图表或分析库集成
- 自定义 API 市场或合作伙伴集成

## 4. 技术方案 / 解决方案架构

### 高层架构

```text
客户 Web 平台
├─ 前端层（Web UI）
│  ├─ React/Next.js 单页应用
│  ├─ WebSocket 实时更新
│  └─ 智能体仪表盘、交易界面、分析视图
├─ API 层（RESTful / GraphQL）
│  ├─ 认证与令牌管理
│  ├─ 智能体生命周期管理
│  ├─ 交易执行与订单管理
│  └─ 用户偏好与设置
├─ 业务逻辑与集成
│  ├─ TradingAgents 研究与分析框架
│  ├─ TradingBot 执行层（券商认证、订单路由）
│  ├─ 智能体推理透明化层
│  └─ 基于令牌的分析与指标
├─ 数据层
│  ├─ 用户与认证数据
│  ├─ 智能体配置与执行日志
│  └─ 交易历史与绩效指标
└─ 外部集成
   ├─ 券商 API（执行、账户数据、市场数据）
   └─ 市场数据提供商（如适用）
```

### 数据流

1. 用户通过基于令牌的认证登录，并获得 JWT
2. 用户在仪表盘中配置或选择智能体
3. 智能体处理市场数据并生成交易信号
4. 智能体推理被记录并展示在界面中
5. 用户审查智能体建议，并批准或拒绝
6. 交易执行通过 TradingBot 执行层路由
7. 券商 API 执行订单；确认结果被记录并展示
8. 投资组合与智能体绩效在实时仪表盘中更新

## 5. 技术栈

| 层级 | 技术建议 | 说明 |
| --- | --- | --- |
| 前端 | React 18 + Next.js | SSR 提升性能，内置路由 |
| 样式 | Tailwind CSS | 快速 UI 开发 |
| 状态管理 | Zustand / Redux | 客户端 UI 状态 |
| 实时能力 | WebSocket / Socket.io | 智能体更新与交易执行实时反馈 |
| 后端 | Node.js + Express / NestJS | 待定，需与 TradingAgents/TradingBot 兼容 |
| API 风格 | RESTful（高级查询可增加 GraphQL） | 待定 |
| 数据库 | PostgreSQL | 用户、交易、智能体、审计日志等关系型数据 |
| 缓存 | Redis | 会话管理与实时数据 |
| 托管 | AWS（EC2、RDS、ALB） | 待定，最终基础设施由客户确认 |
| 认证 | JWT + OAuth2 | 基于令牌，并支持券商 API 集成 |
| 日志 | ELK Stack / CloudWatch | 审计、错误和性能日志 |
| 监控 | DataDog / New Relic | 待定，APM 与告警 |

**待定决策：**
- 最终支持的券商 API（Interactive Brokers、Alpaca 等）
- 市场数据提供商（Alpha Vantage、IEX Cloud 等）
- 高级图表库（TradingView、Lightweight Charts 等）
- 部署区域与多区域策略

## 6. 非功能性需求（NFR）

| 需求 | 目标 | 说明 |
| --- | --- | --- |
| **性能** | | |
| API 响应时间 | < 200ms（p95） | 仪表盘查询 |
| 交易执行延迟 | < 1s（下单到确认） | 对实盘交易关键 |
| 页面加载时间 | < 3s（完全可交互） | Lighthouse 评分：80+ |
| **可扩展性** | | |
| 并发用户 | [待定] | 初始目标与增长预估 |
| 交易吞吐量 | [待定] 笔/分钟 | 峰值容量 |
| 智能体实例 | [待定] 并发智能体 | 单用户与平台总体 |
| **安全性** | | |
| 认证 | OAuth2 + JWT | 令牌过期时间：[待定] 分钟 |
| 数据加密 | 传输中 TLS 1.3；静态 AES-256 | 券商凭证与 PII |
| API 限流 | [待定] 次/分钟/用户 | 防 DDoS 与暴力破解 |
| 审计日志 | 100% 用户操作与交易 | 用于合规的不可变日志 |
| 密码策略 | [待定，复杂度与轮换] | 若采用纯 SSO 可调整 |
| **可用性 / 正常运行时间** | | |
| 平台 SLA | [待定，99.5% / 99.9%] | 业务连续性预期 |
| 优雅降级 | 券商 API 故障时仍可查看智能体建议 | 支持手动兜底 |
| 灾难恢复 RTO | [待定] 小时 | 数据备份与恢复策略 |
| **合规** | | |
| 数据保留 | [待定，交易与审计日志] | 监管要求 |
| GDPR / CCPA | 合规评估：[待定] | 删除权、数据可携带性 |
| 金融监管 | [待定，平台是否需要合规评估] | 取决于客户司法辖区 |

## 7. 团队组成与职责

| 角色 | 职责 | 投入 | 周期 |
| --- | --- | --- | --- |
| 项目负责人 | 总体管理、客户沟通、范围管理 | 全职 | 3 周 |
| 全栈工程师（2 名） | 前端、后端 API、系统集成 | 各全职 | 3 周 |
| 后端 / 集成工程师 | TradingAgents/TradingBot 集成、券商 API、数据层 | 全职 | 3 周 |
| 前端 / UI 工程师 | 仪表盘、智能体推理可视化、UX 打磨 | 全职 | 3 周 |
| QA / 测试 | 单元、集成、UAT、性能测试 | 全职 | 最后 1.5 周 |
| DevOps / 基础设施 | CI/CD、托管、安全加固、监控 | 兼职 | 按需 |

**总资源投入：** 约 3.5 FTE，持续 3 周。

## 8. 项目时间表 / 里程碑

| 阶段 | 周期 | 交付物 |
| --- | --- | --- |
| 第 1 周：核心基础设施与 API | 5 天 | 后端脚手架、认证系统、智能体 API、数据库 schema、CI/CD、券商 API 集成骨架 |
| 第 2 周：前端与集成 | 5 天 | React 仪表盘、智能体管理界面、交易执行 UI、WebSocket 实时更新、TradingAgents/TradingBot 集成、推理日志展示 |
| 第 3 周：打磨、测试与上线 | 5 天 | 端到端测试、性能优化、安全加固、缺陷修复、部署到 staging、客户 UAT、上线 |

**关键里程碑：**
- **第 3 天：** 后端 API 合约冻结，前端脚手架完成
- **第 7 天：** 核心智能体管理与认证可用，券商 API 已连接
- **第 10 天：** MVP 仪表盘可用，交易可端到端执行
- **第 12 天：** QA 签核，性能基准达标
- **第 15 天：** 生产部署与客户切换

## 9. 交付物

**代码与文档：**
1. 完整源代码仓库（GitHub/GitLab）
   - 前端（React/Next.js）
   - 后端 API（Node.js/NestJS）
   - TradingAgents 与 TradingBot 集成层
   - 基础设施即代码（Terraform / CloudFormation）

2. 技术文档
   - API 规格（OpenAPI/Swagger）
   - 架构与设计决策
   - 部署运行手册
   - 故障排查指南

3. 用户文档
   - 入门指南
   - 智能体配置手册
   - 交易界面操作说明
   - FAQ 与支持联系方式

**已部署应用：**
4. Staging 环境（可供客户 UAT 访问）
5. 生产环境（在上线日期完全可用）

**上线后支持：**
6. 针对关键缺陷的 1 周免费初始支持窗口
7. 与客户团队进行 1-2 小时知识转移会议

## 10. 假设与依赖

**客户职责：**
- 提供券商 API 凭证与文档访问
- 确认本阶段支持的券商列表
- 提供现有 TradingAgents 框架代码或模型权重（如有）
- 确认实时市场数据来源
- 指定用于签核与决策的主要联系人

**外部依赖：**
- 券商 API 可用性与限流
- 市场数据提供商（如需要实时数据）
- TradingAgents/TradingBot 所需第三方库或 SDK
- DNS、SSL 证书与托管基础设施准备情况

**技术假设：**
- TradingAgents 与 TradingBot 框架成熟稳定
- 券商 API 支持标准认证（OAuth2 或 API key）
- 项目中途现有框架不会发生重大 schema 或破坏性变更
- 初始用户规模小于 1,000 并发用户（上线后可扩展）

**项目假设：**
- 3 周周期基于范围清晰且返工较少
- 6,400 美元预算覆盖开发人力与基础设施；上线后托管成本由客户承担
- 客户将在最后一周执行 UAT；生产部署前需要签核
- 上线后维护与新增功能不包含在本提案范围内

## 11. 风险分析与缓解计划

| 风险 | 影响 | 可能性 | 缓解措施 |
| --- | --- | --- | --- |
| 券商 API 集成延迟 | 时间线延误，交易执行受阻 | 中 | 第 1 周开始券商 API 集成；必要时保留手动 API 调用兜底；尽早准备测试账户 |
| 智能体推理需求不清晰 | 功能返工、范围蔓延、交付延迟 | 中 | 启动会明确推理透明化要求（可视化、格式、数据深度），并形成书面确认 |
| TradingAgents/TradingBot 框架问题 | 集成阻塞，需要返工 | 低-中 | 项目前审计框架；与维护方保持沟通；保留手动执行兜底路径 |
| 范围蔓延 | 预算超支，时间线延误 | 高 | 严格变更控制；书面记录范围外事项；每周进行范围审查 |
| 负载下性能不足 | 用户体验下降，声誉风险 | 中 | 第 2 周进行负载测试；使用 WebSocket 降低轮询；Redis 缓存智能体数据；优化 API 查询 |
| 安全漏洞 | 数据泄露、凭证暴露、合规风险 | 中-高 | OWASP Top 10 审查；代码安全扫描（SonarQube、Snyk）；上线前第三方安全审计；密钥管理最佳实践 |
| UAT 窗口不足 | 缺陷进入生产，客户不满意 | 中 | 第 3 周预留 3-4 天 UAT；尽早提供沙箱环境；优先测试关键路径 |

## 12. 变更管理流程

**变更请求流程：**
1. 客户以书面形式提交变更请求，包含描述、业务理由与影响预估
2. 项目负责人评估其对时间线、预算与范围的影响
3. 在 24 小时内向客户提交影响评估
4. 如获批准：更新范围、调整时间线，并协商费用影响（如有）
5. 未获得书面批准前，不执行任何变更

**变更审批权限：**
- 不超过 4 小时的变更：项目负责人可批准
- 4-16 小时的变更：需 FineCore CTO 批准
- 超过 16 小时或影响时间线的变更：需客户与 FineCore 共同签核

**范围外功能请求：**
- 原范围未包含的功能将加入上线后路线图
- 客户可在第 2 阶段优先安排（需另行提案）

## 13. 沟通与汇报计划

**会议：**
- **每日站会：** 15 分钟，上午 9 点（如时区不便，可使用 Slack 异步更新）
- **每周同步：** 每周四 30 分钟，汇报进展、阻塞与下周计划
- **Sprint 复盘：** 第 2 周与第 3 周周五各 30 分钟

**汇报：**
- **周报：** 通过邮件总结已完成工作、后续任务、风险与指标
- **燃尽图：** 在共享看板（GitHub Projects / Jira）每日更新
- **阻塞与问题：** 如影响团队推进，立即升级

**工具：**
- **代码：** GitHub / GitLab（启用分支保护与 PR 审查）
- **项目跟踪：** Jira / Linear / GitHub Projects
- **聊天：** Slack #tradingagents-platform 频道
- **视频会议：** Google Meet / Zoom
- **文档：** 共享 Notion / Confluence 或 GitHub Wiki

## 14. 测试与质量保证

**测试策略：**

| 测试类型 | 范围 | 时间 | 负责人 |
| --- | --- | --- | --- |
| 单元测试 | 核心业务逻辑、工具函数 | 持续进行（第 1-2 周） | 工程师 |
| 集成测试 | API 与数据库、TradingAgents 集成、券商 API mock | 第 2 周 | 后端团队 |
| API 合约测试 | 前后端契约验证 | 第 2 周 | 全栈团队 |
| 端到端（E2E） | 用户流程：登录、智能体配置、交易执行 | 第 3 周 | QA + 工程师 |
| 负载与性能 | 100+ 并发用户、交易吞吐量 | 第 2-3 周 | QA + DevOps |
| 安全测试 | SQL 注入、XSS、CSRF、凭证暴露、OWASP Top 10 | 第 3 周 | 安全审查 + QA |
| UAT | 客户按需求验证 | 第 3 周（周四至周五） | 客户 + QA |

**用户故事验收标准：**
- 所有单元测试通过（目标代码覆盖率 > 80%）
- API 响应时间达到 NFR 目标
- 无关键/高危安全发现
- 所有 UAT 签核任务完成

**工具：**
- Jest / Mocha（单元测试）
- Cypress / Playwright（E2E 测试）
- k6 / JMeter（负载测试）
- OWASP ZAP / Burp Suite（安全扫描）
- GitHub Actions / CircleCI（CI/CD 自动化测试）

## 15. 部署与发布策略

**环境：**
1. **本地开发** - 每位工程师的本机环境
2. **Staging** - 预生产复制环境，可供客户 UAT 使用
3. **Production** - 面向真实客户的生产环境

**部署流水线：**
```text
Git Commit → CI/CD Tests → Build → Deploy to Staging →
Client UAT → Approval → Deploy to Production
```

**发布策略：**
- **初始发布：** 第 15 天完整切换到生产环境
- **监控：** 上线后前 24 小时使用实时仪表盘监控
- **快速修复协议：** 如出现关键缺陷，2 小时内部署热修复

**版本管理：**
- 语义化版本：生产上线为 v1.0.0
- 补丁版本（v1.0.1）用于缺陷修复
- 次版本（v1.1.0）用于上线后的新功能

**回滚策略：**
- 保留上一版本快照作为备用
- 每次生产部署前进行数据库备份
- 如检测到关键问题：30 分钟内回滚到上一版本
- 完成根因分析与修复后再重新部署

## 16. 维护与支持计划

**提案包含的上线后支持：**
- **周期：** 1 周（第 15-21 天，5 月 22-28 日）
- **范围：** 关键缺陷修复、部署故障排查
- **响应时间：** 关键问题（交易阻塞）2 小时，中等问题 8 小时
- **支持渠道：** Slack #support，升级至项目负责人

**持续维护（第 2 阶段，范围外）：**
- 安全补丁管理
- 依赖更新
- 数据库备份与监控
- 随用户增长进行基础设施扩容
- 小缺陷修复与功能请求

**未来建议支持等级：**
- **Tier 1（基础）：** 邮件支持，24 小时响应
- **Tier 2（专业）：** 优先支持，4 小时响应，季度健康检查
- **Tier 3（高级）：** 专属客户经理，1 小时响应，月度策略会议

## 17. 成本估算 / 报价

**预算分配：**

| 组成 | 费用 | 说明 |
| --- | --- | --- |
| 开发人力 | $5,000 | 约 3.5 FTE × 3 周，综合日费率 $450 |
| 基础设施与托管（3 周） | $600 | AWS EC2、RDS、ALB staging + production |
| 第三方工具与许可 | $400 | GitHub Actions、监控、安全扫描、Jira |
| 测试与 QA 工具 | $200 | 负载测试、安全扫描（如非免费层） |
| 预备金（5%） | $320 | 未知事项缓冲 |
| **总计** | **$6,400** | 3 周开发阶段固定费用 |

**付款安排：**
- 合同签署后预付 50%（$3,200）
- 生产部署与 UAT 签核后支付 50%（$3,200）

**包含内容：**
- 全栈开发与集成
- 测试与 QA（单元、集成、E2E、安全）
- 1 周上线后关键缺陷支持
- 技术文档与 API 规格
- 部署与基础设施搭建

**不包含内容：**
- 超出 1 周支持窗口的持续维护
- 额外功能开发或定制
- 合规认证（SOC 2、ISO 27001 等）
- 券商账户开设或资金准备
- 市场数据提供商订阅（客户负责）

**可选附加项（待定，需另行报价）：**
- 移动应用（iOS/Android）- 预计 +$12,000-15,000
- 高级回测与优化工具 - 预计 +$4,000-6,000
- 多券商或投资组合管理能力 - 预计 +$3,000-5,000
- 监管合规模块 - 预计 +$5,000-10,000

## 18. 附录

### A. 术语表

- **智能体：** 能够分析市场数据并生成交易建议的自主算法
- **推理日志：** 针对每笔交易记录数据输入、处理步骤和决策依据的时间戳记录
- **TradingAgents：** 用于开发、测试和分析交易策略的多智能体研究框架
- **TradingBot：** 通过券商 API 处理认证、订单路由和实盘交易执行的执行层
- **基于令牌的分析：** 针对智能体绩效、风险和合规性的量化指标与报告
- **券商 API：** 面向券商服务的 RESTful 接口，包括订单执行、账户数据与市场数据

### B. 智能体推理展示示例（概念）

```text
智能体："Momentum Scout"
时间戳：2026-05-22 14:35:00 UTC

输入数据：
- 最近 20 根 K 线（1 小时间隔）：[OHLCV data]
- RSI（14）：72.5（超买）
- MA20：$45,123.50，MA50：$44,987.25（多头交叉）
- 成交量：150M shares（高于 20 日均量）

决策逻辑：
1. RSI > 70？是 → 强动量信号
2. MA20 > MA50？是 → 上升趋势确认
3. 成交量高于均值？是 → 信号置信度高
4. 是否超过组合风险限制？否 → 可安全交易
5. 建议：以市价买入 0.5 BTC

置信度：82%
执行：用户于 2026-05-22 14:35:15 UTC 批准
订单：BTC-USD 市价单以 $45,150 成交（0.5 BTC）
状态：已执行
```

### C. 券商 API 集成清单

- [ ] 确认认证方式（OAuth2 / API Key / 两者）
- [ ] 开通用于测试的沙箱账户
- [ ] 审阅 API 文档并整理端点清单
- [ ] 记录限流与节流政策
- [ ] 设计错误处理与重试逻辑
- [ ] 确认支持的订单类型：市价、限价、止损、移动止损（需确认范围）
- [ ] 确认账户数据获取能力：持仓、余额、交易历史（需确认范围）
- [ ] 确认实时市场数据：价格、报价、深度（需确认范围）
- [ ] 确认订单成交 webhook / 通知机制（如可用）

### D. 项目前启动清单

第 1 周开始前：
- [ ] 收集客户访问凭证（券商沙箱、内部系统等）
- [ ] 团队可访问 TradingAgents/TradingBot 代码仓库
- [ ] 项目团队完成分配与入组
- [ ] 开发、staging 与生产环境完成开通
- [ ] CI/CD 流水线完成脚手架
- [ ] Slack、Jira 与文档空间已创建
- [ ] 首次站会已安排
- [ ] 变更管理与沟通期望已记录

### E. 成功标准（客户验收）

**功能：**
- 用户可认证并访问仪表盘
- 智能体管理（创建、部署、监控）完整可用
- 智能体推理以完整决策审计轨迹展示
- 手动下单与券商执行可用
- 投资组合与智能体绩效指标可见且准确
- 所有已确认券商 API 集成上线

**性能：**
- API 响应时间达到 NFR 目标（< 200ms p95）
- 页面加载时间 < 3 秒
- 交易执行在 1 秒内确认
- 最终安全审计中无关键安全发现

**质量：**
- 单元测试覆盖率 > 80%
- 所有 E2E 测试通过
- UAT 中无关键/高危缺陷
- 负载测试完成并达到并发用户目标

## 签核

**提案方：** FineCore LLC
**日期：** 2026 年 5 月 22 日
**有效期至：** 2026 年 5 月 29 日（7 天）

**若要继续推进，请确认：**
1. 项目范围与目标符合您的预期
2. 预算（$6,400）与周期（3 周）可接受
3. 客户团队可投入每周同步、UAT 与签核所需时间
4. 上述待定事项中是否有必须在启动前澄清的内容

**下一步：**
- 签署合同并返回 FineCore LLC
- 通过安全渠道提供券商 API 访问详情与凭证
- 安排第 1 周项目启动会
- 确认上述所有待定事项

**问题咨询：** 联系方式：[待定，项目负责人联系方式]

*本提案为保密文件，仅供指定客户使用。未经书面同意，不得复制或分发。*
"""


def set_font(
    run,
    font: str,
    size: float | None = None,
    color: RGBColor | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
):
    run.font.name = font
    run._element.rPr.rFonts.set(qn("w:ascii"), font)
    run._element.rPr.rFonts.set(qn("w:hAnsi"), font)
    run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = color
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_cell_shading(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=80, start=120, bottom=80, end=120):
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.find(qn("w:tcMar"))
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for side, value in (("top", top), ("start", start), ("bottom", bottom), ("end", end)):
        node = tc_mar.find(qn(f"w:{side}"))
        if node is None:
            node = OxmlElement(f"w:{side}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.allow_autofit = False
    tbl = table._tbl
    tbl_pr = tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(sum(widths)))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), "120")
    tbl_ind.set(qn("w:type"), "dxa")

    grid = tbl.tblGrid
    if grid is None:
        grid = OxmlElement("w:tblGrid")
        tbl.insert(0, grid)
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)

    for row in table.rows:
        for idx, width in enumerate(widths):
            if idx >= len(row.cells):
                break
            row.cells[idx].width = Pt(width / 20)
            tc_pr = row.cells[idx]._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(width))
            tc_w.set(qn("w:type"), "dxa")


def mark_first_row_as_header(table):
    if not table.rows:
        return
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = tr_pr.find(qn("w:tblHeader"))
    if tbl_header is None:
        tbl_header = OxmlElement("w:tblHeader")
        tr_pr.append(tbl_header)
    tbl_header.set(qn("w:val"), "true")


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = paragraph.add_run()
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    run._r.append(fld)


def setup_document(lang: str):
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    base_font = "Microsoft YaHei" if lang == "zh" else "Calibri"
    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = base_font
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), base_font)
    normal.font.size = Pt(11)
    normal.font.color.rgb = INK
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing = 1.333

    for name, size, color, before, after in [
        ("Title", 26, INK, 0, 8),
        ("Subtitle", 13, GRAY, 0, 12),
        ("Heading 1", 16, BLUE, 18, 10),
        ("Heading 2", 13, BLUE, 12, 6),
        ("Heading 3", 12, DARK_BLUE, 8, 4),
    ]:
        style = styles[name]
        style.font.name = base_font
        style._element.rPr.rFonts.set(qn("w:eastAsia"), base_font)
        style.font.size = Pt(size)
        style.font.color.rgb = color
        style.font.bold = name.startswith("Heading") or name == "Title"
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = name.startswith("Heading")

    for name in ("List Bullet", "List Number"):
        style = styles[name]
        style.font.name = base_font
        style._element.rPr.rFonts.set(qn("w:eastAsia"), base_font)
        style.font.size = Pt(11)
        style.paragraph_format.left_indent = Inches(0.375)
        style.paragraph_format.first_line_indent = Inches(-0.194)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.208

    return doc


def add_run_markdown(paragraph, text: str, base_font: str, size=11):
    text = text.replace("✅", "✓").replace("❌", "✗")
    parts = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text)
    for part in parts:
        if not part:
            continue
        bold = part.startswith("**") and part.endswith("**")
        italic = part.startswith("*") and part.endswith("*") and not bold
        content = part[2:-2] if bold else part[1:-1] if italic else part
        run = paragraph.add_run(content)
        set_font(run, base_font, size=size, color=INK, bold=bold, italic=italic)


def add_callout(doc, title: str, body: str, lang: str):
    table = doc.add_table(rows=1, cols=1)
    set_table_geometry(table, [9360])
    cell = table.cell(0, 0)
    set_cell_shading(cell, LIGHT_FILL)
    set_cell_margins(cell, top=140, bottom=140, start=180, end=180)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(3)
    base_font = "Microsoft YaHei" if lang == "zh" else "Calibri"
    r = p.add_run(title)
    set_font(r, base_font, 10.5, DARK_BLUE, True)
    p2 = cell.add_paragraph()
    p2.paragraph_format.space_after = Pt(0)
    add_run_markdown(p2, body, base_font, size=10.5)


def add_cover(doc, lang: str):
    base_font = "Microsoft YaHei" if lang == "zh" else "Calibri"
    if lang == "zh":
        label = "软件项目提案"
        title = "TradingAgents Web 平台"
        subtitle = "客户产品与智能体分析仪表盘"
        meta_left = [("客户", "Wang Qiang"), ("客户组织", "N/A（个人）"), ("提交方", "FineCore LLC (finecore.dev)")]
        meta_right = [("日期", "2026 年 5 月 22 日"), ("预算", "$6,400 USD"), ("周期", "3 周")]
        status = "提案状态：发现阶段完成，准备进入实施"
        disclaimer_title = "重要说明"
        disclaimer = "本提案仅描述软件交付范围、技术实施与项目管理安排，不构成金融、投资、法律、税务或监管建议。任何真实交易、券商接入和合规义务均需由客户与合格专业顾问另行确认。"
    else:
        label = "Software Project Proposal"
        title = "TradingAgents Web Platform"
        subtitle = "Customer-Facing Product & Agent Analysis Dashboard"
        meta_left = [("Client", "Wang Qiang"), ("Organization", "N/A (Individual)"), ("Submitted By", "FineCore LLC (finecore.dev)")]
        meta_right = [("Date", "May 22, 2026"), ("Budget", "$6,400 USD"), ("Timeline", "3 weeks")]
        status = "Proposal Status: Discovery Phase - Ready for Implementation"
        disclaimer_title = "Important Notice"
        disclaimer = "This proposal describes software delivery scope, technical implementation, and project management only. It is not financial, investment, legal, tax, or regulatory advice. Live trading, broker onboarding, and compliance obligations should be reviewed by the client and qualified advisors."

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(12)
    r = p.add_run(label.upper())
    set_font(r, base_font, 11, GRAY, True)

    p = doc.add_paragraph(style="Title")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(3)
    set_font(p.add_run(title), base_font, 26, INK, True)

    p = doc.add_paragraph(style="Subtitle")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    set_font(p.add_run(subtitle), base_font, 13, GRAY, False)

    table = doc.add_table(rows=3, cols=4)
    set_table_geometry(table, [1680, 3000, 1680, 3000])
    for row_idx, (left, right) in enumerate(zip(meta_left, meta_right)):
        row = table.rows[row_idx]
        values = [left[0], left[1], right[0], right[1]]
        for idx, value in enumerate(values):
            cell = row.cells[idx]
            set_cell_margins(cell, top=90, bottom=90, start=120, end=120)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            if idx in (0, 2):
                set_cell_shading(cell, HEADER_FILL)
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(value)
            set_font(run, base_font, 9.5 if idx in (0, 2) else 10, INK, idx in (0, 2))

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(12)
    set_font(p.add_run(status), base_font, 10.5, DARK_BLUE, True)

    doc.add_paragraph()
    add_callout(doc, disclaimer_title, disclaimer, lang)
    doc.add_page_break()


def add_contents(doc, titles, lang: str):
    heading = "Table of Contents" if lang == "en" else "目录"
    doc.add_heading(heading, level=1)
    base_font = "Microsoft YaHei" if lang == "zh" else "Calibri"
    for idx, title in enumerate(titles, start=1):
        p = doc.add_paragraph(style="List Number")
        add_run_markdown(p, f"{title}", base_font)
    doc.add_page_break()


def parse_table(lines, start):
    table_lines = []
    idx = start
    while idx < len(lines) and lines[idx].strip().startswith("|") and lines[idx].strip().endswith("|"):
        table_lines.append(lines[idx].strip())
        idx += 1
    rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{2,}:?", c.replace(" ", "")) for c in cells):
            continue
        if not any(cells):
            continue
        rows.append(cells)
    return rows, idx


def column_widths(rows):
    if not rows:
        return [9360]
    cols = max(len(r) for r in rows)
    if cols == 2:
        return [2700, 6660]
    if cols == 3:
        return [2100, 2500, 4760]
    if cols == 4:
        return [2200, 1800, 1800, 3560]
    return [9360 // cols] * cols


def add_table(doc, rows, lang):
    if not rows:
        return
    base_font = "Microsoft YaHei" if lang == "zh" else "Calibri"
    cols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=cols)
    table.style = "Table Grid"
    widths = column_widths(rows)
    set_table_geometry(table, widths)
    for r_idx, row in enumerate(rows):
        for c_idx in range(cols):
            cell = table.cell(r_idx, c_idx)
            set_cell_margins(cell)
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            if r_idx == 0:
                set_cell_shading(cell, HEADER_FILL)
            value = row[c_idx] if c_idx < len(row) else ""
            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx in (1, 2) and len(value) < 22 else WD_ALIGN_PARAGRAPH.LEFT
            add_run_markdown(p, value, base_font, size=9.2 if cols >= 4 else 9.5)
            for run in p.runs:
                if r_idx == 0:
                    run.bold = True
    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_after = Pt(4)


def add_code_block(doc, text: str, lang: str):
    table = doc.add_table(rows=1, cols=1)
    set_table_geometry(table, [9360])
    cell = table.cell(0, 0)
    set_cell_shading(cell, "F7F9FB")
    set_cell_margins(cell, top=130, bottom=130, start=160, end=160)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.05
    run = p.add_run(text.strip("\n"))
    set_font(run, "Courier New", 8.5 if lang == "en" else 8, INK, False)
    doc.add_paragraph()


def normalized_source_markdown():
    text = SOURCE.read_text(encoding="utf-8")
    start = text.index("## 1. Executive Summary")
    body = text[start:]
    body = re.sub(r"\n## Sign-Off", "\n## Sign-Off", body)
    return body


def render_markdown(doc, markdown: str, lang: str):
    lines = markdown.splitlines()
    base_font = "Microsoft YaHei" if lang == "zh" else "Calibri"
    i = 0
    in_code = False
    code = []
    while i < len(lines):
        raw = lines[i]
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code:
                add_code_block(doc, "\n".join(code), lang)
                code = []
                in_code = False
            else:
                in_code = True
            i += 1
            continue
        if in_code:
            code.append(raw)
            i += 1
            continue

        if not stripped or stripped == "---":
            i += 1
            continue

        if stripped.startswith("|") and stripped.endswith("|"):
            rows, i = parse_table(lines, i)
            add_table(doc, rows, lang)
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            level = min(len(heading.group(1)), 3)
            text = heading.group(2)
            p = doc.add_heading("", level=level)
            add_run_markdown(p, text, base_font, size={1: 16, 2: 13, 3: 12}[level])
            for run in p.runs:
                run.bold = True
                run.font.color.rgb = BLUE if level in (1, 2) else DARK_BLUE
            i += 1
            continue

        bullet = re.match(r"^\s*-\s+(.*)$", line)
        checkbox = re.match(r"^\s*-\s+\[([ xX])\]\s+(.*)$", line)
        number = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if checkbox:
            p = doc.add_paragraph(style="List Bullet")
            mark = "☐" if checkbox.group(1).strip() == "" else "☑"
            add_run_markdown(p, f"{mark} {checkbox.group(2)}", base_font)
        elif bullet:
            p = doc.add_paragraph(style="List Bullet")
            add_run_markdown(p, bullet.group(1), base_font)
        elif number:
            p = doc.add_paragraph(style="List Number")
            add_run_markdown(p, number.group(1), base_font)
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if lang == "zh" else WD_ALIGN_PARAGRAPH.JUSTIFY
            add_run_markdown(p, stripped, base_font)
        i += 1


def set_running_header_footer(doc, lang: str):
    header_text = "TradingAgents Web Platform Proposal" if lang == "en" else "TradingAgents Web 平台提案"
    footer_text = "Confidential" if lang == "en" else "保密"
    section = doc.sections[0]
    header = section.header.paragraphs[0]
    header.text = ""
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = header.add_run(header_text)
    set_font(run, "Microsoft YaHei" if lang == "zh" else "Calibri", 9, GRAY, True)
    footer = section.footer.paragraphs[0]
    footer.text = ""
    footer.alignment = WD_ALIGN_PARAGRAPH.LEFT
    run = footer.add_run(footer_text)
    set_font(run, "Microsoft YaHei" if lang == "zh" else "Calibri", 9, GRAY, False)
    footer.add_run("\t")
    add_page_number(footer)


def build(lang: str, output: Path):
    doc = setup_document(lang)
    set_running_header_footer(doc, lang)
    add_cover(doc, lang)
    add_contents(doc, SECTION_TITLES_ZH if lang == "zh" else SECTION_TITLES_EN, lang)
    render_markdown(doc, ZH_MARKDOWN if lang == "zh" else normalized_source_markdown(), lang)
    for table in doc.tables:
        mark_first_row_as_header(table)
    doc.save(output)


def main():
    build("en", OUT_EN)
    build("zh", OUT_ZH)
    print(OUT_EN)
    print(OUT_ZH)


if __name__ == "__main__":
    main()
