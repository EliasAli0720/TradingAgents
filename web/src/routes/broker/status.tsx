import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getBrokerChannel } from '@/api/brokerChannel';
import { useAuth } from '@/hooks/useAuth';
import { Subheader, Caption, Info, ErrorBox } from '@/components/ui/Page';
import Metric, { KpiRow } from '@/components/ui/Metric';
import { getLocale, t } from '@/i18n';
import WebullConnectCard from '@/components/broker/WebullConnectCard';

function money(n: number): string {
  return n.toLocaleString(getLocale(), { maximumFractionDigits: 2 });
}

function fmt(iso: string): string {
  try {
    return new Date(iso).toLocaleString(getLocale(), { hour12: false });
  } catch {
    return iso;
  }
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-center text-sm">
      <span className="text-muted">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}

function Bool({ v }: { v: boolean }) {
  return <span className={v ? 'text-success' : 'text-danger'}>{v ? '✓' : '✕'}</span>;
}

export default function BrokerStatusPage() {
  const { canOperate } = useAuth();
  const qc = useQueryClient();
  const channel = getBrokerChannel();

  const status = useQuery({
    queryKey: ['broker', 'status'],
    queryFn: () => channel.status(),
    refetchInterval: 15000,
  });
  const account = useQuery({
    queryKey: ['broker', 'account'],
    queryFn: () => channel.account(),
    enabled: !!status.data?.connected,
  });
  const refresh = useMutation({
    mutationFn: () => channel.refresh(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['broker', 'status'] });
      qc.invalidateQueries({ queryKey: ['broker', 'account'] });
    },
  });
  const disconnect = useMutation({
    mutationFn: () => channel.disconnect(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['broker'] }),
  });

  const s = status.data;

  return (
    <div>
      <Subheader>{t('broker.status.title')}</Subheader>
      <Caption>{t('broker.status.caption')}</Caption>

      {channel.kind === 'server' && (
        <div className="mb-4">
          <WebullConnectCard />
        </div>
      )}

      {status.isLoading ? (
        <div className="text-muted">{t('common.loading')}</div>
      ) : status.error || !s ? (
        <ErrorBox>{t('common.load_failed')}</ErrorBox>
      ) : (
        <>
          <div className="card space-y-2 mb-4">
            <Row label={t('broker.field.broker')} value={s.broker.toUpperCase()} />
            <Row
              label={t('broker.field.connection')}
              value={
                <span className={`badge ${s.connected ? 'bg-successBg text-success' : 'bg-dangerBg text-danger'}`}>
                  {s.connected ? t('broker.connected') : t('broker.not_connected')}
                </span>
              }
            />
            <Row label={t('broker.field.gateway')} value={<Bool v={s.gateway_online} />} />
            <Row label={t('broker.field.session')} value={<Bool v={s.brokerage_session} />} />
            <Row label={t('broker.field.account')} value={s.account_id ?? '—'} />
            <Row
              label={t('broker.field.mode')}
              value={s.paper ? t('app.sidebar.mode_paper') : t('app.sidebar.mode_live')}
            />
            <Row label={t('broker.field.last_refresh')} value={s.last_refresh_at ? fmt(s.last_refresh_at) : '—'} />
            {s.last_error && (
              <Row label={t('broker.field.last_error')} value={<span className="text-danger">{s.last_error}</span>} />
            )}
          </div>

          {!s.connected && <Info>{t('broker.status.not_connected_hint')}</Info>}

          {canOperate && (
            <button className="btn-ghost mt-3" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
              {t('broker.action.refresh')}
            </button>
          )}
          {channel.supportsConnect && canOperate && (
            <button
              className="btn-ghost mt-3 ml-2"
              disabled={disconnect.isPending}
              onClick={() => disconnect.mutate()}
            >
              {t('broker.connect.disconnect')}
            </button>
          )}

          {s.connected && account.data && (
            <div className="mt-6">
              <Subheader>{t('broker.account.title')}</Subheader>
              <KpiRow>
                <Metric label={t('portfolio.total_value')} value={money(account.data.portfolio_value)} />
                <Metric label={t('portfolio.cash')} value={money(account.data.cash)} />
                <Metric label={t('broker.account.buying_power')} value={money(account.data.buying_power)} />
                <Metric label={t('broker.account.equity')} value={money(account.data.equity)} />
              </KpiRow>
            </div>
          )}
        </>
      )}
    </div>
  );
}
