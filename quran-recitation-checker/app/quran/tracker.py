"""
Real-time recitation tracker (replaces M2's SmartAligner).

It consumes the ASR words as they become stable and follows the reciter through
the Mushaf, across verse boundaries, deciding for every reference word whether
it was recited correctly, recited wrongly (substitution) or skipped (deletion),
and noting extra words (insertion).

Design rules that fix the M2 behaviour ("everything red", "green then red"):

* Comparison is done on Imlaei skeletons (see normalize.py / text.py), never on
  the Uthmani display text.
* The transcript is never truncated: the streaming ASR layer commits words once
  they are stable, and the tracker keeps every committed word. Verse changes
  happen here, not in the audio layer, so no audio is thrown away.
* A word's verdict is final once it is followed by a confident match
  ("anchor"). Final verdicts never change. Words after the last anchor are
  shown as provisional (light highlight) and are never shown red.
* Repeating already-recited words, saying the isti'adha / basmala before a
  surah, or "amin" after al-Fatiha are not mistakes.
"""
from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field

from app.profiles import Profile
from app.quran.matching import best_similarity, similarity
from app.quran.normalize import skeleton
from app.quran.text import QuranText, RefWord

logger = logging.getLogger(__name__)

VerseKey = tuple[int, int]

# Said before/after a surah; never counted as extra words there.
_FILLER_PHRASES = [
    "أعوذ بالله من الشيطان الرجيم",
    "بسم الله الرحمن الرحيم",
    "آمين",
    "صدق الله العظيم",
]
_FILLERS = {w for p in _FILLER_PHRASES for w in skeleton(p).split()}


@dataclass
class HypWord:
    text: str
    start: float | None = None
    end: float | None = None
    prob: float | None = None
    skel: str = ""

    def __post_init__(self) -> None:
        if not self.skel:
            self.skel = skeleton(self.text).replace(" ", "")


class Op(str, enum.Enum):
    MATCH = "match"
    SUB = "substitution"
    DEL = "deletion"
    INS = "insertion"
    REPEAT = "repeat"
    FILLER = "filler"


_CONSUMES_REF = (Op.MATCH, Op.SUB, Op.DEL)


@dataclass
class Step:
    op: Op
    ref: int | None              # absolute index into tracker.ref
    hyp: tuple[int, int] | None  # [start, end) absolute indices into the hyp list used
    sim: float = 0.0
    uncertain: bool = False


@dataclass
class WordResult:
    status: str                 # match | substitution | deletion
    score: float                # similarity 0..1 (0 for deletions)
    heard: str | None = None
    start: float | None = None
    end: float | None = None
    conf: float | None = None   # ASR probability
    uncertain: bool = False

    def to_dict(self, final: bool = True) -> dict:
        return {
            "status": self.status, "score": round(self.score, 3), "heard": self.heard,
            "start": self.start, "end": self.end,
            "conf": None if self.conf is None else round(self.conf, 3),
            "uncertain": self.uncertain, "final": final,
        }


@dataclass
class Extra:
    after_ref: int   # absolute ref index the word was heard after (-1 = before the first)
    word: HypWord
    op: Op
    verse: VerseKey | None = None  # verse it is counted against


@dataclass
class _Verse:
    start: int  # absolute ref index of its first word
    end: int    # one past its last word


