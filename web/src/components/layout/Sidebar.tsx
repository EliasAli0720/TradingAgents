import { NavLink } from 'react-router-dom';
import clsx from 'clsx';
import { useState } from 'react';
import { getLocale, t } from '@/i18n';

type Item = { to: string; label: string };

const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: 'group.analysis',
    items: [
      { to: '/analysis', label: 'nav.analysis' },
      { to: '/analysis/new', label: 'nav.analysis_new' },
    ],
  },
  {
    title: 'group.trading',
    items: [
      { to: '/portfolio', label: 'nav.portfolio' },
      { to: '/performance', label: 'nav.performance' },
      { to: '/trades', label: 'nav.trades' },
      { to: '/risk', label: 'nav.risk' },
    ],
  },
];

const MODE = { paper: true, broker: 'MOCK' };
const WATCHLIST = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'GOOGL'];

export default function Sidebar() {
  const [refreshAt, setRefreshAt] = useState(() => new Date());

  const modeWord = MODE.paper ? t('app.sidebar.mode_paper') : t('app.sidebar.mode_live');
  const modeColor = MODE.paper ? 'bg-success' : 'bg-danger';

  return (
    <aside className="w-72 shrink-0 h-full overflow-y-auto bg-panel border-r border-border p-4 text-sm">
      {/* Title + refresh time */}
      <div className="font-bold">{t('app.sidebar.title')}</div>
      <div className="text-xs text-muted mb-3">
        {t('app.sidebar.last_refresh', { time: refreshAt.toLocaleTimeString(getLocale(), { hour12: false }) })}
      </div>

      {/* Mode pill */}
      <div className={clsx('mode-pill text-white mb-3', modeColor)}>
        {modeWord} — {MODE.broker}
      </div>

      <div className="st-divider" />

      {/* Function nav: analysis + trading only */}
      <div className="nav-radio">
        <div className="group-label">{t('app.sidebar.navigate')}</div>
        {GROUPS.map((g) => (
          <div key={g.title}>
            <div className="group-label">{t(g.title)}</div>
            {g.items.map((i) => (
              <NavLink
                key={i.to}
                to={i.to}
                end
                className={({ isActive }) => clsx(isActive && 'active')}
              >
                <span className="dot" />
                <span>{t(i.label)}</span>
              </NavLink>
            ))}
          </div>
        ))}
      </div>

      <div className="st-divider" />

      {/* Watchlist */}
      <div className="font-semibold mb-1">{t('app.sidebar.watchlist')}</div>
      <div className="code-block mb-3">{WATCHLIST.join(', ')}</div>

      <button
        className="btn-ghost btn-block mb-4"
        onClick={() => { setRefreshAt(new Date()); location.reload(); }}
      >
        {t('app.sidebar.refresh')}
      </button>

      <div className="st-divider" />

      {/* Quick trade (placeholder until POST /orders exists) */}
      <div className="font-semibold mb-2">{t('qt.header')}</div>
      <div className="space-y-2 opacity-60">
        <input className="input" placeholder={t('qt.ticker')} disabled />
        <select className="input" disabled>
          <option>{t('qt.side.buy')}</option>
          <option>{t('qt.side.sell')}</option>
        </select>
        <input className="input" type="number" placeholder={t('qt.qty')} disabled />
        <button className="btn-primary btn-block" disabled>{t('qt.submit')}</button>
        <div className="text-xs text-muted">{t('qt.disabled')}</div>
      </div>
    </aside>
  );
}
