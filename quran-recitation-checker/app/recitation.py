"""
One reciter's live session: audio in, verdicts out.

Glues the streaming ASR (app.asr.streaming) to the tracker (app.quran.tracker)
and builds the JSON pushed to the client. Used by the WebSocket endpoint and by
the offline checker / QA harness, so both exercise exactly the same code.
"""
from __future__ import annotations

import threading
import time

import numpy as np

from app.asr.base import AsrBackend, AsrWord
from app.asr.streaming import StreamingTranscriber
from app.config import CONFIG
from app.profiles import get_profile
from app.quran.text import get_quran
from app.quran.tracker import HypWord, RecitationTracker
from app import session_store


def _hyp(words: list[AsrWord]) -> list[HypWord]:
    return [HypWord(w.text, w.start, w.end, w.prob) for w in words]


class RecitationSession:
    def __init__(self, backend: AsrBackend, surah: int, ayah: int,
                 profile: str = "medium", session_id: str | None = None):
        self.q = get_quran()
        self.profile = get_profile(profile)
        self.tracker = RecitationTracker(self.q, surah, ayah, self.profile)
        self.stream = StreamingTranscriber(backend, CONFIG.SAMPLE_RATE, CONFIG.STREAM_MAX_BUFFER_S)
        self.session_id = session_id
        self._lock = threading.Lock()
        self._done: set[tuple[int, int]] = set()   # verses already reported complete
        self.decode_ms: float | None = None
        if session_id:
            session_store.create_session(session_id, self.profile.name)

    # ----------------------------------------------------------------- input
    def add_pcm16(self, data: bytes) -> None:
        self.stream.add_pcm16(data)

    def add_audio(self, x: np.ndarray) -> None:
        self.stream.add_audio(x)

    def pending_seconds(self) -> float:
        return self.stream.pending_seconds()

    # ------------------------------------------------------------ processing
    def step(self) -> dict:
        """Decode pending audio and update verdicts (blocking: run in a worker)."""
        t0 = time.perf_counter()
        committed, tentative = self.stream.process()
        self.decode_ms = round((time.perf_counter() - t0) * 1000)
        with self._lock:
            self.tracker.update(_hyp(committed), _hyp(tentative))
            return self._payload()

    def snapshot(self) -> dict:
        """Current state without decoding (sent right after connecting)."""
        with self._lock:
            return self._payload()

    def finish(self) -> dict:
        """Flush remaining audio; every verdict becomes final."""
        rest = self.stream.finish()
        with self._lock:
            self.tracker.update(_hyp(rest), [])
            self.tracker.finish()
            return self._payload(final=True)

    def goto(self, surah: int, ayah: int) -> dict | None:
        with self._lock:
            if (surah, ayah) == self.tracker.current_verse:
                return None
            # Words still pending belong to the old position.
            rest = self.stream.commit_tentative()
            self.tracker.update(_hyp(rest), [])
            self.tracker.goto(surah, ayah)
            return self._payload()

    def set_profile(self, name: str) -> None:
        with self._lock:
            self.profile = get_profile(name)
            self.tracker.set_profile(self.profile)

    # --------------------------------------------------------------- output
    def _payload(self, final: bool = False) -> dict:
        tr = self.tracker
        cur = tr.current_verse
        changed = tr.pop_changed_verses()
        verses = {f"{s}:{a}": tr.verse_statuses((s, a)) for (s, a) in set(changed) | {cur}}

        completed = []
        for key in changed:
            if key not in self._done and tr.verse_complete(key):
                self._done.add(key)
                completed.append(tr.verse_summary(key))
        self._store(changed, final)

        cur_sum = tr.verse_summary(cur)
        tokens = self.q.display_tokens(*cur)
        idx = tr.index_in_verse(cur)
        statuses = verses[f"{cur[0]}:{cur[1]}"]
        last = statuses[idx] if 0 <= idx < len(statuses) else {}
        conf = last.get("conf")
        committed_text = " ".join(w.text for w in self.stream.committed[-25:])
        tentative_text = " ".join(w.text for w in self.stream.tentative)
        mistakes_note = ", ".join(
            f"{n} {label}" for n, label in ((cur_sum["substitutions"], "wrong"),
                                           (cur_sum["deletions"], "skipped"),
                                           (cur_sum["insertions"], "extra")) if n)
        session = session_store.get_session(self.session_id) if self.session_id else None

        return {
            "type": "final" if final else "update",
            "surah": cur[0],
            "ayah": cur[1],
            "ref_tokens": tokens,
            "current_index": idx,
            "token_statuses": statuses,
            "verses": verses,
            "completed": completed,
            "acc": {"matched": cur_sum["matches"], "total": cur_sum["total"],
                    "accuracy": cur_sum["accuracy"]},
            "mistakes": {"s": cur_sum["substitutions"], "d": cur_sum["deletions"],
                         "i": cur_sum["insertions"], "confidence": cur_sum["average_confidence"]},
            "hyp": f"{committed_text} {tentative_text}".strip(),
            "hyp_committed": committed_text,
            "hyp_tentative": tentative_text,
            "align": {
                "ayah": cur[1],
                "word": tokens[idx] if 0 <= idx < len(tokens) else "",
                "start": last.get("start"), "end": last.get("end"),
                "low": conf is not None and conf < self.profile.low_confidence,
                "note": "final" if final else ("ok" if conf is None else f"conf={conf:.2f}"),
            },
            "score": {"ayah": cur[1], "pct": round(cur_sum["accuracy"] * 100, 1),
                      "note": f" — {mistakes_note}" if mistakes_note else ""},
            "session": session.stats() if session else None,
            "decode_ms": self.decode_ms,
            "final": final,
            "session_updated": final,
        }

    def _store(self, changed: list[tuple[int, int]], final: bool) -> None:
        if not self.session_id:
            return
        touched = self.tracker.touched_verses()
        keys = touched if final else [k for k in changed if k in touched]
        for key in keys:
            s = self.tracker.verse_summary(key)
            statuses = self.tracker.verse_statuses(key)
            session_store.update_verse(self.session_id, {
                **s,
                "text": s["heard"],
                "tokens": self.q.display_tokens(*key),
                "mistakes": {
                    "matches": s["matches"], "substitutions": s["substitutions"],
                    "deletions": s["deletions"], "insertions": s["insertions"],
                    "accuracy": s["accuracy"], "average_confidence": s["average_confidence"],
                },
                "token_statuses": statuses,
                "profile": self.profile.name,
                "timestamp": time.time(),
            })
