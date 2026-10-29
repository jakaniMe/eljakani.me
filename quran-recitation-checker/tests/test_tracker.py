import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QURAN_WORDS_PATH", str(ROOT / "data/quran/quran_words.json"))

from app.profiles import get_profile  # noqa: E402
from app.quran.text import get_quran  # noqa: E402
from app.quran.tracker import HypWord, RecitationTracker  # noqa: E402

Q = get_quran()


def imlaei(surah, ayah):
    """What a good ASR writes for a verse: standard spelling, one item per spoken word."""
    return [p for w in Q.words(surah, ayah) for p in w.imlaei.split()]


def feed(tr, words, step=1, prob=0.9):
    """Feed words as committed ASR output, `step` at a time, like the streamer does."""
    history = []
    t = 0.0
    for i in range(0, len(words), step):
        batch = []
        for w in words[i:i + step]:
            batch.append(HypWord(w, t, t + 0.4, prob))
            t += 0.5
        tr.update(batch, [])
        history.append({k: tr.verse_statuses(k) for k in tr.verses})
    return history


def statuses(tr, key):
    return [s["status"] for s in tr.verse_statuses(key)]


@pytest.mark.parametrize("profile", ["easy", "medium", "strict"])
def test_correct_recitation_is_all_green(profile):
    tr = RecitationTracker(Q, 2, 1, get_profile(profile))
    words = [w for a in range(1, 6) for w in imlaei(2, a)]
    feed(tr, words)
    tr.finish()
    for a in range(1, 6):
        assert set(statuses(tr, (2, a))) == {"match"}, (a, statuses(tr, (2, a)))
        assert tr.verse_summary((2, a))["accuracy"] == 1.0
    assert tr.current_verse == (2, 6)


def test_verdicts_never_flip_from_green_to_red():
    tr = RecitationTracker(Q, 2, 7, get_profile("strict"))
    hist = feed(tr, imlaei(2, 7) + imlaei(2, 8))
    seen_final = {}
    for snap in hist:
        for key, sts in snap.items():
            for i, s in enumerate(sts):
                if s["final"]:
                    prev = seen_final.setdefault((key, i), s["status"])
                    assert prev == s["status"]
                else:
                    assert s["status"] in ("match", "pending")  # provisional words are never red


def test_skipped_word_is_a_deletion():
    tr = RecitationTracker(Q, 2, 3, get_profile("medium"))
    words = imlaei(2, 3)
    del words[3]  # يقيمون
    feed(tr, words + imlaei(2, 4))
    tr.finish()
    st = statuses(tr, (2, 3))
    assert st[3] == "deletion"
    assert st.count("match") == len(st) - 1


def test_wrong_word_is_a_substitution():
    tr = RecitationTracker(Q, 1, 2, get_profile("medium"))
    words = imlaei(1, 2)
    words[2] = "مالك"  # instead of رب
    feed(tr, words + imlaei(1, 3))
    tr.finish()
    assert statuses(tr, (1, 2)) == ["match", "match", "substitution", "match"]


def test_extra_word_is_an_insertion():
    tr = RecitationTracker(Q, 1, 5, get_profile("medium"))
    words = imlaei(1, 5)
    words.insert(2, "الكريم")
    feed(tr, words + imlaei(1, 6))
    tr.finish()
    s = tr.verse_summary((1, 5))
    assert set(statuses(tr, (1, 5))) == {"match"}
    assert s["insertions"] == 1


def test_repeating_words_is_not_a_mistake():
    tr = RecitationTracker(Q, 2, 2, get_profile("medium"))
    w = imlaei(2, 2)
    feed(tr, w[:4] + w[1:4] + w[4:] + imlaei(2, 3))  # goes back three words
    tr.finish()
    s = tr.verse_summary((2, 2))
    assert set(statuses(tr, (2, 2))) == {"match"}
    assert s["insertions"] == 0 and s["repeats"] == 3


