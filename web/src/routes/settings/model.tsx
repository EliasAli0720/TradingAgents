import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { settingsApi, type ModelSettingsInput, type ProviderOption, type ModelChoice } from '@/api/settings';
import type { ApiError } from '@/api/client';
import { Subheader, Caption, Info } from '@/components/ui/Page';

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
      <Subheader>模型设置</Subheader>
      <Caption>从后端支持的列表中选择 provider 与模型；不填 API key 时优先用已保存的或服务端环境变量。</Caption>

      {options.isLoading || current.isLoading || !initialized ? (
        <div className="text-muted text-sm">加载中…</div>
      ) : options.error || !options.data ? (
        <Info>加载 provider 列表失败。</Info>
      ) : (
        <>
          {/* Current key state */}
          <div className="card flex items-center justify-between mb-4">
            <div className="text-sm">
              当前 key：
              {current.data?.has_api_key
                ? <span className="font-mono">{current.data.api_key_masked}</span>
                : <span className="text-muted">未设置（回退服务端 env）</span>}
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                className="btn-ghost"
                disabled={validate.isPending || !current.data}
                onClick={() => validate.mutate()}
              >
                {validate.isPending ? '校验中…' : '校验密钥'}
              </button>
              <button
                type="button"
                className="btn-danger"
                disabled={!current.data?.has_api_key || clearKey.isPending}
                onClick={() => clearKey.mutate()}
              >
                清空 key
              </button>
            </div>
          </div>

          {validate.data && (
            <Info>
              valid: <b>{String(validate.data.valid)}</b> · source: {validate.data.api_key_source}
              <div className="text-muted mt-1">{validate.data.message}</div>
            </Info>
          )}

          <form className="card space-y-4 mt-4" onSubmit={onSubmit}>
            {/* Provider */}
            <div>
              <label className="label">Provider</label>
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
                  服务端兜底环境变量：
                  {currentProvider.required_env_var
                    ? <code className="font-mono">{currentProvider.required_env_var}</code>
                    : <span>不需要</span>}
                </div>
              )}
            </div>

            {/* Models */}
            <div className="grid grid-cols-2 gap-3">
              <ModelPicker
                label="Deep think LLM"
                list={currentProvider?.deep_models ?? []}
                supportsCustom={currentProvider?.supports_custom_model ?? false}
                value={form.deep}
                customValue={form.deepCustom}
                onChange={(v, c) => setForm((f) => ({ ...f, deep: v, deepCustom: c ?? f.deepCustom }))}
              />
              <ModelPicker
                label="Quick think LLM"
                list={currentProvider?.quick_models ?? []}
                supportsCustom={currentProvider?.supports_custom_model ?? false}
                value={form.quick}
                customValue={form.quickCustom}
                onChange={(v, c) => setForm((f) => ({ ...f, quick: v, quickCustom: c ?? f.quickCustom }))}
              />
            </div>

            {/* Backend URL */}
            <div>
              <label className="label">Backend URL</label>
              <input
                className="input"
                placeholder={currentProvider?.default_backend_url ?? ''}
                value={form.backendUrl}
                onChange={(e) => setForm((f) => ({ ...f, backendUrl: e.target.value }))}
                readOnly={!currentProvider?.backend_url_editable}
              />
              {!currentProvider?.backend_url_editable && (
                <div className="text-xs text-muted mt-1">该 provider 的 backend URL 由服务端固定。</div>
              )}
            </div>

            {/* API Key */}
            {needsKey ? (
              <div>
                <label className="label">API Key（留空则保留当前 key）</label>
                <input
                  className="input"
                  type="password"
                  placeholder={current.data?.has_api_key ? '•••••• 已保存，留空保留' : 'sk-...'}
                  value={form.apiKey}
                  onChange={(e) => setForm((f) => ({ ...f, apiKey: e.target.value }))}
                  autoComplete="new-password"
                />
              </div>
            ) : (
              <Info>该 provider 不需要 API key。</Info>
            )}

            {save.error && (
              <div className="text-sm text-danger">
                {(save.error as unknown as ApiError).status} · {(save.error as unknown as ApiError).detail}
              </div>
            )}
            {save.isSuccess && <div className="text-sm text-success">已保存</div>}

            <div className="flex justify-end">
              <button className="btn-primary" disabled={save.isPending || !buildPayload()}>
                {save.isPending ? '保存中…' : '保存'}
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
        {supportsCustom && <option value={CUSTOM}>自定义…</option>}
      </select>
      {showCustom && (
        <input
          className="input mt-2 font-mono"
          placeholder="输入模型 ID"
          value={customValue}
          onChange={(e) => onChange(CUSTOM, e.target.value)}
        />
      )}
    </div>
  );
}
