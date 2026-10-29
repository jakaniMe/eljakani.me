# Qur'an Recitation Checker (M2 fix)

Live recitation checking: the reciter speaks into the microphone, the page follows
along in the Mushaf, and each word is marked **correct**, **wrong word**,
**skipped** or followed by an **extra word**, with a live per-āyah score and a
session summary. Runs fully offline after the first model download; no paid APIs.

The web page and the HTTP/WebSocket interface are the same as M2, so existing
clients keep working.

---

## What was wrong in M2, and what changed

| M2 symptom | Root cause | Fix |
|---|---|---|
| Correct recitation shown red | Mushaf words are **Uthmani** (`ٱلْكِتَـٰبُ`, `ٱلصَّلَوٰةَ`), the ASR writes **standard Arabic** (`الكتاب`, `الصلاة`). Every `ٱل…` word and every word with a dagger alif failed. Even a *perfect* transcript got 31 % of words flagged (Easy/Medium) and 62 % (Strict). | Each Mushaf word now carries its standard spelling (word-by-word map of the whole Qur'an, `data/quran/quran_words.json`). Matching uses letter skeletons (no harakat, unified hamza/alif/tā' marbūṭa). A perfect transcript now scores 100 % on all profiles. |
| Words turn green, then red | The ASR only looked at the **last 10 s** of audio. Once a verse was longer than that, its first words dropped out of the transcript and were re-scored as "skipped". | Streaming ASR now *commits* words once two decodes agree (LocalAgreement) and never forgets them. A word's verdict is final once the next word is matched, and a final verdict never changes. Words still being checked get a light blue highlight only, never red. |
| First words of the next verse missed | On auto-advance the client told the server to switch verse, and the server **wiped the audio buffer**, including the start of the next verse. | The server follows the reciter across verses itself; no audio is discarded. The page just follows the server. |
| Garbage first/last words (`كَافُ` for `ذَٰلِكَ ٱلْكِتَـٰبُ`) | Cutting audio at a fixed 10 s window splits words. | Audio is only trimmed after a committed word. |
| Mushaf showed altered text (`عَلَيٰ`, `هُدًي`) | Normalised tokens were displayed. | Original Uthmani text is displayed, with the Amiri Quran font bundled. |
| Two users interfere | One audio buffer shared by every connection. | One stream state per connection; the model is shared. |
| "Stuck at loading model" | Half-downloaded model cache. | A broken cache is wiped and re-downloaded automatically; `/health` and the page show the error. |
| Final results lost on Stop | Server sent them after the socket closed. | The page sends `stop`, waits for the final verdicts, then closes. |
| `/meta/page/{n}` crashed; API key printed in logs | Bugs. | Fixed. |

Also new: repeating words you already said (going back to re-read) is not a
mistake; the isti'ādha / basmala before a sūrah and "āmīn" are ignored; spelled-out
disjoined letters (`ألف لام ميم`) are accepted; if the reciter skips a whole
verse it is marked skipped; and starting somewhere other than the selected verse is
detected automatically.

## Quick start (Docker)

```bash
cp .env.example .env        # then set API_KEY
docker compose up --build
```

Open <http://localhost:5500>, enter the API key, pick a sūrah/āyah and press
**Start Recording**. The first start downloads the ASR model (a few hundred MB) into
`./models`. Later starts reuse it.

