from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends

from tradingagents.api.config import ApiConfig
from tradingagents.api.deps import get_config, require_auth

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def list_reports(_: str = Depends(require_auth), config: ApiConfig = Depends(get_config)) -> dict:
    root = Path(config.results_dir)
    reports = []
    if root.exists():
        for path in root.glob("**/complete_report.md"):
            reports.append({"id": str(path.relative_to(root)), "path": str(path)})
    return {"reports": reports}