class RecitationTracker:
    WINDOW = 40            # reference words considered ahead of the last final word
    REPEAT_LOOKBACK = 12   # how far back a repeated word may come from
    MAX_TAIL = 30          # unanchored committed words kept before forcing a decision
    LOST_AFTER = 5         # consecutive unmatched words before trying to relocate
    RELOCATE_AHEAD = 600   # words searched forward when the reciter jumps
    RELOCATE_BACK = 300
    MAX_SKIP_AS_MISTAKE = 60  # a longer forward jump is navigation, not a skipped passage

    COST_DEL = 1.0
    COST_INS = 1.0
    COST_REPEAT = 0.5
    COST_FILLER = 0.1
    COST_SPLIT = 0.1
    COST_POOR_MATCH = 0.3  # extra cost of pairing clearly different words (sim < 0.6)

    def __init__(self, quran: QuranText, surah: int, ayah: int, profile: Profile):
        self.q = quran
        self.profile = profile
        self.hyp: list[HypWord] = []
        self.g = 0  # first committed hyp word not yet finalised
        self._reset_ref(surah, ayah)

    # ------------------------------------------------------------------ setup
    def _reset_ref(self, surah: int, ayah: int) -> None:
        self.q.words(surah, ayah)  # raises KeyError for an invalid verse
        self.ref: list[RefWord] = []
        self.results: list[WordResult | None] = []
        self.verses: dict[VerseKey, _Verse] = {}
        self._next_load: VerseKey | None = (surah, ayah)
        self.start_verse: VerseKey = (surah, ayah)
        self.f = 0  # first reference word not yet finalised
        self.extras: list[Extra] = []
        self.provisional: dict[int, Step] = {}
        self.cursor = -1  # last reference word reached (provisional)
        self._dirty: set[VerseKey] = {(surah, ayah)}
        self._ensure(self.WINDOW)

    def _ensure(self, ahead: int) -> None:
        while len(self.ref) < self.f + ahead and self._next_load is not None:
            s, a = self._next_load
            ws = self.q.words(s, a)
            self.verses[(s, a)] = _Verse(len(self.ref), len(self.ref) + len(ws))
            self.ref.extend(ws)
            self.results.extend([None] * len(ws))
            self._next_load = self.q.next_ayah(s, a)

    def set_profile(self, profile: Profile) -> None:
        self.profile = profile

    # ------------------------------------------------------------- public API
    def update(self, committed: list[HypWord], tentative: list[HypWord] | None = None) -> None:
        """Add newly committed ASR words; tentative words only move the cursor."""
        self.hyp.extend(committed)
        if committed:
            self._finalise(force=False)
        self._update_provisional(tentative or [])

    def finish(self) -> None:
        """Everything heard so far is final (stop button / end of stream)."""
        self._finalise(force=True)
        self._update_provisional([])

    def goto(self, surah: int, ayah: int) -> None:
        """Reader manually jumped to another verse."""
        self.finish()
        self.g = len(self.hyp)
        self._reset_ref(surah, ayah)

    @property
    def current_verse(self) -> VerseKey:
        idx = min(self.cursor + 1, len(self.ref) - 1)
        if idx < 0:
            return self.start_verse
        w = self.ref[idx]
        return (w.surah, w.ayah)

    def index_in_verse(self, key: VerseKey) -> int:
        """Last word reached inside `key` (-1 if none yet)."""
        v = self.verses.get(key)
        if v is None or self.cursor < v.start:
            return -1
        return min(self.cursor, v.end - 1) - v.start

    def pop_changed_verses(self) -> list[VerseKey]:
        keys = sorted(k for k in self._dirty if k in self.verses)
        self._dirty.clear()
        return keys

    def verse_complete(self, key: VerseKey) -> bool:
        v = self.verses[key]
        return all(r is not None for r in self.results[v.start:v.end])

    def verse_statuses(self, key: VerseKey) -> list[dict]:
        v = self.verses[key]
        out = []
        for i in range(v.start, v.end):
            r = self.results[i]
            if r is not None:
                out.append(r.to_dict(final=True))
            elif i in self.provisional and self.provisional[i].op == Op.MATCH:
                st = self.provisional[i]
                out.append({"status": "match", "score": round(st.sim, 3), "final": False})
            else:
                out.append({"status": "pending", "score": 0.0, "final": False})
        return out

    def verse_summary(self, key: VerseKey) -> dict:
        """Counts and accuracy for one verse (final verdicts only)."""
        v = self.verses[key]
        res = self.results[v.start:v.end]
        decided = [r for r in res if r is not None]
        m = sum(r.status == "match" for r in decided)
        s = sum(r.status == "substitution" for r in decided)
        d = sum(r.status == "deletion" for r in decided)
        extras = [e for e in self.extras if e.verse == key]
        ins = sum(e.op == Op.INS or (e.op == Op.REPEAT and self.profile.count_repeats) for e in extras)
        reps = sum(e.op == Op.REPEAT for e in extras)
        complete = len(decided) == len(res)
        # Score against the whole verse once finished, against what was recited so far otherwise.
        denom = len(res) if complete else max(1, len(decided))
        acc = max(0.0, m - self.profile.insertion_penalty * ins) / denom if decided else 0.0
        scores = [r.score for r in decided if r.status != "deletion"]
        times = [t for r in decided for t in (r.start, r.end) if t is not None]
        return {
            "surah": key[0], "ayah": key[1],
            "complete": complete,
            "total": len(res), "recited": len(decided),
            "matches": m, "substitutions": s, "deletions": d, "insertions": ins, "repeats": reps,
            "accuracy": round(acc, 4),
            "average_confidence": round(sum(scores) / len(scores), 4) if scores else 0.0,
            "start": min(times) if times else None,
            "end": max(times) if times else None,
            "heard": " ".join(r.heard for r in decided if r.heard),
            "extra_words": [{"text": e.word.text, "kind": e.op.value, "start": e.word.start} for e in extras
                            if e.op != Op.FILLER],
        }

    def touched_verses(self) -> list[VerseKey]:
        return [k for k, v in self.verses.items()
                if any(r is not None for r in self.results[v.start:v.end])]

    # --------------------------------------------------------------- aligning
    def _finalise(self, force: bool) -> None:
        for _ in range(6):  # a few commit / relocate rounds per update at most
            self._ensure(self.WINDOW)
            tail = self.hyp[self.g:]
            if not tail:
                return
            steps = self._align(self.f, tail, self.g, at_end=force)
            if force:
                self._commit(steps)
                return
            cut = self._find_cut(steps)
            if cut is not None:
                self._commit(steps[:cut + 1])
                if cut == len(steps) - 1:
                    return
                continue  # look at what is left after the anchor
            if self._is_lost(steps) and self._relocate():
                continue
            if len(tail) > self.MAX_TAIL:  # keep the problem bounded
                drop = len(tail) - self.MAX_TAIL
                for j in range(self.g, self.g + drop):
                    self._add_extra(self.f - 1, self.hyp[j], Op.INS)
                self.g += drop
            return

    def _align(self, f: int, hyp: list[HypWord], offset: int, at_end: bool = False) -> list[Step]:
        """
        Banded semi-global DP: must start at ref[f], may stop anywhere in ref.
        at_end: no more audio will come, so ties are resolved towards the path
        that explains more of the text; while streaming, towards the shorter one.
        """
        ref = self.ref[f:f + self.WINDOW]
        n, m = len(ref), len(hyp)
        INF = float("inf")
        cost = [[INF] * (m + 1) for _ in range(n + 1)]
        back: list[list[tuple | None]] = [[None] * (m + 1) for _ in range(n + 1)]
        cost[0][0] = 0.0
        ins_cache: dict[tuple[int, int], tuple[Op, float]] = {}

        for i in range(n + 1):
            for j in range(m + 1):
                c = cost[i][j]
                if c == INF:
                    continue
                if i < n:  # skip ref word
                    if c + self.COST_DEL < cost[i + 1][j]:
                        cost[i + 1][j] = c + self.COST_DEL
                        back[i + 1][j] = (i, j, Op.DEL, 0.0)
                if j < m:  # extra hyp word
                    key = (i, j)
                    if key not in ins_cache:
                        ins_cache[key] = self._insertion_kind(f + i, hyp[j])
                    op, ic = ins_cache[key]
                    if c + ic < cost[i][j + 1]:
                        cost[i][j + 1] = c + ic
                        back[i][j + 1] = (i, j, op, 0.0)
                if i < n and j < m:  # ref word heard as 1..k hyp words
                    rw = ref[i]
                    joined = ""
                    prev_sim = 0.0
                    for k in range(1, min(rw.n_words + 1, m - j) + 1):
                        joined += hyp[j + k - 1].skel
                        sim = best_similarity(rw.forms, joined)
                        improved, prev_sim = sim > prev_sim + 0.05, max(prev_sim, sim)
                        if k > rw.n_words and (sim < 0.8 or not improved):
                            continue  # only for a word the ASR split in two, never to swallow the next word
                        step_cost = (1.0 - sim) + self.COST_SPLIT * max(0, k - rw.n_words)
                        if sim < 0.6:
                            step_cost += self.COST_POOR_MATCH
                        if c + step_cost < cost[i + 1][j + k]:
                            cost[i + 1][j + k] = c + step_cost
                            back[i + 1][j + k] = (i, j, Op.MATCH, sim)

        best = min(cost[i][m] for i in range(n + 1))
        tied = [i for i in range(n + 1) if cost[i][m] <= best + 1e-9]
        best_i = max(tied) if at_end else min(tied)
        steps: list[Step] = []
        i, j = best_i, m
        while (i, j) != (0, 0):
            pi, pj, op, sim = back[i][j]
            if op == Op.DEL:
                steps.append(Step(Op.DEL, f + pi, None))
            elif op == Op.MATCH:
                words = hyp[pj:j]
                probs = [w.prob for w in words if w.prob is not None]
                prob = min(probs) if probs else None
                verdict, uncertain = self._classify(sim, prob)
                steps.append(Step(verdict, f + pi, (offset + pj, offset + j), sim, uncertain))
            else:
                steps.append(Step(op, None, (offset + pj, offset + j)))
            i, j = pi, pj
        steps.reverse()
        return steps

    def _classify(self, sim: float, prob: float | None) -> tuple[Op, bool]:
        p = self.profile
        if sim >= p.match_threshold:
            return Op.MATCH, False
        if prob is not None and prob < p.low_confidence and sim >= p.uncertain_threshold:
            return Op.MATCH, True  # the ASR itself was unsure: benefit of the doubt
        return Op.SUB, False

    def _insertion_kind(self, ref_pos: int, w: HypWord) -> tuple[Op, float]:
        if ref_pos < len(self.ref):
            nxt = self.ref[ref_pos]
            at_surah_start = nxt.ayah == 1 and nxt.index == 0
        else:
            at_surah_start = False
        if (at_surah_start or ref_pos == 0) and w.skel in _FILLERS:
            return Op.FILLER, self.COST_FILLER
        thr = max(self.profile.match_threshold, 0.8)
        for r in range(max(0, ref_pos - self.REPEAT_LOOKBACK), min(ref_pos, len(self.ref))):
            if best_similarity(self.ref[r].forms, w.skel) >= thr:
                return Op.REPEAT, self.COST_REPEAT
        return Op.INS, self.COST_INS

    def _find_cut(self, steps: list[Step]) -> int | None:
        """
        Index of the last step after which verdicts can no longer change.

        A match is an anchor when it follows a clean stretch (at most one wrong
        word, no skipped word), or when it is the second match in a row. This
        stops a common word ("الله", "من") that happens to appear further on
        from being taken as proof that the words before it were skipped.
        """
        cut = None
        prev_ref_op: Op = Op.MATCH  # the last final word acts as a match
        subs = dels = 0
        for k, st in enumerate(steps):
            if st.op == Op.MATCH:
                if (dels == 0 and subs <= 1) or prev_ref_op == Op.MATCH:
                    cut = k
                    subs = dels = 0
            elif st.op == Op.SUB:
                subs += 1
            elif st.op == Op.DEL:
                dels += 1
            if st.op in _CONSUMES_REF:
                prev_ref_op = st.op
        return cut

    def _is_lost(self, steps: list[Step]) -> bool:
        """True when the last LOST_AFTER heard words matched nothing nearby."""
        run = 0
        for st in reversed(steps):
            if st.op == Op.MATCH:
                break
            if st.op in (Op.INS, Op.SUB):
                run += st.hyp[1] - st.hyp[0]
        return run >= self.LOST_AFTER

    def _relocate(self) -> bool:
        """
        The reciter jumped (skipped ahead or went back). Find the first three
        unexplained words somewhere else in the text and continue from there.
        """
        thr = max(self.profile.match_threshold, 0.8)
        self._ensure(self.RELOCATE_AHEAD)
        n = len(self.hyp)

        def hit(p: int, h: list[HypWord]) -> bool:
            return all(best_similarity(self.ref[p + k].forms, h[k].skel) >= thr for k in range(3))

        target = j = None
        for j in range(self.g, n - 2):
            h = self.hyp[j:j + 3]
            if sum(len(w.skel) for w in h) < 8:  # too short to be sure
                continue
            target = next((p for p in range(self.f, len(self.ref) - 2) if hit(p, h)), None)
            if target is None:
                lo = max(0, self.f - self.RELOCATE_BACK)
                target = next((p for p in range(self.f - 1, lo - 1, -1) if hit(p, h)), None)
            if target is not None:
                break
        if target is None:
            return False

        nothing_yet = not any(r is not None for r in self.results[:self.f])
        if target >= self.f:
            if nothing_yet or target - self.f > self.MAX_SKIP_AS_MISTAKE:
                # Started somewhere else / navigated far away: not a mistake.
                logger.info("Tracker: reading continues at word %d (no skip recorded)", target)
            else:  # skipped words or verses: those are mistakes
                for r in range(self.f, target):
                    self.results[r] = WordResult("deletion", 0.0)
                    self._mark_dirty(r)
            op = Op.INS
        else:  # went back to re-read: reopen those words
            for r in range(target, self.f):
                self.results[r] = None
                self._mark_dirty(r)
            self.extras = [e for e in self.extras if e.after_ref < target - 1]
            op = Op.REPEAT
        for k in range(self.g, j):
            self._add_extra(min(target, self.f) - 1, self.hyp[k], op)
        logger.info("Tracker relocated from word %d to %d", self.f, target)
        self.f, self.g = target, j
        self.provisional.clear()
        return True

    def _commit(self, steps: list[Step]) -> None:
        last_ref = self.f - 1
        for st in steps:
            if st.op in (Op.MATCH, Op.SUB):
                a, b = st.hyp
                words = self.hyp[a:b]
                probs = [w.prob for w in words if w.prob is not None]
                self.results[st.ref] = WordResult(
                    st.op.value, st.sim, " ".join(w.text for w in words),
                    words[0].start, words[-1].end, min(probs) if probs else None, st.uncertain)
                last_ref = st.ref
                self._mark_dirty(st.ref)
            elif st.op == Op.DEL:
                self.results[st.ref] = WordResult("deletion", 0.0)
                last_ref = st.ref
                self._mark_dirty(st.ref)
            else:
                for j in range(*st.hyp):
                    self._add_extra(last_ref, self.hyp[j], st.op)
                if last_ref >= 0:
                    self._mark_dirty(last_ref)
            if st.hyp:
                self.g = max(self.g, st.hyp[1])
        self.f = max(self.f, last_ref + 1)
        for r in list(self.provisional):
            if r < self.f:
                del self.provisional[r]

    def _update_provisional(self, tentative: list[HypWord]) -> None:
        old = {r: st.op for r, st in self.provisional.items()}
        self.provisional = {}
        tail = self.hyp[self.g:] + tentative
        cursor = self.f - 1
        if tail:
            steps = self._align(self.f, tail, 0)
            for st in steps:
                if st.ref is not None and st.op in (Op.MATCH, Op.SUB):
                    self.provisional[st.ref] = st
                    cursor = max(cursor, st.ref)
        new = {r: st.op for r, st in self.provisional.items()}
        for r in set(old) | set(new):
            if old.get(r) != new.get(r):
                self._mark_dirty(r)
        if cursor != self.cursor:
            for r in (self.cursor, cursor):
                if 0 <= r < len(self.ref):
                    self._mark_dirty(r)
            self.cursor = cursor

    def _add_extra(self, after_ref: int, word: HypWord, op: Op) -> None:
        """A repeat counts against the verse repeated; anything else against the next word's verse."""
        anchor = None
        if op == Op.REPEAT:
            lo = max(0, after_ref + 1 - self.REPEAT_LOOKBACK)
            cands = range(lo, min(after_ref + 1, len(self.ref)))
            anchor = max(cands, key=lambda r: best_similarity(self.ref[r].forms, word.skel), default=None)
        if anchor is None:
            anchor = after_ref + 1 if after_ref + 1 < len(self.ref) else after_ref
        verse = None
        if 0 <= anchor < len(self.ref):
            verse = (self.ref[anchor].surah, self.ref[anchor].ayah)
            self._dirty.add(verse)
        self.extras.append(Extra(after_ref, word, op, verse))

    def _mark_dirty(self, ref_idx: int) -> None:
        w = self.ref[ref_idx]
        self._dirty.add((w.surah, w.ayah))
