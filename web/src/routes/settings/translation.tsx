import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  settingsApi,
  type TranslationSettingsInput,
  type TranslationProviderOption,
} from '@/api/settings';
import type { ApiError } from '@/api/client';
import { Subheader, Caption, Info } from '@/components/ui/Page';
import { ValidationResultCard, ValidationErrorCard } from '@/components/settings/ValidationResult';
import { t } from '@/i18n';

type FormState = {
  provider: string;
  backendUrl: string;
  apiKey: string;
};

export default function TranslationSettingsPage() {
  const qc = useQueryClient();

  const options = useQuery({
    queryKey: ['settings', 'translationOptions'],
    queryFn: settingsApi.translationOptions,
  });
  const current = useQuery({
    queryKey: ['settings', 'translation'],
    queryFn: () => settingsApi.translationGet().catch((e) => {
      if ((e as ApiError).status === 404) return null;
      throw e;
    }),
  });

  const [form, setForm] = useState<FormState>({ provider: '', backendUrl: '', apiKey: '' });
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (initialized || !options.data || current.isLoading) return;
    const providers = options.data.providers;
    if (providers.length === 0) return;
    const c = current.data;
    const prov = providers.find((p) => p.id === c?.llm_provider) ?? providers[0];
    setForm({
      provider: prov.id,
      backendUrl: c?.backend_url ?? prov.default_backend_url ?? '',
      apiKey: '',
    });
    setInitialized(true);
  }, [options.data, current.data, current.isLoading, initialized]);

  const currentProvider: TranslationProviderOption | undefined = useMemo(
    () => options.data?.providers.find((p) => p.id === form.provider),
    [options.data, form.provider],
  );

  function onProviderChange(id: string) {
    const prov = options.data?.providers.find((p) => p.id === id);
    if (!prov) return;
    setForm((f) => ({ ...f, provider: id, backendUrl: prov.default_backend_url ?? '' }));
  }

  const save = useMutation({
    mutationFn: (payload: TranslationSettingsInput) => settingsApi.translationPut(payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'translation'] }),
  });
  const clearKey = useMutation({
    mutationFn: () => settingsApi.translationClearKey(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'translation'] }),
  });
  const validate = useMutation({ mutationFn: () => settingsApi.translationValidate() });

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!currentProvider) return;
    const payload: TranslationSettingsInput = {
      llm_provider: currentProvider.id,
      model: currentProvider.model_id,
      backend_url: form.backendUrl || null,
    };
    if (form.apiKey) payload.api_key = form.apiKey;
    save.mutate(payload);
  }

  return (
    <div className="max-w-2xl">
      <Subheader>{t('nav.translation')}</Subheader>
      <Caption>{t('translation.caption')}</Caption>

      {options.isLoading || current.isLoading || !initialized ? (
        <div className="text-muted text-sm">{t('common.loading')}</div>
      ) : options.error || !options.data ? (
        <Info>{t('common.load_failed')}</Info>
      ) : (
        <>
          <div className="card flex items-center justify-between mb-4">
            <div className="text-sm">
              {t('model.current_key')}
              {current.data?.has_api_key
                ? <span className="font-mono">{current.data.api_key_masked}</span>
                : <span className="text-muted">{t('model.key_fallback')}</span>}
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-ghost"
                disabled={validate.isPending || !current.data}
                onClick={() => { validate.reset(); validate.mutate(); }}
              >
                {validate.isPending ? t('model.validating') : t('model.validate_key')}
              </button>
              <button
                type="button"
                className="btn-danger"
                disabled={!current.data?.has_api_key || clearKey.isPending}
                onClick={() => clearKey.mutate()}
              >
                {t('model.clear_key')}
              </button>
            </div>
          </div>

          {validate.data && (
            <ValidationResultCard
              result={validate.data}
              providerLabel={currentProvider?.label}
              modelId={currentProvider?.model_id}
            />
          )}
          {validate.error && (
            <ValidationErrorCard error={validate.error as unknown as ApiError} />
          )}

          <form className="card space-y-4 mt-4" onSubmit={onSubmit}>
            <div>
              <label className="label">Provider</label>
              <select className="input" value={form.provider} onChange={(e) => onProviderChange(e.target.value)}>
                {options.data.providers.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
              {currentProvider && (
                <div className="text-xs text-muted mt-1">
                  {t('translation.env_fallback')}
                  {currentProvider.required_env_var
                    ? <code className="font-mono">{currentProvider.required_env_var}</code>
                    : <span>{t('model.not_required')}</span>}
                </div>
              )}
            </div>

            <div>
              <label className="label">{t('translation.model')}</label>
              <input className="input font-mono" value={currentProvider?.model_label ?? ''} readOnly />
            </div>

            <div>
              <label className="label">Backend URL</label>
              <input
                className="input"
                value={form.backendUrl}
                onChange={(e) => setForm((f) => ({ ...f, backendUrl: e.target.value }))}
                readOnly={!currentProvider?.backend_url_editable}
              />
            </div>

            <div>
              <label className="label">{t('model.api_key_label')}</label>
              <input
                className="input"
                type="password"
                placeholder={current.data?.has_api_key ? t('model.api_key_saved_placeholder') : 'sk-...'}
                value={form.apiKey}
                onChange={(e) => setForm((f) => ({ ...f, apiKey: e.target.value }))}
                autoComplete="new-password"
              />
            </div>

            {save.error && (
              <div className="text-sm text-danger">
                {(save.error as unknown as ApiError).status} · {(save.error as unknown as ApiError).detail}
              </div>
            )}
            {save.isSuccess && <div className="text-sm text-success">{t('common.saved')}</div>}

            <div className="flex justify-end">
              <button className="btn-primary" disabled={save.isPending}>{t('common.save')}</button>
            </div>
          </form>
        </>
      )}
    </div>
  );
}
