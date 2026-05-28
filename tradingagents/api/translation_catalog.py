from __future__ import annotations

from dataclasses import dataclass

from tradingagents.llm_clients.api_key_env import get_api_key_env


@dataclass(frozen=True)
class TranslationProviderOption:
    provider_id: str
    label: str
    model_id: str
    model_label: str
    default_backend_url: str | None
    backend_url_editable: bool = False

    @property
    def required_env_var(self) -> str | None:
        return get_api_key_env(self.provider_id)


# Curated short list of models offered for the dedicated translation model.
# Intentionally smaller than the analysis catalog — translation is a
# mechanical task, so we expose a few cheap/capable options across providers.
TRANSLATION_PROVIDERS: list[TranslationProviderOption] = [
    TranslationProviderOption(
        provider_id="openai",
        label="OpenAI",
        model_id="gpt-4o-mini",
        model_label="GPT-4o mini",
        default_backend_url="https://api.openai.com/v1",
    ),
    TranslationProviderOption(
        provider_id="deepseek",
        # Official DeepSeek API exposes V3 via the model id "deepseek-chat"
        # (now backed by V3.2). There is no "deepseek-v3" id. OpenAI-compatible
        # endpoint; the SDK appends /chat/completions to this base.
        label="DeepSeek",
        model_id="deepseek-chat",
        model_label="DeepSeek V3.2 (deepseek-chat)",
        default_backend_url="https://api.deepseek.com",
    ),
    TranslationProviderOption(
        provider_id="google",
        # Native Gemini Developer API via langchain_google_genai. Leave the
        # base URL empty: the SDK targets generativelanguage.googleapis.com and
        # appends /v1beta/models/... itself. Passing a /v1beta-suffixed URL
        # double-prefixes the path and 404s.
        label="Google",
        model_id="gemini-2.5-pro",
        model_label="Gemini 2.5 Pro",
        default_backend_url=None,
    ),
]

_BY_PROVIDER = {opt.provider_id: opt for opt in TRANSLATION_PROVIDERS}


def get_translation_provider(provider_id: str) -> TranslationProviderOption | None:
    return _BY_PROVIDER.get(provider_id)


def validate_translation_settings(provider_id: str, model: str) -> str | None:
    """Return an error message if (provider, model) is not an allowed combo."""
    option = _BY_PROVIDER.get(provider_id)
    if option is None:
        return f"unsupported translation provider {provider_id}"
    if model != option.model_id:
        return f"unsupported translation model {model} for provider {provider_id}"
    return None