def test_istiadha_and_basmala_are_ignored():
    tr = RecitationTracker(Q, 2, 1, get_profile("strict"))
    pre = "أعوذ بالله من الشيطان الرجيم بسم الله الرحمن الرحيم".split()
    feed(tr, pre + imlaei(2, 1) + imlaei(2, 2))
    tr.finish()
    assert statuses(tr, (2, 1)) == ["match"]
    assert tr.verse_summary((2, 1))["insertions"] == 0


def test_disjoined_letters_spelled_out():
    tr = RecitationTracker(Q, 2, 1, get_profile("strict"))
    feed(tr, ["ألف", "لام", "ميم"] + imlaei(2, 2))
    tr.finish()
    assert statuses(tr, (2, 1)) == ["match"]


def test_asr_spelling_noise_is_tolerated_on_medium():
    tr = RecitationTracker(Q, 2, 3, get_profile("medium"))
    # missing hamza, Uthmani-style spelling of الصلاة, no diacritics at all
    words = "الذين يومنون بالغيب ويقيمون الصلوة ومما رزقناهم ينفقون".split()
    feed(tr, words + imlaei(2, 4))
    tr.finish()
    assert set(statuses(tr, (2, 3))) == {"match"}


def test_low_confidence_word_gets_benefit_of_doubt_except_strict():
    words = imlaei(1, 4)
    words[1] = "يوما"  # close but not equal to يوم
    for prof, expected in [("easy", "match"), ("medium", "match"), ("strict", "substitution")]:
        tr = RecitationTracker(Q, 1, 4, get_profile(prof))
        t = 0.0
        for i, w in enumerate(words + imlaei(1, 5)):
            tr.update([HypWord(w, t, t + 0.4, 0.3 if i == 1 else 0.95)])
            t += 0.5
        tr.finish()
        assert statuses(tr, (1, 4))[1] == expected, prof


def test_skipping_a_whole_verse_relocates():
    tr = RecitationTracker(Q, 2, 6, get_profile("medium"))
    feed(tr, imlaei(2, 6) + imlaei(2, 8) + imlaei(2, 9))  # 2:7 skipped
    tr.finish()
    assert set(statuses(tr, (2, 6))) == {"match"}
    assert set(statuses(tr, (2, 7))) == {"deletion"}
    assert set(statuses(tr, (2, 8))) == {"match"}


def test_goto_resets_position_but_keeps_results():
    tr = RecitationTracker(Q, 1, 1, get_profile("medium"))
    feed(tr, imlaei(1, 1))
    tr.goto(112, 1)
    feed(tr, imlaei(112, 1) + imlaei(112, 2))
    tr.finish()
    assert set(statuses(tr, (112, 1))) == {"match"}
    assert tr.current_verse == (112, 3)


def test_skip_right_before_the_end_of_the_recording():
    tr = RecitationTracker(Q, 1, 5, get_profile("easy"))
    w = imlaei(1, 5)
    feed(tr, w[:2] + w[3:])  # وإياك skipped, then the recording stops
    tr.finish()
    assert statuses(tr, (1, 5)) == ["match", "match", "deletion", "match"]


def test_starting_at_another_verse_is_not_a_skip():
    tr = RecitationTracker(Q, 2, 1, get_profile("medium"))
    feed(tr, imlaei(2, 5) + imlaei(2, 6))  # selected 2:1 but started at 2:5
    tr.finish()
    for a in range(1, 5):
        assert set(statuses(tr, (2, a))) == {"pending"}
    assert set(statuses(tr, (2, 5))) == {"match"}
    assert tr.current_verse == (2, 7)


def test_rereading_keeps_the_mistake_but_does_not_penalise_the_repeat():
    tr = RecitationTracker(Q, 112, 1, get_profile("medium"))
    w1 = imlaei(112, 1)
    bad = w1[:2] + ["الرحمن"] + w1[3:]  # wrong third word
    feed(tr, bad + w1 + imlaei(112, 2) + imlaei(112, 3))  # then re-reads the verse correctly
    tr.finish()
    assert statuses(tr, (112, 1)) == ["match", "match", "substitution", "match"]
    s = tr.verse_summary((112, 1))
    assert s["insertions"] == 0 and s["repeats"] == 4
    assert set(statuses(tr, (112, 2))) == {"match"}
