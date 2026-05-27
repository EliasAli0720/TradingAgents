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
};
