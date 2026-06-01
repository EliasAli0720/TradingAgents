import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { brokerApi } from '@/api/broker';
import { getBrokerChannel, isDesktop } from '@/api/brokerChannel';
import { shouldUseServerProposal } from '@/api/brokerReadiness';
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
  const desktop = isDesktop();

  const serverStatus = useQuery({
    queryKey: ['broker', 'status', 'server'],
    queryFn: () => brokerApi.status(),
    enabled: channel.kind === 'server' || desktop,
    // Webull (server) link state rarely changes; IBKR (local) needs liveness.
    // (Shared query key → effective interval is the min across observers, so
    // this must match the hook to actually back off on the server channel.)
    refetchInterval: 30000,
  });
  const activeServerBroker = channel.kind === 'server' || shouldUseServerProposal(serverStatus.data);
  const localStatus = useQuery({
    queryKey: ['broker', 'status', 'local'],
    queryFn: () => channel.status(),
    enabled: channel.kind === 'local' && !activeServerBroker,
    refetchInterval: 15000,
  });
  const status = activeServerBroker ? serverStatus : localStatus;
  const account = useQuery({
    queryKey: ['broker', 'account', activeServerBroker ? 'server' : 'local'],
    queryFn: () => (activeServerBroker ? brokerApi.account() : channel.account()),
    enabled: !!status.data?.connected,
  });
  const refresh = useMutation({
    mutationFn: () => (activeServerBroker ? brokerApi.refresh() : channel.refresh()),
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
  const isWebull = activeServerBroker && s?.broker === 'webull';
  const showWebullCard = activeServerBroker || desktop;

  return (
    <div>
      <Subheader>{t('broker.status.title')}</Subheader>
      <Caption>{t(isWebull ? 'broker.status.caption_webull' : 'broker.status.caption')}</Caption>

      {showWebullCard && (
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
            {/* Gateway / session are IBKR (local TWS) concepts; Webull is a
                stateless cloud REST broker with no gateway or session. */}
            {!isWebull && <Row label={t('broker.field.gateway')} value={<Bool v={s.gateway_online} />} />}
            {!isWebull && <Row label={t('broker.field.session')} value={<Bool v={s.brokerage_session} />} />}
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

          {/* Webull: the connect card above already prompts to link; only the
              IBKR (local) channel needs the connector/TWS hint here. */}
          {!s.connected && !isWebull && <Info>{t('broker.status.not_connected_hint')}</Info>}

          {canOperate && (
            <button className="btn-ghost mt-3" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
              {t('broker.action.refresh')}
            </button>
          )}
          {!activeServerBroker && channel.supportsConnect && canOperate && (
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