## Run without Docker

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --port 8000
# in another terminal
cd frontend && python -m http.server 5500
```

Python 3.13 is the tested version.

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `API_KEY` | – | Required from clients (header `X-API-Key`, or `?api_key=` on the WebSocket). Empty disables auth. |
| `FRONTEND_ORIGINS` | `http://localhost:5500,…` | Browser origins allowed to call the HTTP API. |
| `WHISPER_MODEL_SIZE` | `OdyAsh/faster-whisper-base-ar-quran` | Hugging Face id of a CTranslate2 Whisper model. The default is Tarteel's Qur'an-tuned Whisper base. |
| `WHISPER_MODEL_DIR` | – | Local model folder (overrides the above). |
| `WHISPER_DEVICE` / `WHISPER_COMPUTE_TYPE` | `cpu` / `int8` | `cuda` / `float16` on an NVIDIA GPU. |
| `WHISPER_CPU_THREADS` | 4 | Threads per decode. |
| `WHISPER_BEAM_SIZE` | 1 | 1 = fastest; 5 = slightly better, about 2× slower. |
| `ASR_WORKERS` | 1 | Simultaneous reciters decoded in parallel (needs `ASR_WORKERS × WHISPER_CPU_THREADS` cores). |
| `STREAM_STEP_MS` | 1000 | How often new audio is decoded. Lower is more responsive and uses more CPU. |
| `STREAM_MAX_BUFFER_S` | 12 | Un-committed audio kept before trimming (must stay < 25). |
| `PROFILES_PATH` | – | JSON file overriding profile thresholds (see below). |

## Profiles (Easy / Medium / Strict)

All profiles check **whole words**. Harakat/Tajwīd are out of scope for this
milestone. Profiles differ in how much ASR uncertainty is forgiven:

| | match threshold | benefit of the doubt when the ASR itself was unsure | extra-word penalty in score |
|---|---|---|---|
| Easy | 0.60 | yes (similarity ≥ 0.34) | 0 |
| Medium | 0.75 | yes (similarity ≥ 0.50) | 0.25 |
| Strict | 0.88 | no | 0.5 |

"Similarity" is 1 − (letter edit distance ÷ word length) on the letter skeletons.
Override any value without code changes:

```json
{ "medium": { "match_threshold": 0.7 }, "strict": { "count_repeats": true } }
```

Score per āyah = (correct words − penalty × extra words) ÷ words in the āyah (or
÷ words recited so far while the āyah is in progress). The session score is the
word-weighted average.

## How it works

```
mic ─PCM16─▶ WebSocket ─▶ StreamingTranscriber ──committed words──▶ RecitationTracker ─▶ JSON to page
            (per user)     app/asr/streaming.py                      app/quran/tracker.py
                           re-decodes the uncommitted buffer every    aligns words to the Mushaf
                           STREAM_STEP_MS; commits words two decodes  (current āyah and the following
                           agree on; trims committed audio            ones), decides match / wrong /
                                │                                     skipped / extra, follows the
                         ASR backend (shared)                         reciter across āyāt
                         app/asr/faster_whisper_engine.py
```

* `app/quran/normalize.py`: letter skeletons used for matching.
* `app/quran/text.py`: Mushaf words (Uthmani for display, standard spelling for matching).
* `app/quran/tracker.py`: alignment (dynamic programming over the next ~40 words)
  and the rules for when a verdict becomes final.
* `app/recitation.py`: one reciter's session; builds the JSON for the page.
* `app/offline.py`: runs the same pipeline on a recorded file.

## HTTP API

All routes need the API key (`X-API-Key` header or `?api_key=`), except `/health`
and the session summary.

| Route | |
|---|---|
| `GET /health` | Server and ASR model state (`asr.ready`, `asr.error`). |
| `GET /ayah/{s}/{a}` | `ref_tokens` (Uthmani words shown) and `imlaei_tokens`. |
| `GET /meta/surahs`, `/meta/surah/{s}`, `/meta/page/{n}`, `/meta/lookup/page?surah=&ayah=` | Metadata. |
| `GET /api/session/{id}/summary` | Per-āyah results of a session: accuracy, `mistakes` (S/D/I), `token_statuses` with timestamps, words heard, extra words, plus overall `stats`. |
| `GET /api/profiles` | Current profile values. |
| `POST /api/check` | Multipart `file` + `surah`, `ayah`, `profile`. Checks a whole recording with the live pipeline. Handy for testing and for a "record then check" mode. |

## WebSocket `/ws/recite`

```
ws://HOST:8000/ws/recite?surah=2&ayah=1&profile=medium&session_id=<uuid>&api_key=<key>
```

