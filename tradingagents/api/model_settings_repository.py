from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

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
    ) -> UserModelSetting:
        now = utcnow()
        settings = self.get(user_id)
        if settings is None:
            settings = UserModelSetting(
                user_id=user_id,
                llm_provider=llm_provider,
                deep_think_llm=deep_think_llm,
                quick_think_llm=quick_think_llm,
                backend_url=backend_url,
                created_at=now,
                updated_at=now,
            )
            self.session.add(settings)
            return settings

        settings.llm_provider = llm_provider
        settings.deep_think_llm = deep_think_llm
        settings.quick_think_llm = quick_think_llm
        settings.backend_url = backend_url
        settings.updated_at = now
        return settings

    def snapshot(self, user_id: str) -> Optional[dict[str, str | None]]:
        settings = self.get(user_id)
        if settings is None:
            return None
        return {
            "llm_provider": settings.llm_provider,
            "deep_think_llm": settings.deep_think_llm,
            "quick_think_llm": settings.quick_think_llm,
            "backend_url": settings.backend_url,
        }
