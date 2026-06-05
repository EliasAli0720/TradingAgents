import { useQuery } from '@tanstack/react-query';
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

export default function PortfolioPage() {
  const broker = useBrokerAccountContext();
  const selected = broker.selected;
  const connected = Boolean(selected);

  const account = useQuery({
    queryKey: ['broker', 'account', selected?.key],
    queryFn: broker.account,
    enabled: connected,
  });
  const positions = useQuery({
    queryKey: ['broker', 'positions', selected?.key],
    queryFn: broker.positions,
    enabled: connected,
    refetchInterval: 15000,
  });

  const invested = (positions.data ?? []).reduce((sum, p) => sum + p.market_value, 0);
  const unrealized = (positions.data ?? []).reduce((sum, p) => sum + p.unrealized_pnl, 0);

  return (
    <div>
      <Subheader>{t('portfolio.current')}</Subheader>
      <div className="mb-3">
        <BrokerAccountSelector
          options={broker.options}
          selectedKey={broker.selectedKey}
          onChange={broker.setSelectedKey}
        />
      </div>

      {!connected ? (
        <Info>{t('broker.not_connected_generic')}</Info>
      ) : (
        <>
          <KpiRow>
            <Metric label={t('portfolio.total_value')} value={account.data ? money(account.data.portfolio_value) : '—'} />
            <Metric label={t('portfolio.cash')} value={account.data ? money(account.data.cash) : '—'} />
            <Metric label={t('portfolio.invested')} value={money(invested)} />
            <Metric
              label={t('portfolio.unrealized_pnl')}
              value={money(unrealized)}
              delta={unrealized !== 0 ? money(unrealized) : null}
              deltaPositive={unrealized >= 0}
            />
          </KpiRow>

          <div className="mt-6" />
          <Subheader>{t('portfolio.positions')}</Subheader>
          {positions.isLoading ? (
            <div className="text-muted">{t('common.loading')}</div>
          ) : positions.error ? (
            <ErrorBox>{t('common.load_failed')}</ErrorBox>
          ) : (
            <div className="card overflow-x-auto">
              <table className="df">
                <thead>
                  <tr>
                    <th>{t('table.ticker')}</th>
                    <th>{t('table.qty')}</th>
                    <th>{t('table.avg_cost')}</th>
                    <th>{t('table.price')}</th>
                    <th>{t('table.market_value')}</th>
                    <th>{t('portfolio.unrealized_pnl')}</th>
                    <th>%</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.data?.map((p) => (
                    <tr key={p.ticker}>
                      <td className="font-mono">{p.ticker}</td>
                      <td>{p.qty}</td>
                      <td>{money(p.avg_entry_price)}</td>
                      <td>{money(p.current_price)}</td>
                      <td>{money(p.market_value)}</td>
                      <td className={p.unrealized_pnl >= 0 ? 'text-success' : 'text-danger'}>
                        {money(p.unrealized_pnl)}
                      </td>
                      <td className={p.unrealized_pnl_pct >= 0 ? 'text-success' : 'text-danger'}>
                        {pct(p.unrealized_pnl_pct)}
                      </td>
                    </tr>
                  ))}
                  {positions.data?.length === 0 && (
                    <tr>
                      <td colSpan={7} className="py-4 text-muted text-center">{t('common.empty')}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
