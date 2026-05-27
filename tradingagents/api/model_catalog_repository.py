from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from tradingagents.api.models import LLMModelOption, LLMProviderOption
from tradingagents.llm_clients.api_key_env import get_api_key_env
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS


@dataclass(frozen=True)
class ProviderSeed:
    provider_id: str
    label: str
    default_backend_url: str | None
    backend_url_editable: bool = False


PROVIDER_SEEDS = [
    # openai: official endpoint per developers.openai.com/api/docs.
    # langchain_openai.ChatOpenAI defaults to this when base_url is None,
    # but seeding it makes the value visible in the SPA settings UI.
    ProviderSeed("openai", "OpenAI", "https://api.openai.com/v1"),
    # google: Gemini Developer API endpoint per ai.google.dev/api.
    # Honored by langchain_google_genai when base_url is passed through.
    ProviderSeed("google", "Google", "https://generativelanguage.googleapis.com/v1beta"),
    # anthropic: official default per langchain_anthropic.ChatAnthropic
    # (anthropic_api_url alias 'base_url'). No /v1 suffix — the Anthropic
    # SDK appends versioned paths itself.
    ProviderSeed("anthropic", "Anthropic", "https://api.anthropic.com"),
    ProviderSeed("xai", "xAI", "https://api.x.ai/v1"),
    ProviderSeed("deepseek", "DeepSeek", "https://api.deepseek.com"),
    ProviderSeed("qwen", "Qwen International", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    ProviderSeed("qwen-cn", "Qwen China", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    ProviderSeed("glm", "GLM Z.AI", "https://api.z.ai/api/paas/v4/"),
    ProviderSeed("glm-cn", "GLM BigModel China", "https://open.bigmodel.cn/api/paas/v4/"),
    ProviderSeed("minimax", "MiniMax Global", "https://api.minimax.io/v1"),
    ProviderSeed("minimax-cn", "MiniMax China", "https://api.minimaxi.com/v1"),
    ProviderSeed("openrouter", "OpenRouter", "https://openrouter.ai/api/v1", True),
    # azure: per-customer deployment URL, no universal default; user must
    # supply it themselves, hence editable=True.
    ProviderSeed("azure", "Azure OpenAI", None, True),
    ProviderSeed("ollama", "Ollama", "http://localhost:11434/v1", True),
]

CUSTOM_MODEL_PROVIDERS = {"azure", "openrouter"}


class LLMModelCatalogRepository:
    def __init__(self, session: Session):
        self.session = session
        self._seeded = False

    def ensure_seeded(self) -> None:
        """Sync the DB-backed model catalog from application defaults.

        Runs once per repository instance (caller boundary = HTTP request).
        Provider rows are upserted; model option rows are fully rebuilt
        from MODEL_OPTIONS so edits to the Python catalog propagate on
        the next process start without one-off SQL migrations.
        """
        if self._seeded:
            return
        provider_rows = {
            row.provider_id: row
            for row in self.session.scalars(select(LLMProviderOption)).all()
        }

        for sort_order, seed in enumerate(PROVIDER_SEEDS):
            supports_custom_model = (
                seed.provider_id in CUSTOM_MODEL_PROVIDERS
                or _catalog_has_custom_model(seed.provider_id)
            )
            row = provider_rows.get(seed.provider_id)
            if row is None:
                row = LLMProviderOption(provider_id=seed.provider_id)
                self.session.add(row)
            row.label = seed.label
            row.required_env_var = get_api_key_env(seed.provider_id)
            row.default_backend_url = seed.default_backend_url
            row.backend_url_editable = seed.backend_url_editable
            row.supports_custom_model = supports_custom_model
            row.sort_order = sort_order

        self.session.flush()

        # Rebuild model_options to match the current Python catalog. Cheap
        # (~70 inserts across all providers) and means dropping or renaming
        # a model in MODEL_OPTIONS takes effect on the next API start
        # rather than requiring a hand-written SQL migration each time.
        for seed in PROVIDER_SEEDS:
            self.session.execute(
                delete(LLMModelOption).where(LLMModelOption.provider_id == seed.provider_id)
            )
            for mode in ("quick", "deep"):
                for model_order, (label, model_id) in enumerate(
                    MODEL_OPTIONS.get(seed.provider_id, {}).get(mode, [])
                ):
                    if model_id == "custom":
                        continue
                    self.session.add(
                        LLMModelOption(
                            provider_id=seed.provider_id,
                            mode=mode,
                            model_id=model_id,
                            label=label,
                            sort_order=model_order,
                        )
                    )
        self.session.flush()
        self._seeded = True

    def list_provider_options(self) -> list[LLMProviderOption]:
        self.ensure_seeded()
        return list(
            self.session.scalars(
                select(LLMProviderOption).order_by(LLMProviderOption.sort_order)
            ).all()
        )

    def list_model_options(self, provider_id: str, mode: str) -> list[LLMModelOption]:
        self.ensure_seeded()
        return list(
            self.session.scalars(
                select(LLMModelOption)
                .where(
                    LLMModelOption.provider_id == provider_id,
                    LLMModelOption.mode == mode,
                )
                .order_by(LLMModelOption.sort_order)
            ).all()
        )

    def validate_model_settings(
        self,
        provider_id: str,
        quick_model: str,
        deep_model: str,
    ) -> str | None:
        self.ensure_seeded()
        provider = self.session.get(LLMProviderOption, provider_id)
        if provider is None:
            return f"unsupported llm_provider {provider_id}"
        if provider.supports_custom_model:
            return None
        if not self._model_exists(provider_id, "quick", quick_model):
            return f"unsupported quick_think_llm for provider {provider_id}"
        if not self._model_exists(provider_id, "deep", deep_model):
            return f"unsupported deep_think_llm for provider {provider_id}"
        return None

    def _model_exists(self, provider_id: str, mode: str, model_id: str) -> bool:
        return (
            self.session.scalar(
                select(LLMModelOption.id).where(
                    LLMModelOption.provider_id == provider_id,
                    LLMModelOption.mode == mode,
                    LLMModelOption.model_id == model_id,
                )
            )
            is not None
        )


def _catalog_has_custom_model(provider_id: str) -> bool:
    return any(
        model_id == "custom"
        for options in MODEL_OPTIONS.get(provider_id, {}).values()
        for _, model_id in options
    )
