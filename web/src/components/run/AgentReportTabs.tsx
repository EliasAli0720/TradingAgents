import { useState } from 'react';
import clsx from 'clsx';
import Markdown from './Markdown';

type Tab = {
  key: string;
  label: string;
  desc: string;
  source?: string;
};

export type ReportMap = Record<string, unknown>;

function s(reports: ReportMap, key: string): string {
  const v = reports[key];
  return typeof v === 'string' ? v : '';
}

export default function AgentReportTabs({ reports }: { reports: ReportMap }) {
  const tabs: Tab[] = [
    {
      key: 'pm',
      label: '🎯 组合经理',
      desc: '最终决策者。综合所有智能体的输入与风险辩论，给出最终的交易评级。',
      source: s(reports, 'final_trade_decision'),
    },
    {
      key: 'market',
      label: '📊 行情',
      desc: '技术指标分析（MACD、RSI、布林带、均线、ATR、VWMA）。',
      source: s(reports, 'market_report'),
    },
    {
      key: 'news',
      label: '📰 新闻',
      desc: '全球新闻、财报与宏观经济事件。',
      source: s(reports, 'news_report'),
    },
    {
      key: 'sentiment',
      label: '💬 情绪',
      desc: '社交媒体与公众情绪分析。',
      source: s(reports, 'sentiment_report'),
    },
    {
      key: 'fundamentals',
      label: '📈 基本面',
      desc: '财务报表与关键比率分析。',
      source: s(reports, 'fundamentals_report'),
    },
    {
      key: 'research_mgr',
      label: '⚖️ 研究经理',
      desc: '裁决多空辩论，综合分析师团队报告产出投资计划。',
      source: s(reports, 'investment_plan'),
    },
    {
      key: 'trader',
      label: '💼 交易员',
      desc: '将投资计划转化为具体的 买入/持有/卖出 方案。',
      source: s(reports, 'trader_investment_plan'),
    },
  ].filter((t) => t.source && t.source.trim().length > 0);

  const [active, setActive] = useState(tabs[0]?.key ?? '');
  const cur = tabs.find((t) => t.key === active) ?? tabs[0];

  if (tabs.length === 0) {
    return <div className="card text-muted text-sm italic">未返回任何报告。</div>;
  }

  return (
    <div>
      <div className="tabs">
        {tabs.map((t) => (
          <button
            key={t.key}
            className={clsx(active === t.key && 'active')}
            onClick={() => setActive(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {cur && (
        <div className="card">
          <h3 className="text-base font-semibold">{cur.label.replace(/^[^\s]+\s/, '')}</h3>
          <div className="text-xs text-muted mb-3">{cur.desc}</div>
          <div className="st-divider !my-3" />
          <Markdown source={cur.source!} />
        </div>
      )}
    </div>
  );
}
