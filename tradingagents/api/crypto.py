from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from tradingagents.api.config import get_api_settings


def _fernet() -> Fernet:
    key = get_api_settings().model_api_key_encryption_key
    if not key:
        raise RuntimeError(
            "MODEL_API_KEY_ENCRYPTION_KEY is required to store model API keys. "
            "Generate one with: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(key.encode("utf-8"))
    except ValueError as exc:
        raise RuntimeError("MODEL_API_KEY_ENCRYPTION_KEY must be a valid Fernet key") from exc


def encrypt_secret(secret: str) -> str:
    value = secret.strip()
    if not value:
        raise ValueError("secret cannot be empty")
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise RuntimeError("encrypted model API key cannot be decrypted") from exc


def mask_secret(secret: str) -> str:
    if len(secret) < 12:
        return "****"
    return f"{secret[:4]}...{secret[-4:]}"
