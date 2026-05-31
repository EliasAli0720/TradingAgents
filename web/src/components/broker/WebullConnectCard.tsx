import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { brokerApi } from '@/api/broker';
import { Info, ErrorBox } from '@/components/ui/Page';
import { t } from '@/i18n';

// Webull Connect API link card (server / cloud broker). Shown in the browser
// (server channel): the user authorises their own Webull account via OAuth. The
// platform exchanges + stores the tokens server-side (see broker_oauth.py); here
// we only start the flow and reflect the link state. Account data and trading
// then flow through the same /broker/* endpoints (provider picks Webull).
export default function WebullConnectCard() {
  const qc = useQueryClient();
  const [banner, setBanner] = useState<'connected' | 'error' | null>(null);

  // Reflect the OAuth callback result (?connected=webull / ?error=…) once, then
  // strip it from the URL so a refresh doesn't re-show the banner.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('connected') === 'webull') setBanner('connected');
    else if (params.get('error')) setBanner('error');
    if (params.has('connected') || params.has('error')) {
      params.delete('connected');
      params.delete('error');
      const qs = params.toString();
      window.history.replaceState({}, '', window.location.pathname + (qs ? `?${qs}` : ''));
    }
  }, []);

  const status = useQuery({
    queryKey: ['broker', 'webull', 'status'],
    queryFn: () => brokerApi.webull.status(),
  });

  const connect = useMutation({
    mutationFn: () => brokerApi.webull.authorizeUrl(),
    onSuccess: (url) => window.location.assign(url), // leaves SPA; returns via callback
  });

  const disconnect = useMutation({
    mutationFn: () => brokerApi.webull.disconnect(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['broker'] });
    },
  });

  const s = status.data;
  const connected = Boolean(s?.connected);
  const state = s?.status ?? 'not_connected';

  return (
    <div className="card space-y-3 max-w-md">
      <div className="flex items-center justify-between">
        <span className="font-medium">{t('broker.webull.title')}</span>
        <span className={`badge ${connected ? 'bg-successBg text-success' : 'bg-neutral text-white'}`}>
          {t(`broker.webull.state.${state}`)}
        </span>
      </div>
      <p className="text-xs text-muted">{t('broker.webull.subtitle')}</p>

      {connected && s?.account_id && (
        <div className="text-sm">
          {t('broker.field.account')}: <span className="font-medium">{s.account_id}</span>
        </div>
      )}

      {banner === 'connected' && <Info>{t('broker.webull.linked')}</Info>}
      {banner === 'error' && <ErrorBox>{t('broker.webull.linkFailed')}</ErrorBox>}
      {connect.isError && <ErrorBox>{t('broker.webull.linkFailed')}</ErrorBox>}

      <div className="flex gap-2">
        {!connected ? (
          <button
            className="btn-primary"
            disabled={connect.isPending || status.isLoading}
            onClick={() => connect.mutate()}
          >
            {state === 'expired' ? t('broker.webull.reconnect') : t('broker.webull.connect')}
          </button>
        ) : (
          <button className="btn-ghost" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
            {t('broker.webull.disconnect')}
          </button>
        )}
      </div>
    </div>
  );
}
