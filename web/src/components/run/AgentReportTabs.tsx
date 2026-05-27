import { useState } from 'react';
import clsx from 'clsx';
import Markdown from './Markdown';
import { t } from '@/i18n';

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
      label: t('report.pm'),
      desc: t('report.pm.desc'),
      source: s(reports, 'final_trade_decision'),
    },
    {
      key: 'market',
      label: t('report.market'),
      desc: t('report.market.desc'),
      source: s(reports, 'market_report'),
    },
    {
      key: 'news',
      label: t('report.news'),
      desc: t('report.news.desc'),
      source: s(reports, 'news_report'),
    },
    {
      key: 'sentiment',
      label: t('report.sentiment'),
      desc: t('report.sentiment.desc'),
      source: s(reports, 'sentiment_report'),
    },
    {
      key: 'fundamentals',
      label: t('report.fundamentals'),
      desc: t('report.fundamentals.desc'),
      source: s(reports, 'fundamentals_report'),
    },
    {
      key: 'research_mgr',
      label: t('report.research_mgr'),
      desc: t('report.research_mgr.desc'),
      source: s(reports, 'investment_plan'),
    },
    {
      key: 'trader',
      label: t('report.trader'),
      desc: t('report.trader.desc'),
      source: s(reports, 'trader_investment_plan'),
    },
  ].filter((t) => t.source && t.source.trim().length > 0);

  const [active, setActive] = useState(tabs[0]?.key ?? '');
  const cur = tabs.find((t) => t.key === active) ?? tabs[0];

  if (tabs.length === 0) {
    return <div className="card text-muted text-sm italic">{t('report.empty')}</div>;
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
