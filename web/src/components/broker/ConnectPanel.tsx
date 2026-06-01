import { useState, type ReactNode } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useBrokerConnection } from '@/hooks/useBrokerConnection';
import type { BrokerCandidate, ConnectOpts } from '@/api/brokerChannel';
import { Subheader, Caption, Info, ErrorBox } from '@/components/ui/Page';
import { t } from '@/i18n';
import WebullConnectCard from './WebullConnectCard';

function Step({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className={ok ? 'text-success' : 'text-muted'}>{ok ? '✓' : '○'}</span>
      <span className={ok ? '' : 'text-muted'}>{label}</span>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="block text-xs text-muted mb-1">{label}</span>
      {children}
    </label>
  );
}

function candidateLabel(c: BrokerCandidate): string {
  const kind = c.kind === 'gateway' ? t('broker.connect.kind_gateway') : t('broker.connect.kind_tws');
  const board = c.paper ? t('app.sidebar.board_paper') : t('app.sidebar.board_live');
  return `${kind} · ${board}`;
}

// Connect-first gate for the desktop local channel. One-click connect probes the
// well-known IBKR ports and connects to the running TWS / IB Gateway, adopting
// the locally logged-in account automatically; if several are up the user picks.
// The manual form stays as an advanced fallback (custom host/port/account).
export default function ConnectPanel() {
  const { channel, status, isError, refetch } = useBrokerConnection();
  const qc = useQueryClient();

  const [host, setHost] = useState('127.0.0.1');
  const [port, setPort] = useState(7497);
  const [clientId, setClientId] = useState(0);
  const [accountId, setAccountId] = useState('');
  const [paper, setPaper] = useState(true);
  const [candidates, setCandidates] = useState<BrokerCandidate[] | null>(null);

  const connect = useMutation({
    mutationFn: (opts: ConnectOpts) => channel.connect(opts),
    onSuccess: () => {
      setCandidates(null);
      qc.invalidateQueries({ queryKey: ['broker'] });
      refetch();
    },
  });

  const connectTo = (c: BrokerCandidate) =>
    // account_id omitted → the sidecar adopts the logged-in account on connect.
    connect.mutate({ host: c.host, port: c.port, client_id: clientId, market_data_type: 3, paper: c.paper });

  const discover = useMutation({
    mutationFn: async () => {
      if (!channel.discover) throw new Error('discover unsupported');
      return (await channel.discover(host)).candidates;
    },
    onSuccess: (list) => {
      if (list.length === 1) connectTo(list[0]); // unambiguous → connect straight away
      else setCandidates(list); // 0 → "none found"; >1 → let the user pick
    },
  });

  // server-managed channel never renders this panel, but guard anyway.
  if (!channel.supportsConnect) {
    return (
      <div>
        <Subheader>{t('broker.connect.title')}</Subheader>
        <Info>{t('broker.connect.server_managed')}</Info>
      </div>
    );
  }

  const sidecarUp = !isError && !!status;
  const gatewayOnline = !!status?.gateway_online;
  const sessionLive = !!status?.brokerage_session;
  const busy = discover.isPending || connect.isPending;

  return (
    <div>
      <Subheader>{t('broker.connect.title')}</Subheader>
      <Caption>{t('broker.connect.caption')}</Caption>

      <div className="card space-y-2 my-4 max-w-md">
        <Step ok={sidecarUp} label={t('broker.connect.step_sidecar')} />
        <Step ok={gatewayOnline} label={t('broker.connect.step_gateway')} />
        <Step ok={sessionLive} label={t('broker.connect.step_session')} />
      </div>

      {/* One-click connect — auto-detect the running TWS / IB Gateway */}
      <div className="card space-y-3 max-w-md">
        <button
          className="btn-primary btn-block"
          disabled={busy}
          onClick={() => {
            setCandidates(null);
            discover.mutate();
          }}
        >
          {discover.isPending ? t('broker.connect.discovering') : t('broker.connect.oneclick')}
        </button>

        {candidates && candidates.length === 0 && <Info>{t('broker.connect.none_found')}</Info>}

        {candidates && candidates.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs text-muted">{t('broker.connect.pick')}</p>
            {candidates.map((c) => (
              <button
                key={`${c.host}:${c.port}`}
                className="btn-ghost btn-block flex items-center justify-between"
                disabled={connect.isPending}
                onClick={() => connectTo(c)}
              >
                <span>{candidateLabel(c)}</span>
                <span className="text-xs text-muted">:{c.port}</span>
              </button>
            ))}
          </div>
        )}

        {discover.isError && <ErrorBox>{t('broker.connect.discover_failed')}</ErrorBox>}
      </div>

      {/* Manual connect (advanced) — custom host/port, optionally pin an account */}
      <div className="card space-y-3 max-w-md mt-3">
        <p className="text-xs text-muted">{t('broker.connect.manual_title')}</p>
        <Field label={t('broker.connect.host')}>
          <input className="input" value={host} onChange={(e) => setHost(e.target.value)} />
        </Field>
        <Field label={t('broker.connect.port')}>
          <input
            className="input"
            type="number"
            value={port}
            onChange={(e) => setPort(Number(e.target.value))}
          />
        </Field>
        <Field label={t('broker.connect.client_id')}>
          <input
            className="input"
            type="number"
            value={clientId}
            onChange={(e) => setClientId(Number(e.target.value))}
          />
        </Field>
        <Field label={t('broker.connect.account_id')}>
          <input
            className="input"
            value={accountId}
            placeholder={t('broker.connect.account_id_ph')}
            onChange={(e) => setAccountId(e.target.value.toUpperCase())}
          />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={paper} onChange={(e) => setPaper(e.target.checked)} />
          {t('broker.connect.paper')}
        </label>
        <button
          className="btn-ghost btn-block"
          disabled={busy}
          onClick={() =>
            connect.mutate({
              host,
              port,
              client_id: clientId,
              market_data_type: 3,
              account_id: accountId.trim() || undefined,
              paper,
            })
          }
        >
          {connect.isPending ? t('broker.connect.connecting') : t('broker.connect.connect')}
        </button>
      </div>

      {connect.isError && (
        <div className="max-w-md mt-3">
          <ErrorBox>
            {(connect.error as { detail?: string; message?: string })?.detail ||
              (connect.error as { message?: string })?.message ||
              t('broker.connect.failed')}
          </ErrorBox>
        </div>
      )}

      <div className="mt-3 max-w-md">
        <Info>{t('broker.connect.hint')}</Info>
      </div>

      <div className="mt-6">
        <WebullConnectCard />
      </div>
    </div>
  );
}
