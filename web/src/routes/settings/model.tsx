import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { settingsApi, type ModelSettingsInput, type ProviderOption, type ModelChoice } from '@/api/settings';
import type { ApiError } from '@/api/client';
import { Subheader, Caption, Info } from '@/components/ui/Page';
import { ValidationResultCard, ValidationErrorCard } from '@/components/settings/ValidationResult';
import { t } from '@/i18n';

const CUSTOM = '__custom__';

type FormState = {
  provider: string;
  quick: string;       // model id or CUSTOM
  quickCustom: string; // typed value when CUSTOM
  deep: string;
  deepCustom: string;
  backendUrl: string;
  apiKey: string;
};

export default function ModelSettingsPage() {
  const qc = useQueryClient();

  const options = useQuery({ queryKey: ['settings', 'modelOptions'], queryFn: settingsApi.options });
  const current = useQuery({
    queryKey: ['settings', 'model'],
    queryFn: () => settingsApi.get().catch((e) => {
      if ((e as ApiError).status === 404) return null;
      throw e;
    }),
  });

  const [form, setForm] = useState<FormState>({
    provider: '', quick: '', quickCustom: '', deep: '', deepCustom: '',
    backendUrl: '', apiKey: '',
  });
  const [initialized, setInitialized] = useState(false);

  // Seed form once options + current load
  useEffect(() => {
    if (initialized || !options.data) return;
    if (current.isLoading) return;
    const providers = options.data.providers;
    if (providers.length === 0) return;

    const c = current.data;
    const providerId = c?.llm_provider ?? providers[0].id;
    const prov = providers.find((p) => p.id === providerId) ?? providers[0];

    const matchOrCustom = (val: string | undefined, list: ModelChoice[]) => {
      if (!val) return list[0]?.id ?? CUSTOM;
      return list.some((m) => m.id === val) ? val : CUSTOM;
    };
    const quick = matchOrCustom(c?.quick_think_llm, prov.quick_models);
    const deep  = matchOrCustom(c?.deep_think_llm,  prov.deep_models);

    setForm({
      provider: prov.id,
      quick,
      quickCustom: quick === CUSTOM ? (c?.quick_think_llm ?? '') : '',
      deep,
      deepCustom: deep === CUSTOM ? (c?.deep_think_llm ?? '') : '',
      backendUrl: c?.backend_url ?? prov.default_backend_url ?? '',
      apiKey: '',
    });
    setInitialized(true);
  }, [options.data, current.data, current.isLoading, initialized]);

  const currentProvider: ProviderOption | undefined = useMemo(
    () => options.data?.providers.find((p) => p.id === form.provider),
    [options.data, form.provider],
  );

  // When provider changes, reseed dependent fields to that provider's defaults
  function onProviderChange(id: string) {
    const prov = options.data?.providers.find((p) => p.id === id);
    if (!prov) return;
    setForm((f) => ({
      ...f,
      provider: id,
      quick: prov.quick_models[0]?.id ?? CUSTOM,
      quickCustom: '',
      deep: prov.deep_models[0]?.id ?? CUSTOM,
      deepCustom: '',
      backendUrl: prov.default_backend_url ?? '',
      // keep apiKey (user might have one in clipboard); empty means "do not change"
    }));
  }

  const save = useMutation({
    mutationFn: (payload: ModelSettingsInput) => settingsApi.put(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings', 'model'] });
    },
  });

  const clearKey = useMutation({
    mutationFn: () => settingsApi.clearKey(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'model'] }),
  });

  const validate = useMutation({ mutationFn: () => settingsApi.validate() });

  function buildPayload(): ModelSettingsInput | null {
    if (!currentProvider) return null;
    const quickId = form.quick === CUSTOM ? form.quickCustom.trim() : form.quick;
    const deepId  = form.deep  === CUSTOM ? form.deepCustom.trim()  : form.deep;
    if (!quickId || !deepId) return null;
    const payload: ModelSettingsInput = {
      llm_provider: form.provider,
      deep_think_llm: deepId,
      quick_think_llm: quickId,
      backend_url: form.backendUrl ? form.backendUrl : null,
    };
    if (form.apiKey) payload.api_key = form.apiKey;
    return payload;
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = buildPayload();
    if (!payload) return;
    save.mutate(payload);
  }

  const needsKey = currentProvider && currentProvider.required_env_var !== null;

  return (
    <div className="max-w-2xl">
      <Subheader>{t('nav.model')}</Subheader>
      <Caption>{t('model.caption')}</Caption>

      {options.isLoading || current.isLoading || !initialized ? (
        <div className="text-muted text-sm">{t('common.loading')}</div>
      ) : options.error || !options.data ? (
        <Info>{t('model.options_failed')}</Info>
      ) : (
        <>
          {/* Current key state */}
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
                onClick={() => {
                  validate.reset();
                  validate.mutate();
                }}
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
              modelId={current.data?.quick_think_llm}
            />
          )}

          {validate.error && (
            <ValidationErrorCard error={validate.error as unknown as ApiError} />
          )}

          <form className="card space-y-4 mt-4" onSubmit={onSubmit}>
            {/* Provider */}
            <div>
              <label className="label">{t('model.provider')}</label>
              <select
                className="input"
                value={form.provider}
                onChange={(e) => onProviderChange(e.target.value)}
              >
                {options.data.providers.map((p) => (
                  <option key={p.id} value={p.id}>{p.label}</option>
                ))}
              </select>
              {currentProvider && (
                <div className="text-xs text-muted mt-1">
                  {t('model.service_env')}
                  {currentProvider.required_env_var
                    ? <code className="font-mono">{currentProvider.required_env_var}</code>
                    : <span>{t('model.not_required')}</span>}
                </div>
              )}
            </div>

            {/* Models */}
            <div className="grid grid-cols-2 gap-3">
              <ModelPicker
                label={t('model.deep_llm')}
                list={currentProvider?.deep_models ?? []}
                supportsCustom={currentProvider?.supports_custom_model ?? false}
                value={form.deep}
                customValue={form.deepCustom}
                onChange={(v, c) => setForm((f) => ({ ...f, deep: v, deepCustom: c ?? f.deepCustom }))}
              />
              <ModelPicker
                label={t('model.quick_llm')}
                list={currentProvider?.quick_models ?? []}
                supportsCustom={currentProvider?.supports_custom_model ?? false}
                value={form.quick}
                customValue={form.quickCustom}
                onChange={(v, c) => setForm((f) => ({ ...f, quick: v, quickCustom: c ?? f.quickCustom }))}
              />
            </div>

            {/* Backend URL */}
            <div>
              <label className="label">{t('model.backend_url')}</label>
              <input
                className="input"
                placeholder={currentProvider?.default_backend_url ?? ''}
                value={form.backendUrl}
                onChange={(e) => setForm((f) => ({ ...f, backendUrl: e.target.value }))}
                readOnly={!currentProvider?.backend_url_editable}
              />
              {!currentProvider?.backend_url_editable && (
                <div className="text-xs text-muted mt-1">{t('model.backend_fixed')}</div>
              )}
            </div>

            {/* API Key */}
            {needsKey ? (
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
            ) : (
              <Info>{t('model.no_api_key_needed')}</Info>
            )}

            {save.error && (
              <div className="text-sm text-danger">
                {(save.error as unknown as ApiError).status} · {(save.error as unknown as ApiError).detail}
              </div>
            )}
            {save.isSuccess && <div className="text-sm text-success">{t('common.saved')}</div>}

            <div className="flex justify-end">
              <button className="btn-primary" disabled={save.isPending || !buildPayload()}>
                {save.isPending ? t('model.saving') : t('common.save')}
              </button>
            </div>
          </form>
        </>
      )}
    </div>
  );
}

function ModelPicker(props: {
  label: string;
  list: ModelChoice[];
  supportsCustom: boolean;
  value: string;
  customValue: string;
  onChange: (value: string, customValue?: string) => void;
}) {
  const { label, list, supportsCustom, value, customValue, onChange } = props;
  const showCustom = value === CUSTOM;
  return (
    <div>
      <label className="label">{label}</label>
      <select
        className="input"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {list.map((m) => (
          <option key={m.id} value={m.id}>{m.label}</option>
        ))}
        {supportsCustom && <option value={CUSTOM}>{t('model.custom')}</option>}
      </select>
      {showCustom && (
        <input
          className="input mt-2 font-mono"
          placeholder={t('model.custom_placeholder')}
          value={customValue}
          onChange={(e) => onChange(CUSTOM, e.target.value)}
        />
      )}
    </div>
  );
}
