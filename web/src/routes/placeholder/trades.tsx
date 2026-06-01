import { useQuery } from '@tanstack/react-query';
import { brokerApi } from '@/api/broker';
import { useBrokerConnection } from '@/hooks/useBrokerConnection';
import { Subheader, Info, ErrorBox } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';
import { getLocale, t } from '@/i18n';

function money(n: number): string {
  return n.toLocaleString(getLocale(), { maximumFractionDigits: 2 });
}
function pct(n: number): string {
  return `${(n * 100).toLocaleString(getLocale(), { maximumFractionDigits: 2 })}%`;
}

export default function TradesPage() {
  const { status } = useBrokerConnection();
  const accountId = status?.account_id ?? '';

  const q = useQuery({
    queryKey: ['trades', accountId],
    queryFn: () => brokerApi.trades(accountId),
    enabled: !!accountId,
    refetchInterval: 30000,
  });

  if (!accountId) {
    return (
      <div>
        <Subheader>{t('nav.trades')}</Subheader>
        <Info>{t('broker.not_connected_generic')}</Info>
      </div>
    );
  }

  const trades = q.data?.trades ?? [];
  const closed = q.data?.closed ?? [];
  const buys = trades.filter((r) => r.side.toLowerCase() === 'buy').length;
  const sells = trades.filter((r) => r.side.toLowerCase() === 'sell').length;
  const realized = closed.reduce((s, c) => s + c.realized_pnl, 0);

  return (
    <div>
      <Subheader>{t('nav.trades')}</Subheader>

      {q.isLoading ? (
        <div className="text-muted">{t('common.loading')}</div>
      ) : q.error ? (
        <ErrorBox>{t('common.load_failed')}</ErrorBox>
      ) : (
        <>
          <KpiRow>
            <Metric label={t('trades.total')} value={String(trades.length)} />
            <Metric label={t('trades.buy')} value={String(buys)} />
            <Metric label={t('trades.sell')} value={String(sells)} />
            <Metric
              label={t('trades.realized_pnl')}
              value={money(realized)}
              delta={realized !== 0 ? money(realized) : null}
              deltaPositive={realized >= 0}
            />
          </KpiRow>

          <div className="mt-6">
            <Subheader>{t('trades.details')}</Subheader>
            <div className="card overflow-x-auto">
              <table className="df">
                <thead>
                  <tr>
                    <th>{t('table.trade_date')}</th>
                    <th>{t('table.ticker')}</th>
                    <th>{t('table.side')}</th>
                    <th>{t('table.qty')}</th>
                    <th>{t('table.price')}</th>
                    <th>{t('table.market_value')}</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((r, i) => (
                    <tr key={`${r.order_id}-${i}`}>
                      <td className="font-mono">{r.trade_date}</td>
                      <td className="font-mono">{r.ticker}</td>
                      <td className={r.side.toLowerCase() === 'buy' ? 'text-success' : 'text-danger'}>
                        {r.side.toUpperCase()}
                      </td>
                      <td>{r.qty}</td>
                      <td>{money(r.price)}</td>
                      <td>{money(r.total_value)}</td>
                    </tr>
                  ))}
                  {trades.length === 0 && (
                    <tr><td colSpan={6} className="py-4 text-muted text-center">{t('common.empty')}</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <div className="mt-6">
            <Subheader>{t('trades.closed')}</Subheader>
            <div className="card overflow-x-auto">
              <table className="df">
                <thead>
                  <tr>
                    <th>{t('table.ticker')}</th>
                    <th>{t('trades.entry_price')}</th>
                    <th>{t('trades.exit_price')}</th>
                    <th>{t('table.qty')}</th>
                    <th>{t('trades.realized_pnl')}</th>
                    <th>{t('trades.holding_days')}</th>
                    <th>{t('trades.exit_date')}</th>
                  </tr>
                </thead>
                <tbody>
                  {closed.map((c, i) => (
                    <tr key={`${c.ticker}-${c.exit_date}-${i}`}>
                      <td className="font-mono">{c.ticker}</td>
                      <td>{money(c.entry_price)}</td>
                      <td>{money(c.exit_price)}</td>
                      <td>{c.qty}</td>
                      <td className={c.realized_pnl >= 0 ? 'text-success' : 'text-danger'}>
                        {money(c.realized_pnl)} ({pct(c.realized_pnl_pct)})
                      </td>
                      <td>{c.holding_days}</td>
                      <td className="font-mono">{c.exit_date}</td>
                    </tr>
                  ))}
                  {closed.length === 0 && (
                    <tr><td colSpan={7} className="py-4 text-muted text-center">{t('common.empty')}</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
