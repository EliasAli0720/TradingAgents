import { http } from './client';

export type ModelSettings = {
  llm_provider: string;
  deep_think_llm: string;
  quick_think_llm: string;
  backend_url: string | null;
  has_api_key: boolean;
  api_key_masked: string | null;
};

export type ModelSettingsInput = {
  llm_provider: string;
  deep_think_llm: string;
  quick_think_llm: string;
  backend_url?: string | null;
  api_key?: string | null;
};

export type ValidateResult = {
  valid: boolean;
  provider: string;
  required_env_var: string | null;
  api_key_source: 'user' | 'service' | 'none' | 'not_required';
  message: string;
  probe_status?:
    | 'success'
    | 'invalid_api_key'
    | 'model_not_found'
    | 'endpoint_unreachable'
    | 'permission_denied'
    | 'timeout'
    | 'provider_error';
  probe_message?: string;
};

export type ModelChoice = { id: string; label: string };

export type ProviderOption = {
  id: string;
  label: string;
  required_env_var: string | null;
  default_backend_url: string | null;
  backend_url_editable: boolean;
  supports_custom_model: boolean;
  quick_models: ModelChoice[];
  deep_models: ModelChoice[];
};

export type ModelOptions = { providers: ProviderOption[] };

export type TranslationSettings = {
  llm_provider: string;
  model: string;
  backend_url: string | null;
  has_api_key: boolean;
  api_key_masked: string | null;
};

export type TranslationSettingsInput = {
  llm_provider: string;
  model: string;
  backend_url?: string | null;
  api_key?: string | null;
};

export type TranslationProviderOption = {
  id: string;
  label: string;
  model_id: string;
  model_label: string;
  required_env_var: string | null;
  default_backend_url: string | null;
  backend_url_editable: boolean;
};

export type TranslationOptions = { providers: TranslationProviderOption[] };

export const settingsApi = {
  async options(): Promise<ModelOptions> {
    const { data } = await http.get<ModelOptions>('/settings/model/options');
    return data;
  },
  async get(): Promise<ModelSettings> {
    const { data } = await http.get<ModelSettings>('/settings/model');
    return data;
  },
  async put(input: ModelSettingsInput): Promise<ModelSettings> {
    const { data } = await http.put<ModelSettings>('/settings/model', input);
    return data;
  },
  async clearKey(): Promise<void> {
    await http.delete('/settings/model/api-key');
  },
  async validate(): Promise<ValidateResult> {
    const { data } = await http.post<ValidateResult>('/settings/model/validate');
    return data;
  },

  // ── Dedicated translation model ──
  async translationOptions(): Promise<TranslationOptions> {
    const { data } = await http.get<TranslationOptions>('/settings/translation/options');
    return data;
  },
  async translationGet(): Promise<TranslationSettings> {
    const { data } = await http.get<TranslationSettings>('/settings/translation');
    return data;
  },
  async translationPut(input: TranslationSettingsInput): Promise<TranslationSettings> {
    const { data } = await http.put<TranslationSettings>('/settings/translation', input);
    return data;
  },
  async translationClearKey(): Promise<void> {
    await http.delete('/settings/translation/api-key');
  },
  async translationValidate(): Promise<ValidateResult> {
    const { data } = await http.post<ValidateResult>('/settings/translation/validate');
    return data;
  },
};
