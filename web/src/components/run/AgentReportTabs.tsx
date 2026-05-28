import { useState } from 'react';
import clsx from 'clsx';
import Markdown from './Markdown';
import { t, getLang } from '@/i18n';

type Tab = {
  key: string;
  label: string;
  desc: string;
  field: string;
};

export type ReportMap = Record<string, unknown>;

function s(reports: ReportMap, key: string): string {
  const v = reports[key];
  return typeof v === 'string' ? v : '';
}

const TAB_DEFS: { key: string; labelKey: string; descKey: string; field: string }[] = [
  { key: 'pm', labelKey: 'report.pm', descKey: 'report.pm.desc', field: 'final_trade_decision' },
  { key: 'market', labelKey: 'report.market', descKey: 'report.market.desc', field: 'market_report' },
  { key: 'news', labelKey: 'report.news', descKey: 'report.news.desc', field: 'news_report' },
  { key: 'sentiment', labelKey: 'report.sentiment', descKey: 'report.sentiment.desc', field: 'sentiment_report' },
  { key: 'fundamentals', labelKey: 'report.fundamentals', descKey: 'report.fundamentals.desc', field: 'fundamentals_report' },
  { key: 'research_mgr', labelKey: 'report.research_mgr', descKey: 'report.research_mgr.desc', field: 'investment_plan' },
  { key: 'trader', labelKey: 'report.trader', descKey: 'report.trader.desc', field: 'trader_investment_plan' },
];

export default function AgentReportTabs({
  reports,
  reportsI18n,
}: {
  reports: ReportMap;
  reportsI18n?: Record<string, ReportMap> | null;
}) {
  const lang = getLang();
  const translated = reportsI18n?.[lang];

  // Tabs exist based on the English source of truth, so the tab set stays
  // stable while translations stream in (no tabs popping in/out).
  const tabs: Tab[] = TAB_DEFS
    .filter((d) => s(reports, d.field).trim().length > 0)
    .map((d) => ({ key: d.key, label: t(d.labelKey), desc: t(d.descKey), field: d.field }));

  const [active, setActive] = useState(tabs[0]?.key ?? '');
  const cur = tabs.find((t) => t.key === active) ?? tabs[0];

  if (tabs.length === 0) {
    return <div className="card text-muted text-sm italic">{t('report.empty')}</div>;
  }

  // For non-English, show the translation; if a section isn't translated yet,
  // show a "translating" placeholder rather than flashing the English text.
  let body: React.ReactNode;
  if (cur) {
    if (lang === 'en') {
      body = <Markdown source={s(reports, cur.field)} />;
    } else {
      const tv = translated?.[cur.field];
      body = typeof tv === 'string' && tv.trim()
        ? <Markdown source={tv} />
        : <div className="text-sm text-muted italic">{t('report.translating')}</div>;
    }
  }

  return (
    <div>
      <div className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            className={clsx(active === tab.key && 'active')}
            onClick={() => setActive(tab.key)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {cur && (
        <div className="card">
          <h3 className="text-base font-semibold">{cur.label.replace(/^[^\s]+\s/, '')}</h3>
          <div className="text-xs text-muted mb-3">{cur.desc}</div>
          <div className="st-divider !my-3" />
          {body}
        </div>
      )}
    </div>
  );
}
