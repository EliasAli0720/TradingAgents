"""One-off: translate an existing report Markdown with the user's configured
translation model, writing a new file with the model name in its filename.

Usage: python scripts/translate_report_once.py <user_id> <path-to-report.md> [zh|en]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from tradingagents.api.db import SessionLocal  # noqa: E402
from tradingagents.api.translation_settings_repository import (  # noqa: E402
    UserTranslationSettingsRepository,
)
from tradingagents.translation import build_translation_translator  # noqa: E402


def chunk_markdown(text: str, max_len: int = 6000) -> list[str]:
    """Split on top-level '## ' sections, packing into <= max_len pieces so
    each translation call stays under the model's output token cap."""
    parts = re.split(r"(?m)(?=^## )", text)
    chunks: list[str] = []
    buf = ""
    for part in parts:
        if buf and len(buf) + len(part) > max_len:
            chunks.append(buf)
            buf = part
        else:
            buf += part
    if buf:
        chunks.append(buf)
    return chunks


def main() -> None:
    user_id = sys.argv[1]
    src = Path(sys.argv[2])
    lang = sys.argv[3] if len(sys.argv) > 3 else "zh"

    text = src.read_text(encoding="utf-8")
    with SessionLocal() as session:
        snapshot = UserTranslationSettingsRepository(session).snapshot(user_id)
    if snapshot is None:
        raise SystemExit(f"no translation settings for user {user_id}")

    translator = build_translation_translator(snapshot)
    chunks = chunk_markdown(text)
    print(f"translating {len(chunks)} chunk(s) with {snapshot['llm_provider']}/{snapshot['model']}")

    translated: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        print(f"  chunk {i}/{len(chunks)} ({len(chunk)} chars)...", flush=True)
        translated.append(translator.translate(chunk, target_lang=lang))

    model_slug = snapshot["model"].replace("/", "-")
    out = src.with_name(f"{src.stem}.{lang}.{model_slug}.md")
    out.write_text("\n\n".join(translated) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
