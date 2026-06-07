from sqlalchemy.orm import sessionmaker

from tradingagents.api.db import Base, create_db_engine
from tradingagents.api.model_settings_repository import UserModelSettingsRepository
from tradingagents.api.models import User
from tradingagents.api.repositories import utcnow


FERNET_KEY = "dBBj0g2y16HOVnBCwG9r20eyHmxtPXgvBXVHfJfRB4U="


def _session():
    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def _user(user_id: str = "usr_1") -> User:
    return User(
        user_id=user_id,
        username=user_id,
        password_hash="scrypt$placeholder",
        role="operator",
        is_active=True,
        created_at=utcnow(),
    )


def test_user_model_settings_repository_upserts_and_reads_settings():
    session = _session()
    session.add(_user())
    repo = UserModelSettingsRepository(session)

    settings = repo.upsert(
        user_id="usr_1",
        llm_provider="openai",
        deep_think_llm="gpt-5.4",
        quick_think_llm="gpt-5.4-mini",
        backend_url=None,
    )
    session.commit()

    saved = repo.get("usr_1")
    assert saved is settings
    assert saved.llm_provider == "openai"
    assert saved.deep_think_llm == "gpt-5.4"
    assert saved.quick_think_llm == "gpt-5.4-mini"
    assert saved.backend_url is None

    repo.upsert(
        user_id="usr_1",
        llm_provider="anthropic",
        deep_think_llm="claude-opus-4-7",
        quick_think_llm="claude-haiku-4-5",
        backend_url="https://llm.example.com",
    )
    session.commit()

    updated = repo.get("usr_1")
    assert updated.llm_provider == "anthropic"
    assert updated.deep_think_llm == "claude-opus-4-7"
    assert updated.quick_think_llm == "claude-haiku-4-5"
    assert updated.backend_url == "https://llm.example.com"
    assert updated.updated_at >= updated.created_at


def test_user_model_settings_repository_snapshot_is_plain_json():
    session = _session()
    session.add(_user())
    repo = UserModelSettingsRepository(session)
    repo.upsert(
        user_id="usr_1",
        llm_provider="ollama",
        deep_think_llm="gpt-oss:latest",
        quick_think_llm="qwen3:latest",
        backend_url="http://localhost:11434/v1",
    )
    session.commit()

    assert repo.snapshot("usr_1") == {
        "llm_provider": "ollama",
        "deep_think_llm": "gpt-oss:latest",
        "quick_think_llm": "qwen3:latest",
        "backend_url": "http://localhost:11434/v1",
        "api_key_encrypted": None,
    }
    assert repo.snapshot("missing") is None


def test_user_model_settings_repository_encrypts_masks_and_snapshots_api_key(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    session = _session()
    session.add(_user())
    repo = UserModelSettingsRepository(session)

    settings = repo.upsert(
        user_id="usr_1",
        llm_provider="openai",
        deep_think_llm="gpt-5.4",
        quick_think_llm="gpt-5.4-mini",
        backend_url=None,
        api_key="sk-test-abcdef123456",
    )
    session.commit()

    assert settings.encrypted_api_key is not None
    assert "sk-test" not in settings.encrypted_api_key
    assert repo.api_key_metadata(settings) == {
        "has_api_key": True,
        "api_key_masked": "sk-t...3456",
    }
    snapshot = repo.snapshot("usr_1")
    assert snapshot["api_key_encrypted"] == settings.encrypted_api_key
    assert "sk-test" not in snapshot["api_key_encrypted"]


def test_user_model_settings_repository_preserves_replaces_and_clears_api_key(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    session = _session()
    session.add(_user())
    repo = UserModelSettingsRepository(session)

    first = repo.upsert(
        user_id="usr_1",
        llm_provider="openai",
        deep_think_llm="gpt-5.4",
        quick_think_llm="gpt-5.4-mini",
        backend_url=None,
        api_key="sk-first-abcdef123456",
    )
    first_token = first.encrypted_api_key
    repo.upsert(
        user_id="usr_1",
        llm_provider="openai",
        deep_think_llm="gpt-5.4",
        quick_think_llm="gpt-5.4-mini",
        backend_url=None,
    )
    assert repo.get("usr_1").encrypted_api_key == first_token

    repo.upsert(
        user_id="usr_1",
        llm_provider="openai",
        deep_think_llm="gpt-5.4",
        quick_think_llm="gpt-5.4-mini",
        backend_url=None,
        api_key="sk-second-abcdef123456",
    )
    assert repo.get("usr_1").encrypted_api_key != first_token

    repo.clear_api_key("usr_1")
    assert repo.get("usr_1").encrypted_api_key is None
    assert repo.api_key_metadata(repo.get("usr_1")) == {
        "has_api_key": False,
        "api_key_masked": None,
    }


def test_user_model_settings_repository_clears_api_key_when_provider_changes(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)
    session = _session()
    session.add(_user())
    repo = UserModelSettingsRepository(session)

    repo.upsert(
        user_id="usr_1",
        llm_provider="openai",
        deep_think_llm="gpt-5.4",
        quick_think_llm="gpt-5.4-mini",
        backend_url=None,
        api_key="sk-openai-abcdef123456",
    )

    repo.upsert(
        user_id="usr_1",
        llm_provider="anthropic",
        deep_think_llm="claude-opus-4-7",
        quick_think_llm="claude-haiku-4-5",
        backend_url=None,
    )

    assert repo.get("usr_1").encrypted_api_key is None
