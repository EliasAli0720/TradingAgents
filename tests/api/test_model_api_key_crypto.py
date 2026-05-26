import pytest

from tradingagents.api.crypto import decrypt_secret, encrypt_secret, mask_secret


FERNET_KEY = "dBBj0g2y16HOVnBCwG9r20eyHmxtPXgvBXVHfJfRB4U="


def test_encrypt_secret_round_trips_without_plaintext(monkeypatch):
    monkeypatch.setenv("MODEL_API_KEY_ENCRYPTION_KEY", FERNET_KEY)

    token = encrypt_secret("sk-test-abcdef123456")

    assert "sk-test" not in token
    assert decrypt_secret(token) == "sk-test-abcdef123456"


def test_encrypt_secret_requires_configured_key(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY_ENCRYPTION_KEY", raising=False)

    with pytest.raises(RuntimeError, match="MODEL_API_KEY_ENCRYPTION_KEY"):
        encrypt_secret("sk-test-abcdef123456")


def test_mask_secret_keeps_only_prefix_and_suffix():
    assert mask_secret("sk-test-abcdef123456") == "sk-t...3456"
    assert mask_secret("short") == "****"
