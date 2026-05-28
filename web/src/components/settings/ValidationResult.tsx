// Shared validation-result display for model + translation settings pages,
// so both render the same probe-status cards instead of diverging.
import type { ValidateResult } from '@/api/settings';
import type { ApiError } from '@/api/client';
import { t } from '@/i18n';

export function ValidationResultCard({
  result,
  providerLabel,
  modelId,
}: {
  result: ValidateResult;
  providerLabel?: string;
  modelId?: string;
}) {
  const success = result.valid && result.probe_status === 'success';
  const copy = validationCopy(result);
  const source = apiKeySourceLabel(result.api_key_source, result.required_env_var);
  const provider = providerLabel ?? result.provider;

  return (
    <div className={`card text-sm mb-4 border-l-4 ${success ? 'border-l-success' : 'border-l-danger'}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className={`font-semibold ${success ? 'text-success' : 'text-danger'}`}>
            {success ? t('model.connection_success') : t('model.connection_failed')}
          </div>
          <div className="mt-1 text-text">{copy.title}</div>
        </div>
        <span className={`badge shrink-0 ${success ? 'bg-successBg text-success' : 'bg-dangerBg text-danger'}`}>
          {success ? t('model.available') : t('model.needs_action')}
        </span>
      </div>

      <div className="mt-3 grid gap-2 text-xs text-muted sm:grid-cols-2">
        <div>
          {t('model.provider')}: <span className="text-text">{provider}</span>
        </div>
        {modelId && (
          <div>
            {t('model.probe_model')}<code className="font-mono text-text">{modelId}</code>
          </div>
        )}
        <div className="sm:col-span-2">
          {t('model.key_source')}<span className="text-text">{source}</span>
        </div>
      </div>

      <div className="mt-3 text-xs text-muted">{copy.detail}</div>
      {result.probe_message && result.probe_message !== copy.detail && (
        <div className="mt-2 rounded border border-border bg-bg p-2 text-xs text-muted">
          {t('model.technical_detail', { detail: result.probe_message })}
        </div>
      )}
    </div>
  );
}

export function ValidationErrorCard({ error }: { error: ApiError }) {
  return (
    <div className="card text-sm mb-4 border-l-4 border-l-danger">
      <div className="font-semibold text-danger">{t('model.request_failed')}</div>
      <div className="mt-1 text-text">{t('model.request_failed_desc')}</div>
      <div className="mt-2 text-xs text-muted">HTTP {error.status}：{String(error.detail)}</div>
    </div>
  );
}

function validationCopy(result: ValidateResult): { title: string; detail: string } {
  if (!result.probe_status) {
    if (result.api_key_source === 'none') {
      return {
        title: t('model.missing_key_title'),
        detail: result.required_env_var
          ? t('model.missing_key_detail', { envVar: result.required_env_var })
          : result.message,
      };
    }
    return {
      title: result.valid ? t('model.config_passed') : t('model.config_failed'),
      detail: result.message,
    };
  }

  switch (result.probe_status) {
    case 'success':
      return { title: t('model.probe_success_title'), detail: t('model.probe_success_detail') };
    case 'invalid_api_key':
      return { title: t('model.invalid_key_title'), detail: t('model.invalid_key_detail') };
    case 'model_not_found':
      return { title: t('model.model_not_found_title'), detail: t('model.model_not_found_detail') };
    case 'endpoint_unreachable':
      return { title: t('model.endpoint_unreachable_title'), detail: t('model.endpoint_unreachable_detail') };
    case 'permission_denied':
      return { title: t('model.permission_denied_title'), detail: t('model.permission_denied_detail') };
    case 'timeout':
      return { title: t('model.timeout_title'), detail: t('model.timeout_detail') };
    case 'provider_error':
      return { title: t('model.provider_error_title'), detail: t('model.provider_error_detail') };
    default:
      return { title: result.message, detail: result.message };
  }
}

function apiKeySourceLabel(source: ValidateResult['api_key_source'], envVar: string | null): string {
  switch (source) {
    case 'user':
      return t('model.key_source.user');
    case 'service':
      return envVar ? t('model.key_source.service', { envVar }) : t('model.key_source.service_generic');
    case 'not_required':
      return t('model.key_source.not_required');
    case 'none':
      return t('model.key_source.none');
    default:
      return source;
  }
}
