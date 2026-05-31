import { NavLink } from 'react-router-dom';
import clsx from 'clsx';
import { useState } from 'react';
import { getLocale, t } from '@/i18n';
import QuickTrade from '@/components/broker/QuickTrade';
import BrokerBadge from '@/components/broker/BrokerBadge';

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
      { to: '/broker', label: 'nav.broker' },
      { to: '/portfolio', label: 'nav.portfolio' },
      { to: '/broker/approvals', label: 'nav.approvals' },
      { to: '/broker/orders', label: 'nav.orders' },
      { to: '/performance', label: 'nav.performance' },
      { to: '/trades', label: 'nav.trades' },
      { to: '/risk', label: 'nav.risk' },
    ],
  },
];

const WATCHLIST = ['AAPL', 'MSFT', 'NVDA', 'TSLA', 'GOOGL'];

export default function Sidebar() {
  const [refreshAt, setRefreshAt] = useState(() => new Date());

  return (
    <aside className="w-72 shrink-0 h-full overflow-y-auto bg-panel border-r border-border p-4 text-sm">
      {/* Title + refresh time */}
      <div className="font-bold">{t('app.sidebar.title')}</div>
      <div className="text-xs text-muted mb-3">
        {t('app.sidebar.last_refresh', { time: refreshAt.toLocaleTimeString(getLocale(), { hour12: false }) })}
      </div>

      {/* Mode pill — reflects the connected broker account (mock / real) */}
      <div className="mb-3">
        <BrokerBadge />
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

      {/* Manual quick order — places on the connected account via the sidecar */}
      <QuickTrade />
    </aside>
  );
}