* **Client → server:** binary frames of 16 kHz mono PCM16 little-endian (about 200 ms each).
  Text frames: `{"type":"goto","surah":2,"ayah":5}` (or M2's `surah:2,ayah:5`),
  `{"type":"profile","profile":"strict"}`, and `{"type":"stop"}`, which flushes and
  sends the final verdicts while keeping the socket open.
* **Server → client:** `{"status":"loading"}` while the model loads,
  `{"status":"ready"}`, then after every decode:

```jsonc
{
  "type": "update",              // "final" after stop
  "surah": 2, "ayah": 3,         // where the reciter is now (server follows them)
  "ref_tokens": ["ٱلَّذِينَ", …],  // words of that āyah as displayed
  "current_index": 4,            // last word reached in that āyah (-1 = none)
  "token_statuses": [ {"status":"match","final":true,"score":1.0,"heard":"الَّذِينَ","start":12.3,"end":12.8,"conf":0.93,"uncertain":false}, … ],
  "verses": { "2:2": [ … ], "2:3": [ … ] },   // every āyah whose words changed
  "completed": [ {"surah":2,"ayah":2,"accuracy":0.86,"substitutions":0,"deletions":1,"insertions":0, …} ],
  "acc": {"matched":4,"total":8,"accuracy":1.0},
  "mistakes": {"s":0,"d":0,"i":0,"confidence":0.97},
  "score": {"ayah":3,"pct":100.0,"note":""},
  "session": {"accuracy":0.95, "matches":…, "substitutions":…, "deletions":…, "insertions":…},
  "hyp": "…what was heard…",
  "final": false
}
```

`status` is `match`, `substitution`, `deletion` or `pending`. Colour a word only when
`final` is true; a non-final `match` means "heard, being checked".

**Flutter notes:** stream the mic as 16 kHz mono PCM16 (e.g. the `record` package,
`AudioEncoder.pcm16bits`) in about 200 ms frames, keep a `Map<String, List>` of
`verses` statuses, scroll to `surah:ayah` from each update, and send
`{"type":"stop"}` before closing.

## QA (precision / recall)

```bash
python qa/build_dataset.py --reciters Alafasy_128kbps,Husary_128kbps --noise-snr 20
python qa/run_qa.py                     # writes qa/reports/qa_report.md + .json
python qa/check_file.py my_recitation.m4a --from 2:1 --profile medium
```

`build_dataset.py` downloads EveryAyah recordings (Al-Fātiḥa, Al-Baqarah 1–5 and
random āyāt from Juz' 'Amma and the rest of the Qur'an). It plants one mistake per
clip by cutting a word out, replacing it with a word from another verse, or
inserting one, and records the expected verdicts. `run_qa.py` reports recall,
false-positive rate, clean-verse rate, repeatability and decode time per profile
against the targets (recall ≥ 85 %, false positives ≤ 10 %). Add your own
recordings to `qa/data/manifest.jsonl` (format in `build_dataset.py`) to measure
real-microphone performance.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests need no model download. They use a fake ASR that encodes each word as a
tone, so streaming, trimming, verse following, the WebSocket protocol and the QA
harness are all exercised end to end.

## Troubleshooting

* **Page stuck on "Loading model" / error on start:** check `GET /health` →
  `asr.error`. Without internet on first start the model cannot be downloaded. A
  broken download is cleared and retried automatically; deleting `models/` also
  forces a fresh download.
* **Feedback lags behind:** decodes are slower than `STREAM_STEP_MS` on this CPU.
  See `decode_ms` in the WebSocket updates, raise `STREAM_STEP_MS` to 1500, or use
  a GPU.
* **Too many words flagged with a poor microphone:** use Easy, or lower
  `match_threshold` through `PROFILES_PATH`.

## Credits and licences

* Qur'an text: Tanzil.net (Uthmani). Uthmani↔standard word map: `quran-transcript`
  (MIT, obadx/quran-transcript), rebuilt with `tools/build_quran_words.py`.
* Font: Amiri Quran, SIL Open Font License (`frontend/fonts/OFL.txt`).
* ASR model: Tarteel's `whisper-base-ar-quran` (CTranslate2 conversion by OdyAsh).
  Check the model card licence before commercial use.
