"""Madani page lookups (604 pages)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.config import CONFIG
from app.quran.text import get_quran


@lru_cache(maxsize=1)
def load_page_map() -> list[dict]:
    path = Path(CONFIG.PAGE_MAP_PATH)
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _verse_to_page() -> dict[tuple[int, int], int]:
    index: dict[tuple[int, int], int] = {}
    for page_id, page in enumerate(load_page_map()):
        for key, content in page.items():
            if key.isdigit():
                for v in content.get("text", []):
                    index.setdefault((int(key), int(v["verseNumber"])), page_id)
    return index


def get_page_content(page_id: int) -> dict[str, Any]:
    pages = load_page_map()
    if page_id < 1 or page_id >= len(pages):
        raise KeyError(f"Page {page_id} out of range (1-{len(pages) - 1}).")
    page = pages[page_id]
    q = get_quran()
    out: dict[str, Any] = {"page": page_id, "verses": [], "meta": {}}
    if "juzNumber" in page:
        out["meta"]["juz"] = page["juzNumber"]
    for key in sorted((k for k in page if k.isdigit()), key=int):
        content = page[key]
        for v in content.get("text", []):
            s, a = int(key), int(v["verseNumber"])
            out["verses"].append({
                "surah": s, "ayah": a,
                "tokens": q.display_tokens(s, a) if q.exists(s, a) else [],
                "surahNameAr": content.get("titleAr", ""),
                "surahNameEn": content.get("titleEn", ""),
            })
    return out


def find_page_for_ayah(surah: int, ayah: int) -> int:
    return _verse_to_page().get((surah, ayah), 1)
