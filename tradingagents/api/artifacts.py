from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


@dataclass(frozen=True)
class ArtifactWrite:
    kind: str
    storage_backend: str
    storage_key: str
    content_type: str
    size_bytes: int
    sha256: str


class LocalArtifactStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def write_text(
        self,
        *,
        run_id: str,
        kind: str,
        relative_path: str,
        content: str,
        content_type: str,
    ) -> ArtifactWrite:
        data = content.encode("utf-8")
        return self._write_bytes(
            run_id=run_id,
            kind=kind,
            relative_path=relative_path,
            data=data,
            content_type=content_type,
        )

    def write_json(
        self,
        *,
        run_id: str,
        kind: str,
        relative_path: str,
        content: Any,
    ) -> ArtifactWrite:
        data = json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")
        return self._write_bytes(
            run_id=run_id,
            kind=kind,
            relative_path=relative_path,
            data=data,
            content_type="application/json",
        )

    def _write_bytes(
        self,
        *,
        run_id: str,
        kind: str,
        relative_path: str,
        data: bytes,
        content_type: str,
    ) -> ArtifactWrite:
        storage_key = self._storage_key(run_id, relative_path)
        destination = self.root / storage_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return ArtifactWrite(
            kind=kind,
            storage_backend="local",
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    @staticmethod
    def _storage_key(run_id: str, relative_path: str) -> str:
        rel = PurePosixPath(relative_path)
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError("artifact relative_path must stay under the run directory")
        return str(PurePosixPath(run_id) / rel)
