import { useQuery } from '@tanstack/react-query';
import { getBrokerChannel } from '@/api/brokerChannel';
import { Subheader, Caption, Info } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';
import { getLocale, t } from '@/i18n';

// Hard-limit defaults — mirror tradingbot/config.py RiskGate knobs.
const MAX_SINGLE = 0.1; // max_single_position_pct
const MAX_TOTAL = 0.8; // max_total_exposure_pct
const MIN_CASH = 1000; // min_cash_reserve (absolute)

function money(n: number): string {
  return n.toLocaleString(getLocale(), { maximumFractionDigits: 2 });
}
function pct(n: number): string {
  return `${(n * 100).toLocaleString(getLocale(), { maximumFractionDigits: 1 })}%`;
}

function Bar({ ratio, limit }: { ratio: number; limit: number }) {
  const over = ratio > limit;
  return (
    <div className="w-full bg-bg border border-border rounded h-3 overflow-hidden relative">
      <div
        className={over ? 'h-full bg-danger' : 'h-full bg-success'}
        style={{ width: `${Math.min(100, Math.max(0, ratio * 100))}%` }}
      />
      <div className="absolute top-0 bottom-0 border-r border-white/40" style={{ left: `${limit * 100}%` }} />
    </div>
  );
}

export default function RiskPage() {
  const channel = getBrokerChannel();
  const status = useQuery({ queryKey: ['broker', 'status'], queryFn: () => channel.status() });
  const connected = !!status.data?.connected;

  const account = useQuery({
    queryKey: ['broker', 'account'],
    queryFn: () => channel.account(),
    enabled: connected,
  });
  const positions = useQuery({
    queryKey: ['broker', 'positions'],
    queryFn: () => channel.positions(),
    enabled: connected,
    refetchInterval: 15000,
  });

  const acct = account.data;
  const pos = positions.data ?? [];
  const equity = acct?.equity || acct?.portfolio_value || 0;
  const invested = pos.reduce((s, p) => s + p.market_value, 0);
  const cash = acct?.cash ?? 0;
  const investmentRatio = equity > 0 ? invested / equity : 0;
  const ranked = [...pos]
    .map((p) => ({ ...p, weight: equity > 0 ? p.market_value / equity : 0 }))
    .sort((a, b) => b.weight - a.weight);
  const largest = ranked[0];

  return (
    <div>
      <Subheader>{t('nav.risk')}</Subheader>
      <Caption>{t('risk.caption')}</Caption>

      {!connected ? (
        <div className="mt-3"><Info>{t('broker.not_connected_generic')}</Info></div>
      ) : (
        <>
          <KpiRow>
            <Metric label={t('risk.investment_ratio')} value={pct(investmentRatio)} />
            <Metric label={t('risk.cash_available')} value={money(cash)} />
            <Metric label={t('risk.invested_amount')} value={money(invested)} />
            <Metric
              label={t('risk.largest_position')}
              value={largest ? `${largest.ticker} ${pct(largest.weight)}` : '—'}
            />
          </KpiRow>

          <div className="mt-6">
            <Subheader>{t('risk.total_exposure')}</Subheader>
            <div className="card space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-muted">{pct(investmentRatio)} {t('risk.pct_equity')}</span>
                <span className={investmentRatio > MAX_TOTAL ? 'text-danger' : 'text-success'}>
                  {t('risk.limit')} {pct(MAX_TOTAL)} · {investmentRatio > MAX_TOTAL ? t('risk.over_limit') : t('risk.within_limit')}
                </span>
              </div>
              <Bar ratio={investmentRatio} limit={MAX_TOTAL} />
            </div>
          </div>

          <div className="mt-6">
            <Subheader>{t('risk.concentration')}</Subheader>
            <div className="card overflow-x-auto">
              <table className="df">
                <thead>
                  <tr>
                    <th>{t('table.ticker')}</th>
                    <th>{t('table.market_value')}</th>
                    <th>{t('risk.pct_equity')}</th>
                    <th>{t('table.status')}</th>
                  </tr>
                </thead>
                <tbody>
                  {ranked.map((p) => (
                    <tr key={p.ticker}>
                      <td className="font-mono">{p.ticker}</td>
                      <td>{money(p.market_value)}</td>
                      <td className={p.weight > MAX_SINGLE ? 'text-danger' : ''}>{pct(p.weight)}</td>
                      <td>
                        <span className={`badge ${p.weight > MAX_SINGLE ? 'bg-dangerBg text-danger' : 'bg-successBg text-success'}`}>
                          {p.weight > MAX_SINGLE ? t('risk.over_limit') : t('risk.within_limit')}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {ranked.length === 0 && (
                    <tr><td colSpan={4} className="py-4 text-muted text-center">{t('common.empty')}</td></tr>
                  )}
                </tbody>
              </table>
              <div className="text-xs text-muted mt-2">{t('risk.limit')} {t('risk.concentration')}: {pct(MAX_SINGLE)} {t('risk.pct_equity')}</div>
            </div>
          </div>

          <div className="mt-6">
            <Subheader>{t('risk.min_cash')}</Subheader>
            <div className="card flex justify-between text-sm">
              <span className="text-muted">{money(cash)} / {t('risk.limit')} {money(MIN_CASH)}</span>
              <span className={cash < MIN_CASH ? 'text-danger' : 'text-success'}>
                {cash < MIN_CASH ? t('risk.over_limit') : t('risk.within_limit')}
              </span>
            </div>
          </div>

          <div className="mt-6">
            <Subheader>{t('risk.circuit_breaker')}</Subheader>
            <div className="card text-muted text-sm">{t('risk.no_daily_ref')}</div>
          </div>
        </>
      )}
    </div>
  );
}
