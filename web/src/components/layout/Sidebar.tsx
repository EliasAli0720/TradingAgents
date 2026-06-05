import { NavLink } from 'react-router-dom';
import clsx from 'clsx';
import { t } from '@/i18n';
import QuickTrade from '@/components/broker/QuickTrade';
import BrokerBadge from '@/components/broker/BrokerBadge';

type Item = { to: string; label: string };

const GROUPS: { title: string; items: Item[] }[] = [
  {
    title: 'group.analysis',
    items: [
      { to: '/recommendations', label: 'nav.recommendations' },
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

export default function Sidebar() {
  return (
    <aside className="w-72 shrink-0 h-full overflow-y-auto bg-panel border-r border-border p-4 text-sm shadow-2xl shadow-black/20">
      <div className="flex items-center gap-3 rounded-lg border border-brandGold/30 bg-[linear-gradient(145deg,#F7F4EA_0%,#EEF0E7_58%,#C6CDBF_100%)] p-3 shadow-md shadow-black/10">
        <img
          src="/brand/icon.png"
          alt=""
          className="h-12 w-12 shrink-0 rounded-md object-cover ring-1 ring-brandGold/45"
          aria-hidden="true"
        />
        <div className="min-w-0">
          <img
            src="/brand/logo.png"
            alt={t('app.sidebar.title')}
            className="h-8 max-w-[11.5rem] object-contain object-left"
          />
          <div className="mt-1 text-xs text-[#3B563F]">{t('app.sidebar.product_tagline')}</div>
        </div>
      </div>

      {/* Mode pill — reflects the connected broker account (mock / real) */}
      <div className="my-3">
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

      {/* Manual quick order — places on the connected account via the sidecar */}
      <QuickTrade />
    </aside>
  );
}
