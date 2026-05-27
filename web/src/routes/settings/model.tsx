import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { settingsApi, type ModelSettingsInput } from '@/api/settings';
import type { ApiError } from '@/api/client';
import { Subheader, Caption, Info } from '@/components/ui/Page';

const PROVIDERS = [
  'openai', 'anthropic', 'google', 'azure', 'xai', 'deepseek',
  'qwen', 'qwen-cn', 'glm', 'glm-cn', 'minimax', 'minimax-cn',
  'openrouter', 'ollama',
];

type Form = ModelSettingsInput;

export default function ModelSettingsPage() {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ['settings', 'model'],
    queryFn: () => settingsApi.get().catch((e) => {
      if ((e as ApiError).status === 404) return null;
      throw e;
    }),
  });

  const { register, handleSubmit, reset } = useForm<Form>({
    defaultValues: {
      llm_provider: 'openai',
      deep_think_llm: 'gpt-4.1',
      quick_think_llm: 'gpt-4.1-mini',
      backend_url: 'https://api.openai.com/v1',
      api_key: '',
    },
  });

  useEffect(() => {
    if (q.data) {
      reset({
        llm_provider: q.data.llm_provider,
        deep_think_llm: q.data.deep_think_llm,
        quick_think_llm: q.data.quick_think_llm,
        backend_url: q.data.backend_url ?? '',
        api_key: '',
      });
    }
  }, [q.data, reset]);

  const save = useMutation({
    mutationFn: (v: Form) => {
      const payload: ModelSettingsInput = { ...v };
      if (!payload.api_key) delete payload.api_key;
      if (!payload.backend_url) payload.backend_url = null;
      return settingsApi.put(payload);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'model'] }),
  });

  const clearKey = useMutation({
    mutationFn: () => settingsApi.clearKey(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['settings', 'model'] }),
  });

  const validate = useMutation({ mutationFn: () => settingsApi.validate() });

  return (
    <div className="max-w-2xl">
      <Subheader>模型设置</Subheader>
      <Caption>用户自有 API key 优先；未保存时回退服务端环境变量。</Caption>

      {q.data && (
        <div className="card flex items-center justify-between mb-4">
          <div className="text-sm">
            当前 key：
            {q.data.has_api_key
              ? <span className="font-mono">{q.data.api_key_masked}</span>
              : <span className="text-muted">未设置（回退服务端 env）</span>}
          </div>
          <div className="flex gap-2">
            <button className="btn-ghost" disabled={validate.isPending} onClick={() => validate.mutate()}>
              {validate.isPending ? '校验中…' : '校验密钥'}
            </button>
            <button className="btn-danger" disabled={!q.data.has_api_key || clearKey.isPending} onClick={() => clearKey.mutate()}>
              清空 key
            </button>
          </div>
        </div>
      )}

      {validate.data && (
        <Info>
          valid: <b>{String(validate.data.valid)}</b> · source: {validate.data.api_key_source}
          <div className="text-muted mt-1">{validate.data.message}</div>
        </Info>
      )}

      <form className="card space-y-3 mt-4" onSubmit={handleSubmit((v) => save.mutate(v))}>
        <div>
          <label className="label">Provider</label>
          <select className="input" {...register('llm_provider')}>
            {PROVIDERS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Deep think LLM</label>
            <input className="input" {...register('deep_think_llm', { required: true })} />
          </div>
          <div>
            <label className="label">Quick think LLM</label>
            <input className="input" {...register('quick_think_llm', { required: true })} />
          </div>
        </div>
        <div>
          <label className="label">Backend URL（可选）</label>
          <input className="input" placeholder="https://api.openai.com/v1" {...register('backend_url')} />
        </div>
        <div>
          <label className="label">API Key（留空则保留当前 key）</label>
          <input className="input" type="password" placeholder="sk-..." {...register('api_key')} />
        </div>

        {save.error && (
          <div className="text-sm text-danger">
            {(save.error as unknown as ApiError).status} · {(save.error as unknown as ApiError).detail}
          </div>
        )}
        {save.isSuccess && <div className="text-sm text-success">已保存</div>}

        <div className="flex justify-end">
          <button className="btn-primary" disabled={save.isPending}>保存</button>
        </div>
      </form>
    </div>
  );
}
