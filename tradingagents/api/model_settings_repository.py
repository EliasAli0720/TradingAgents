from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from tradingagents.api.crypto import decrypt_secret, encrypt_secret, mask_secret
from tradingagents.api.models import UserModelSetting
from tradingagents.api.repositories import utcnow


class UserModelSettingsRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, user_id: str) -> Optional[UserModelSetting]:
        return self.session.get(UserModelSetting, user_id)

    def upsert(
        self,
        user_id: str,
        llm_provider: str,
        deep_think_llm: str,
        quick_think_llm: str,
        backend_url: Optional[str],
        api_key: Optional[str] = None,
    ) -> UserModelSetting:
        now = utcnow()
        if llm_provider == "google":
            backend_url = None
        encrypted_api_key = encrypt_secret(api_key) if api_key else None
        settings = self.get(user_id)
        if settings is None:
            settings = UserModelSetting(
                user_id=user_id,
                llm_provider=llm_provider,
                deep_think_llm=deep_think_llm,
                quick_think_llm=quick_think_llm,
                backend_url=backend_url,
                encrypted_api_key=encrypted_api_key,
                created_at=now,
                updated_at=now,
            )
            self.session.add(settings)
            return settings

        settings.llm_provider = llm_provider
        settings.deep_think_llm = deep_think_llm
        settings.quick_think_llm = quick_think_llm
        settings.backend_url = backend_url
        if encrypted_api_key is not None:
            settings.encrypted_api_key = encrypted_api_key
        settings.updated_at = now
        return settings

    def clear_api_key(self, user_id: str) -> Optional[UserModelSetting]:
        settings = self.get(user_id)
        if settings is None:
            return None
        settings.encrypted_api_key = None
        settings.updated_at = utcnow()
        return settings

    def api_key_metadata(self, settings: UserModelSetting) -> dict[str, str | bool | None]:
        if not settings.encrypted_api_key:
            return {"has_api_key": False, "api_key_masked": None}
        return {
            "has_api_key": True,
            "api_key_masked": mask_secret(decrypt_secret(settings.encrypted_api_key)),
        }

    def snapshot(self, user_id: str) -> Optional[dict[str, str | None]]:
        settings = self.get(user_id)
        if settings is None:
            return None
        return {
            "llm_provider": settings.llm_provider,
            "deep_think_llm": settings.deep_think_llm,
            "quick_think_llm": settings.quick_think_llm,
            "backend_url": settings.backend_url,
            "api_key_encrypted": settings.encrypted_api_key,
        }
