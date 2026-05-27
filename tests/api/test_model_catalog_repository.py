from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.model_catalog_repository import LLMModelCatalogRepository
from tradingagents.api.models import LLMModelOption, LLMProviderOption


def test_model_catalog_repository_seeds_provider_and_model_options():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        LLMModelCatalogRepository(session).ensure_seeded()
        session.commit()

    with Session() as session:
        openai = session.get(LLMProviderOption, "openai")
        assert openai is not None
        assert openai.required_env_var == "OPENAI_API_KEY"
        assert openai.supports_custom_model is False

        ollama = session.get(LLMProviderOption, "ollama")
        assert ollama is not None
        assert ollama.default_backend_url == "http://localhost:11434/v1"
        assert ollama.supports_custom_model is True

        minimax_cn = session.get(LLMProviderOption, "minimax-cn")
        assert minimax_cn is not None
        assert minimax_cn.default_backend_url == "https://api.minimaxi.com/v1"

        quick_openai_models = session.scalars(
            select(LLMModelOption.model_id)
            .where(
                LLMModelOption.provider_id == "openai",
                LLMModelOption.mode == "quick",
            )
            .order_by(LLMModelOption.sort_order)
        ).all()
        assert quick_openai_models[0] == "gpt-5.4-mini"


def test_model_catalog_repository_refreshes_existing_provider_metadata():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)

    with Session() as session:
        session.add(
            LLMProviderOption(
                provider_id="minimax-cn",
                label="Old MiniMax",
                required_env_var="OLD_KEY",
                default_backend_url="https://api.minimaxi.com/anthropic",
                backend_url_editable=False,
                supports_custom_model=False,
                sort_order=99,
            )
        )
        session.commit()

    with Session() as session:
        LLMModelCatalogRepository(session).ensure_seeded()
        session.commit()

    with Session() as session:
        minimax_cn = session.get(LLMProviderOption, "minimax-cn")
        assert minimax_cn is not None
        assert minimax_cn.label == "MiniMax China"
        assert minimax_cn.required_env_var == "MINIMAX_CN_API_KEY"
        assert minimax_cn.default_backend_url == "https://api.minimaxi.com/v1"
