"""
In-memory session results (one entry per verse, latest attempt wins).

The JSON returned by /api/session/{id}/summary keeps the M2 field names
(verses[].accuracy, verses[].mistakes.substitutions, stats.accuracy, ...) and
adds per-verse timestamps, completion and the extra words that were heard.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

_MAX_SESSIONS = 500
_IDLE_TTL_S = 6 * 3600


@dataclass
class SessionData:
    session_id: str
    start_time: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)
    profile: str = "medium"
    verses: dict[str, dict] = field(default_factory=dict)  # "surah:ayah" -> record

    def stats(self) -> dict:
        recs = list(self.verses.values())
        m = sum(r["mistakes"]["matches"] for r in recs)
        s = sum(r["mistakes"]["substitutions"] for r in recs)
        d = sum(r["mistakes"]["deletions"] for r in recs)
        i = sum(r["mistakes"]["insertions"] for r in recs)
        # Accuracy weighted by words: each verse counts with its scored words.
        weights = [r["total"] if r["complete"] else r["recited"] for r in recs]
        scored = sum(r["accuracy"] * w for r, w in zip(recs, weights))
        total_w = sum(weights)
        return {
            "matches": m, "substitutions": s, "deletions": d, "insertions": i,
            "count": m + s + d,
            "accuracy": round(scored / total_w, 4) if total_w else 0.0,
            "verses_complete": sum(r["complete"] for r in recs),
        }

    def to_dict(self) -> dict:
        verses = sorted(self.verses.values(), key=lambda r: (r["surah"], r["ayah"]))
        return {
            "session_id": self.session_id,
            "start_time": self.start_time,
            "updated": self.updated,
            "profile": self.profile,
            "verses_count": len(verses),
            "verses": verses,
            "stats": self.stats(),
        }


_SESSIONS: dict[str, SessionData] = {}
_LOCK = threading.Lock()


def _evict() -> None:
    if len(_SESSIONS) <= _MAX_SESSIONS:
        return
    cutoff = time.time() - _IDLE_TTL_S
    for sid in [k for k, v in _SESSIONS.items() if v.updated < cutoff]:
        del _SESSIONS[sid]
    while len(_SESSIONS) > _MAX_SESSIONS:
        oldest = min(_SESSIONS, key=lambda k: _SESSIONS[k].updated)
        del _SESSIONS[oldest]


def create_session(session_id: str, profile: str = "medium") -> SessionData:
    with _LOCK:
        s = _SESSIONS.get(session_id)
        if s is None:
            _evict()
            s = _SESSIONS[session_id] = SessionData(session_id, profile=profile)
        s.profile = profile
        return s


def get_session(session_id: str) -> SessionData | None:
    return _SESSIONS.get(session_id)


def update_verse(session_id: str, record: dict) -> None:
    with _LOCK:
        s = _SESSIONS.get(session_id)
        if s is None:
            return
        s.verses[f'{record["surah"]}:{record["ayah"]}'] = record
        s.updated = time.time()
