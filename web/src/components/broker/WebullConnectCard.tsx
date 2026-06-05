import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { brokerApi } from '@/api/broker';
import { Info, ErrorBox, Spinner } from '@/components/ui/Page';
import { t } from '@/i18n';

// Webull Connect API link card (server / cloud broker). Shown in the browser
// (server channel): the user authorises their own Webull account via OAuth. The
// platform exchanges + stores the tokens server-side (see broker_oauth.py); here
// we only start the flow and reflect the link state. Account data and trading
// then flow through the same /broker/* endpoints (provider picks Webull).
export default function WebullConnectCard() {
  const qc = useQueryClient();
  const [banner, setBanner] = useState<'connected' | 'error' | null>(null);
  const [mode, setMode] = useState<'oauth' | 'api_key'>('api_key');
  const [appKey, setAppKey] = useState('');
  const [appSecret, setAppSecret] = useState('');
  const [accountId, setAccountId] = useState('');

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

  const connectApiKey = useMutation({
    mutationFn: () => brokerApi.webull.connectApiKey({
      app_key: appKey.trim(),
      app_secret: appSecret.trim(),
      account_id: accountId.trim() || undefined,
    }),
    onSuccess: () => {
      setBanner('connected');
      setAppSecret('');
      qc.invalidateQueries({ queryKey: ['broker'] });
    },
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
  const canSubmitApiKey = Boolean(appKey.trim() && appSecret.trim());

  function submitApiKey(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canSubmitApiKey) return;
    connectApiKey.mutate();
  }

  return (
    <div className="card space-y-3 max-w-xl">
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
      {connected && s?.auth_type && (
        <div className="text-sm">
          {t('broker.webull.authType')}: <span className="font-medium">{t(`broker.webull.auth.${s.auth_type}`)}</span>
        </div>
      )}

      {banner === 'connected' && <Info>{t('broker.webull.linked')}</Info>}
      {banner === 'error' && <ErrorBox>{t('broker.webull.linkFailed')}</ErrorBox>}
      {connect.isError && <ErrorBox>{t('broker.webull.linkFailed')}</ErrorBox>}
      {connectApiKey.isError && <ErrorBox>{t('broker.webull.apiKeyFailed')}</ErrorBox>}

      {!connected ? (
        <div className="space-y-3">
          <div className="inline-flex overflow-hidden rounded-md border border-border">
            <button
              type="button"
              className={`px-3 py-1.5 text-sm ${mode === 'api_key' ? 'bg-brandGold text-bg' : 'text-muted hover:bg-brandGold/10'}`}
              onClick={() => setMode('api_key')}
            >
              {t('broker.webull.mode.apiKey')}
            </button>
            <button
              type="button"
              className={`px-3 py-1.5 text-sm border-l border-border ${mode === 'oauth' ? 'bg-brandGold text-bg' : 'text-muted hover:bg-brandGold/10'}`}
              onClick={() => setMode('oauth')}
            >
              {t('broker.webull.mode.oauth')}
            </button>
          </div>

          {mode === 'api_key' ? (
            <form className="grid gap-2 sm:grid-cols-2" onSubmit={submitApiKey}>
              <label className="block">
                <span className="label">{t('broker.webull.appKey')}</span>
                <input className="input font-mono" value={appKey} onChange={(e) => setAppKey(e.target.value)} />
              </label>
              <label className="block">
                <span className="label">{t('broker.webull.appSecret')}</span>
                <input
                  className="input font-mono"
                  type="password"
                  value={appSecret}
                  onChange={(e) => setAppSecret(e.target.value)}
                />
              </label>
              <label className="block sm:col-span-2">
                <span className="label">{t('broker.connect.account_id')}</span>
                <input
                  className="input font-mono"
                  value={accountId}
                  placeholder={t('broker.connect.account_id_ph')}
                  onChange={(e) => setAccountId(e.target.value)}
                />
              </label>
              <div className="sm:col-span-2">
                <button
                  type="submit"
                  className="btn-primary inline-flex items-center gap-2"
                  disabled={connectApiKey.isPending || status.isLoading || !canSubmitApiKey}
                >
                  {connectApiKey.isPending && <Spinner />}
                  {connectApiKey.isPending ? t('broker.webull.connecting') : t('broker.webull.connectApiKey')}
                </button>
              </div>
            </form>
          ) : (
            <button
              type="button"
              className="btn-primary inline-flex items-center gap-2"
              disabled={connect.isPending || status.isLoading}
              onClick={() => connect.mutate()}
            >
              {connect.isPending && <Spinner />}
              {connect.isPending
                ? t('broker.webull.connecting')
                : state === 'expired'
                  ? t('broker.webull.reconnect')
                  : t('broker.webull.connect')}
            </button>
          )}
        </div>
      ) : (
        <div className="flex gap-2">
          <button
            className="btn-ghost inline-flex items-center gap-2"
            disabled={disconnect.isPending}
            onClick={() => disconnect.mutate()}
          >
            {disconnect.isPending && <Spinner />}
            {t('broker.webull.disconnect')}
          </button>
        </div>
      )}
    </div>
  );
}
