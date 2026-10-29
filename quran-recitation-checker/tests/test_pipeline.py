"""
End-to-end tests of streaming ASR + tracker + WebSocket, using the tone-burst
fake ASR (see fake_asr.py), so they run without downloading a model.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).parent))
os.chdir(ROOT)
os.environ["API_KEY"] = "test-key"
os.environ["STREAM_STEP_MS"] = "500"

from fake_asr import SR, FakeToneBackend, ToneVocab, synth  # noqa: E402

from app.asr.streaming import StreamingTranscriber  # noqa: E402
from app.quran.text import get_quran  # noqa: E402
from app.recitation import RecitationSession  # noqa: E402

Q = get_quran()


def imlaei(surah, ayah):
    return [p for w in Q.words(surah, ayah) for p in w.imlaei.split()]


def stream_file(rs_or_st, audio, chunk_s=0.2, step_s=0.5):
    """Feed audio in real-time-sized chunks, decoding every step_s like the server."""
    chunk = int(chunk_s * SR)
    outs = []
    for i in range(0, audio.size, chunk):
        rs_or_st.add_audio(audio[i:i + chunk])
        if rs_or_st.pending_seconds() >= step_s:
            outs.append(rs_or_st.step() if hasattr(rs_or_st, "step") else rs_or_st.process())
    return outs


def test_streaming_commits_every_word_once_even_for_long_audio():
    vocab = ToneVocab()
    words = [w for a in range(1, 8) for w in imlaei(2, a)]  # ~70 words, ~35 s: far beyond the buffer
    audio = synth(words, vocab)
    st = StreamingTranscriber(FakeToneBackend(vocab), SR, max_buffer_s=6.0)
    committed = []
    for c, _t in stream_file(st, audio):
        committed.extend(c)
    committed.extend(st.finish())
    assert [w.text for w in committed] == words
    times = [w.start for w in committed]
    assert times == sorted(times)
    assert st._audio.size == 0


def test_session_long_passage_all_green_and_follows_verses():
    vocab = ToneVocab()
    words = [w for a in range(1, 8) for w in imlaei(2, a)]
    audio = synth(words, vocab, pause_after={len(imlaei(2, 1)) - 1: 1.0})
    rs = RecitationSession(FakeToneBackend(vocab), 2, 1, "strict", session_id="t1")
    payloads = stream_file(rs, audio)
    final = rs.finish()
    ayat_seen = [(p["surah"], p["ayah"]) for p in payloads]
    assert ayat_seen == sorted(ayat_seen)  # only moves forward
    assert final["surah"] == 2 and final["ayah"] == 8
    from app.session_store import get_session
    summary = get_session("t1").to_dict()
    assert [v["ayah"] for v in summary["verses"]] == list(range(1, 8))
    assert summary["stats"]["accuracy"] == 1.0
    for p in payloads:  # nothing is ever shown red for a correct recitation
        for sts in p["verses"].values():
            assert all(s["status"] in ("match", "pending") for s in sts)


def test_session_reports_skip_and_wrong_word():
    vocab = ToneVocab()
    w3 = imlaei(2, 3)
    spoken = w3[:2] + w3[3:6] + ["الكافرين"] + w3[7:] + imlaei(2, 4)  # skip word 3, wrong word 7
    audio = synth(spoken, vocab)
    rs = RecitationSession(FakeToneBackend(vocab), 2, 3, "medium")
    stream_file(rs, audio)
    rs.finish()
    st = [s["status"] for s in rs.tracker.verse_statuses((2, 3))]
    assert st[2] == "deletion"
    assert st[6] == "substitution"
    assert st.count("match") == len(st) - 2


def test_websocket_protocol(monkeypatch):
    from fastapi.testclient import TestClient

    import app.asr.registry as registry
    vocab = ToneVocab()
    monkeypatch.setattr(registry, "_backend", FakeToneBackend(vocab))
    monkeypatch.setattr(registry, "preload_in_background", lambda: None)
    from app.main import app

    words = imlaei(1, 1) + imlaei(1, 2) + imlaei(1, 3)
    audio = synth(words, vocab)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()

    with TestClient(app) as client:
        r = client.get("/ayah/1/2", headers={"X-API-Key": "test-key"})
        assert r.json()["ref_tokens"][-1] == "ٱلْعَـٰلَمِينَ"
        assert client.get("/ayah/1/2").status_code == 403
        assert client.get("/meta/page/1", headers={"X-API-Key": "test-key"}).status_code == 200

        url = "/ws/recite?surah=1&ayah=1&profile=medium&session_id=ws1&api_key=test-key"
        with client.websocket_connect(url) as ws:
            assert ws.receive_json() == {"status": "ready"}
            first = ws.receive_json()
            assert first["ref_tokens"][0] == "بِسْمِ" and first["current_index"] == -1
            step = int(0.2 * SR) * 2
            for i in range(0, len(pcm), step):
                ws.send_bytes(pcm[i:i + step])
            ws.send_text(json.dumps({"type": "stop"}))
            msgs = []
            while True:
                m = ws.receive_json()
                msgs.append(m)
                if m.get("type") == "final":
                    break
        final = msgs[-1]
        assert (final["surah"], final["ayah"]) == (1, 4)
        assert final["session"]["accuracy"] == 1.0
        summary = client.get("/api/session/ws1/summary").json()
        assert [v["ayah"] for v in summary["verses"]] == [1, 2, 3]
        assert all(v["complete"] for v in summary["verses"])
