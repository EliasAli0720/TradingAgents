import { useQuery } from '@tanstack/react-query';
import { brokerApi } from '@/api/broker';
import { useBrokerAccountContext } from '@/hooks/useBrokerAccountContext';
import BrokerAccountSelector from '@/components/broker/BrokerAccountSelector';
import { Subheader, Info, ErrorBox } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';
import { getLocale, t } from '@/i18n';

function money(n: number): string {
  return n.toLocaleString(getLocale(), { maximumFractionDigits: 2 });
}
function pct(n: number): string {
  return `${(n * 100).toLocaleString(getLocale(), { maximumFractionDigits: 2 })}%`;
}
function num(n: number): string {
  return n.toLocaleString(getLocale(), { maximumFractionDigits: 2 });
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length < 2) return null;
  const w = 600;
  const h = 80;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const step = w / (points.length - 1);
  const d = points.map((v, i) => `${(i * step).toFixed(1)},${(h - ((v - min) / range) * h).toFixed(1)}`).join(' ');
  const up = points[points.length - 1] >= points[0];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="w-full h-20">
      <polyline points={d} fill="none" stroke={up ? '#4CAF50' : '#F44336'} strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export default function PerformancePage() {
  const broker = useBrokerAccountContext();
  const accountId = broker.selected?.account_id ?? '';
  const brokerName = broker.selected?.broker ?? 'ibkr';

  const q = useQuery({
    queryKey: ['perf', brokerName, accountId],
    queryFn: () => brokerApi.performance(accountId, brokerName),
    enabled: !!accountId,
    refetchInterval: 30000,
  });

  if (!accountId) {
    return (
      <div>
        <Subheader>{t('nav.performance')}</Subheader>
        <div className="mb-3">
          <BrokerAccountSelector
            options={broker.options}
            selectedKey={broker.selectedKey}
            onChange={broker.setSelectedKey}
          />
        </div>
        <Info>{t('broker.not_connected_generic')}</Info>
      </div>
    );
  }

  const d = q.data;
  const curve = d?.equity_curve ?? [];

  return (
    <div>
      <Subheader>{t('nav.performance')}</Subheader>
      <div className="mb-3">
        <BrokerAccountSelector
          options={broker.options}
          selectedKey={broker.selectedKey}
          onChange={broker.setSelectedKey}
        />
      </div>

      {q.isLoading ? (
        <div className="text-muted">{t('common.loading')}</div>
      ) : q.error || !d ? (
        <ErrorBox>{t('common.load_failed')}</ErrorBox>
      ) : (
        <>
          <KpiRow>
            <Metric
              label={t('performance.total_return')}
              value={pct(d.total_return_pct)}
              deltaPositive={d.total_return_pct >= 0}
              delta={pct(d.total_return_pct)}
            />
            <Metric label={t('performance.sharpe')} value={num(d.sharpe_ratio)} />
            <Metric label={t('performance.max_drawdown')} value={pct(d.max_drawdown)} />
            <Metric label={t('performance.win_rate')} value={pct(d.win_rate)} />
          </KpiRow>
          <div className="mt-4" />
          <KpiRow>
            <Metric label={t('performance.total_trades')} value={String(d.total_trades)} />
            <Metric label={t('performance.avg_win')} value={money(d.avg_win)} />
            <Metric label={t('performance.avg_loss')} value={money(d.avg_loss)} />
            <Metric label={t('performance.profit_factor')} value={d.profit_factor == null ? '∞' : num(d.profit_factor)} />
          </KpiRow>
          <div className="mt-4" />
          <KpiRow>
            <Metric label={t('performance.equity_start')} value={money(d.starting_equity)} />
            <Metric label={t('performance.equity_now')} value={money(d.current_equity)} />
          </KpiRow>

          <div className="mt-6">
            <Subheader>{t('performance.equity')}</Subheader>
            {curve.length < 2 ? (
              <div className="card text-muted text-sm">{t('performance.no_history')}</div>
            ) : (
              <div className="card">
                <Sparkline points={curve.map((s) => s.total_value)} />
              </div>
            )}
          </div>

          {curve.length > 0 && (
            <div className="mt-6">
              <Subheader>{t('performance.recent_snapshots')}</Subheader>
              <div className="card overflow-x-auto">
                <table className="df">
                  <thead>
                    <tr>
                      <th>{t('table.trade_date')}</th>
                      <th>{t('portfolio.total_value')}</th>
                      <th>{t('portfolio.cash')}</th>
                      <th>{t('performance.daily_pnl')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {curve.slice(-20).reverse().map((s) => (
                      <tr key={s.date}>
                        <td className="font-mono">{s.date}</td>
                        <td>{money(s.total_value)}</td>
                        <td>{money(s.cash)}</td>
                        <td className={s.daily_pnl >= 0 ? 'text-success' : 'text-danger'}>
                          {money(s.daily_pnl)} ({pct(s.daily_pnl_pct)})
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
