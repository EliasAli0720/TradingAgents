import { useBrokerAccountContext } from '@/hooks/useBrokerAccountContext';
import { t } from '@/i18n';

// Display registry for known brokers. `simulated: true` means the broker itself
// is a sandbox with no real login (the built-in mock). Real brokerages
// (IBKR / Alpaca / Webull …) are added here as a single entry each; the badge
// then distinguishes paper vs live from the connected account's `paper` flag.
const BROKER_META: Record<string, { label: string; simulated: boolean }> = {
  mock: { label: 'MOCK', simulated: true },
  ibkr: { label: 'IBKR', simulated: false },
  alpaca: { label: 'Alpaca', simulated: false },
  webull: { label: 'Webull', simulated: false },
};

// Mode pill driven entirely by the *connected* account — no env / hardcoded mode:
//   • not connected         → grey  「未连接」
//   • mock broker           → green 「模拟 · MOCK」
//   • real brokerage login  → red   「真实用户 · IBKR · 实盘/模拟盘」
export default function BrokerBadge() {
  const { selected } = useBrokerAccountContext();
  const connected = Boolean(selected);
  const key = (selected?.broker ?? '').toLowerCase();
  const meta = BROKER_META[key];

  if (!connected || !meta) {
    return (
      <div className="mode-pill bg-neutral text-white">
        {t('app.sidebar.mode_offline')}
        {meta ? ` · ${meta.label}` : ''}
      </div>
    );
  }

  if (meta.simulated) {
    return (
      <div className="mode-pill bg-success text-white">
        {t('app.sidebar.mode_sim')} · {meta.label}
      </div>
    );
  }

  const board = selected?.paper ? t('app.sidebar.board_paper') : t('app.sidebar.board_live');
  return (
    <div className="mode-pill bg-danger text-white">
      {t('app.sidebar.mode_real')} · {meta.label} · {board}
    </div>
  );
}
