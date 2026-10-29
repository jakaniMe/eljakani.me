/* global AudioContext */
const $ = (id) => document.getElementById(id);

// Backend address: same host as this page, port 8000 (override with window.QURAN_API_BASE).
const API_BASE_HTTP = (window.QURAN_API_BASE || `${location.protocol}//${location.hostname || 'localhost'}:8000`).replace(/\/$/, '');
const WS_BASE = API_BASE_HTTP.replace(/^http/, 'ws') + '/ws/recite';

// Get API Key from LocalStorage or Prompt User
let API_KEY = localStorage.getItem("api_key");
if (!API_KEY) {
  API_KEY = prompt("Please enter your API Key to access the Quran Recitation App:");
  if (API_KEY) {
    localStorage.setItem("api_key", API_KEY);
  } else {
    alert("API Key is required. The app may not function correctly.");
  }
}

const TARGET_SAMPLE_RATE = 16000;
const CHUNK_MS = 200;
const BUFFER_SIZE = 4096;
const WINDOW_SIZE = 9;
const STOP_TIMEOUT_MS = 15000;

// --- State ---
function generateUUID() {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
    var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
}
// --- State ---
// --- State ---
let ws = null;
let audioCtx = null;
let processor = null;
let mediaStream = null;
let sessionId = generateUUID();
let stopResolver = null; // resolves when the server sends the final results

let currentSurah = 1;
let currentAyah = 1;
let currentIndex = -1; // last word reached in the current verse
let verseStatuses = new Map(); // "surah:ayah" -> [{status, final, score, heard, ...}]

// Page Navigation State
let currentPage = 1;
let pageMode = false;
let versesOnPage = [];

// --- Config ---
let autoAdvance = true;
let lastMistakes = { s: 0, d: 0, i: 0 };
let appState = "idle";

let refTokens = [], lowCurrent = false;
let windowStartAyah = Math.max(1, currentAyah - 1);
const ayahCache = new Map();
const SURAH_META = new Map(); // index:int -> { index, name, arabic, total_verses }

async function loadSurahList() {
  const url = `${API_BASE_HTTP}/meta/surahs`;
  try {
    const res = await fetch(url, {
      headers: { 'X-API-Key': API_KEY }
    });
    if (!res.ok) {
      console.error('Failed to fetch /meta/surahs', res.status);
      return;
    }
    const data = await res.json();
    const list = data.surahs || [];
    SURAH_META.clear();

    for (const s of list) {
      const idx = Number(s.id);
      SURAH_META.set(idx, {
        index: idx,
        name: s.transliteration, // e.g. "Al-Fatihah"
        arabic: s.name,          // e.g. "الفاتحة"
        total_verses: Number(s.total_verses) || 1,
      });
    }

    // Populate Dropdown if it exists
    const surahSel = $('surah');
    if (surahSel) {
      surahSel.innerHTML = '';
      SURAH_META.forEach(meta => {
        const opt = document.createElement('option');
        opt.value = String(meta.index);
        opt.textContent = `${meta.index}. ${meta.name} (${meta.arabic})`;
        surahSel.appendChild(opt);
      });

      // Select current
      surahSel.value = String(currentSurah);

      // Event Listener
      surahSel.addEventListener('change', async () => {
        currentSurah = Number(surahSel.value);
        currentAyah = 1;
        windowStartAyah = 1;
        updateAyahInputMax();
        $('ayah').value = "1";
        // Just load active ayah, it handles window building
        await loadActiveAyah(currentSurah, currentAyah);
      });
    }

    // Ayah Input Wiring
    const ayahIn = $('ayah');
    if (ayahIn) {
      ayahIn.value = String(currentAyah);
      updateAyahInputMax();

      ayahIn.addEventListener('change', async () => {
        let val = parseInt(ayahIn.value);
        if (isNaN(val)) val = 1;
        let s = currentSurah;
        const meta = SURAH_META.get(s);

        if (meta) {
          // Handle Next Surah
          if (val > meta.total_verses) {
            if (s < 114) {
              s++;
              val = 1;
              // Update Surah Dropdown
              const surahSel = $('surah');
              if (surahSel) surahSel.value = String(s);
            } else {
              val = meta.total_verses; // Cap at end of Quran
            }
          }
          // Handle Previous Surah (Optional, but nice)
          else if (val < 1) {
            if (s > 1) {
              s--;
              const prevMeta = SURAH_META.get(s);
              val = prevMeta ? prevMeta.total_verses : 1;
              // Update Surah Dropdown
              const surahSel = $('surah');
              if (surahSel) surahSel.value = String(s);
            } else {
              val = 1; // Cap at start of Quran
            }
          }
        }

        currentSurah = s;
        currentAyah = val;
        windowStartAyah = Math.max(1, currentAyah - 1);
        ayahIn.value = String(val);
        updateAyahInputMax(); // Update max for new Surah

        await loadActiveAyah(currentSurah, currentAyah);
      });
    }

    // Metadata loaded
  } catch (e) {
    console.error('Error loading surahs:', e);
  }
}

function updateAyahInputMax() {
  const ayahIn = $('ayah');
  if (!ayahIn) return;
  // We remove max to allow the user to go beyond the last ayah, triggering the jump to the next surah.
  ayahIn.removeAttribute('max');
  // We remove min to allow the user to go below 1, triggering the jump to the previous surah.
  ayahIn.removeAttribute('min');
}

let floatQueue = [], lastSendTs = 0;
let lastHyp = "";

function logln(msg) {
  const el = $('log');
  if (!el) return;
  const t = typeof msg === 'string' ? msg : JSON.stringify(msg);
  el.textContent += t + '\n';
  el.scrollTop = el.scrollHeight;
}

function arabicIndic(n) {
  const map = ["٠", "١", "٢", "٣", "٤", "٥", "٦", "٧", "٨", "٩"];
  return String(n).split("").map(d => map[+d]).join("");
}

function debounce(fn, ms = 160) {
  let t;
  return (...a) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...a), ms);
  };
}

async function fetchAyahTokens(surah, ayah) {
  const key = `${surah}:${ayah}`;
  if (ayahCache.has(key)) return ayahCache.get(key);

  const url = `${API_BASE_HTTP}/ayah/${surah}/${ayah}`;
  try {
    const res = await fetch(url, {
      headers: { 'X-API-Key': API_KEY }
    });
    if (!res.ok) {
      logln(`HTTP ${res.status} for ${url}`);
      return [];
    }
    const data = await res.json();
    const toks = data.ref_tokens || [];
    if (!toks.length) logln(`Empty tokens for ${surah}:${ayah}`);

    ayahCache.set(key, toks);
    return toks;
  } catch (e) {
    logln(`Fetch error ${url}: ${e.message}`);
    return [];
  }
}

async function buildWindow() {
  const ayahs = [];
  let added = 0;
  let s = currentSurah;
  let a = windowStartAyah;

  while (added < WINDOW_SIZE) {
    let toks = await fetchAyahTokens(s, a);

    // If empty, it might be end of Surah. Try next Surah.
    if (!toks.length) {
      if (s < 114) {
        s++;
        a = 1;
        toks = await fetchAyahTokens(s, a);
      }
      // If still empty (or end of Quran), stop.
      if (!toks.length) break;
    }

    ayahs.push({ surah: s, ayah: a, tokens: toks });
    added++;
    a++;
  }
  return ayahs;
}

function renderMushafPanel(ayahs) {
  const panel = $('mushafPanel');
  if (!panel) return;
  panel.innerHTML = "";

  if (!ayahs || ayahs.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'panel small';
    empty.textContent = 'No verses to display — check API connection.';
    panel.appendChild(empty);
    return;
  }

  // Create a single container for the continuous paragraph
  const container = document.createElement('div');
  container.className = 'mushaf-layout';

  let lastRenderedSurah = -1;

  ayahs.forEach(item => {
    const { surah, ayah, tokens } = item;

    // Check for Surah change
    if (surah !== lastRenderedSurah) {
      const meta = SURAH_META.get(surah);
      const surahName = meta ? meta.arabic : `Surah ${surah}`;

      const header = document.createElement('div');
      header.className = 'surah-separator';

      // Decorative frame for Surah name
      const frame = document.createElement('div');
      frame.className = 'surah-frame';
      frame.textContent = `سورة ${surahName}`;

      header.appendChild(frame);
      container.appendChild(header);
      lastRenderedSurah = surah;
    }

    const isActive = (surah === currentSurah && ayah === currentAyah);

    // Create a span for the Ayah text
    const ayahSpan = document.createElement('span');
    ayahSpan.className = 'ayah-span';
    if (isActive) ayahSpan.classList.add('active-ayah');

    const vStatuses = verseStatuses.get(`${surah}:${ayah}`) || [];
    tokens.forEach((tok, idx) => {
      const span = document.createElement('span');
      span.className = 'token';
      // Highlight the NEXT word to be recited (currentIndex is the last one reached)
      if (isActive && appState === 'recording' && idx === currentIndex + 1) {
        span.classList.add('active');
        if (lowCurrent) span.classList.add('low');
      }
      applyStatus(span, vStatuses[idx]);
      span.textContent = tok;
      ayahSpan.appendChild(span);
      ayahSpan.appendChild(document.createTextNode(' '));
    });

    container.appendChild(ayahSpan);

    // Add Ayah Marker (Number)
    const marker = document.createElement('span');
    marker.className = 'ayah-marker';
    marker.textContent = arabicIndic(ayah);
    container.appendChild(marker);

    // Add a space after the marker
    container.appendChild(document.createTextNode(' '));
  });

  panel.appendChild(container);
}

// Final verdicts get their colour; words heard but not yet final get a light highlight only,
// so a word is never shown green and then red.
function applyStatus(span, st) {
  if (!st) return;
  const status = typeof st === 'object' ? st.status : st;
  const final = typeof st === 'object' ? st.final !== false : true;
  if (status === 'pending') return;
  if (!final) {
    if (status === 'match') span.classList.add('confirmed');
    return;
  }
  span.classList.add(`status-${status}`);
  if (st.uncertain) span.classList.add('low');
  if (typeof st === 'object') {
    const parts = [];
    if (st.heard) parts.push(`Heard: ${st.heard}`);
    if (typeof st.score === 'number' && status !== 'deletion') parts.push(`Similarity: ${Math.round(st.score * 100)}%`);
    if (st.uncertain) parts.push('ASR was unsure here');
    if (parts.length) span.title = parts.join('\n');
  }
}

// We need to store the current window ayahs locally for re-rendering (e.g. status updates)
// Since we removed the global windowAyahs, we should probably keep a reference if needed for debounced updates.
// Or just pass it around. But debouncedRelayout takes no args.
// Let's re-introduce a module-level variable ONLY for the current view state, but only write to it in one place.
let currentWindowAyahs = [];

const debouncedRelayout = debounce(() => renderMushafPanel(currentWindowAyahs), 140);

async function lookupPageForVerse(surah, ayah) {
  try {
    const res = await fetch(`${API_BASE_HTTP}/meta/lookup/page?surah=${surah}&ayah=${ayah}`, {
      headers: { 'X-API-Key': API_KEY }
    });
    if (res.ok) {
      const data = await res.json();
      return data.page;
    }
  } catch (e) { console.error(e); }
  return 1;
}

async function loadPage(pageId) {
  pageMode = true; // Enable page mode
  currentPage = pageId;
  const pi = $('pageInput');
  if (pi) pi.value = pageId;


  try {
    const res = await fetch(`${API_BASE_HTTP}/meta/page/${pageId}`, {
      headers: { 'X-API-Key': API_KEY }
    });
    if (!res.ok) throw new Error("Page not found");
    const data = await res.json();

    versesOnPage = data.verses; // {surah, ayah, tokens, ...}

    // Update global current position to start of page
    if (versesOnPage.length > 0) {
      currentSurah = versesOnPage[0].surah;
      currentAyah = versesOnPage[0].ayah;

      // Update Selectors if they exist
      if ($('surahSelect')) $('surahSelect').value = currentSurah;
      if ($('ayahSelect')) {
        // Might need to wait for ayah count?
        // Just set it, updateAyahInputMax usually runs on surah change
        $('ayahSelect').value = currentAyah;
      }
    }

    renderMushafPanel(versesOnPage);
  } catch (e) {
    console.error(e);
    alert("Failed to load page: " + e.message);
  }
}

// fromServer = true when the server says the reciter moved on: update the view only,
// do not send a "goto" (that would reset the server's position).
async function loadActiveAyah(surah, ayah, fromServer = false) {
  // If in page mode, check if we need to change page
  if (pageMode) {
    // Find if currentSurah:currentAyah is on current page
    const onPage = versesOnPage.find(v => v.surah === currentSurah && v.ayah === currentAyah);
    if (onPage) {
      // Just re-render to update highlights
      renderMushafPanel(versesOnPage);
      return;
    } else {
      // Determine if we moved forward or backward off-page
      // Simplification: Try loading the page that *should* contain this verse?
      // Or just load next page?
      // For now, if we drift off page, disable Page Mode or load next page?
      // Let's assume sequential reading:
      loadPage(currentPage + 1);
      return;
    }
  }

  // Legacy behavior for single-verse mode
  try {
    // Show loading state...
  } catch (e) {
    console.error(e);
  }

  currentSurah = surah;
  currentAyah = ayah;

  if ($('surah') && $('surah').value != surah) $('surah').value = surah;
  if ($('ayah') && $('ayah').value != ayah) $('ayah').value = ayah;

  try {
    localStorage.setItem('currentSurah', currentSurah);
    localStorage.setItem('currentAyah', currentAyah);
  } catch (e) {
    console.error(e);
  }



  // Sync Page Number (Background)
  lookupPageForVerse(currentSurah, currentAyah).then(p => {
    if (p) {
      currentPage = p;
      const pi = $('pageInput');
      if (pi && document.activeElement !== pi) pi.value = p;
    }
  });

  refTokens = await fetchAyahTokens(currentSurah, currentAyah);
  // verseStatuses is NOT reset here, to persist tags across verses
  lastMistakes = { s: 0, d: 0, i: 0 }; // Reset mistakes

  currentIndex = -1;
  lowCurrent = false;

  // Pagination Logic with Overlap
  // User wants to advance when reaching N-1, and include N in the next block.
  // This implies a stride of WINDOW_SIZE - 2.
  // e.g. Size 8. Stride 6.
  // 1-8 (Trigger at 7) -> 7-14 (Includes 8) -> 13-20 (Trigger at 13)
  const stride = Math.max(1, WINDOW_SIZE - 2);
  const pageIndex = Math.floor((currentAyah - 1) / stride);
  const newWindowStart = (pageIndex * stride) + 1;

  // Only rebuild window if we moved to a new page
  if (newWindowStart !== windowStartAyah || currentWindowAyahs.length === 0) {
    windowStartAyah = newWindowStart;
    currentWindowAyahs = await buildWindow();
  }

  // Always render to update active highlights
  renderMushafPanel(currentWindowAyahs);

  try {
    history.replaceState(null, "", `#${currentSurah}:${currentAyah}`);
  } catch { }
  if (!fromServer) logln(`Active verse loaded ${currentSurah}:${currentAyah}`);

  if (!fromServer && ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'goto', surah: currentSurah, ayah: currentAyah }));
  }
}

function openWS() {
  try {
    if (ws && ws.readyState === WebSocket.OPEN) ws.close();
  } catch { }
  const profile = $('profileSelect').value || "medium";
  const wsUrl = `${WS_BASE}?surah=${currentSurah}&ayah=${currentAyah}&api_key=${encodeURIComponent(API_KEY || '')}&profile=${profile}&session_id=${sessionId}`;

  logln(`Connecting WS to ${currentSurah}:${currentAyah} (Profile: ${profile})...`);
  ws = new WebSocket(wsUrl);
  ws.binaryType = "arraybuffer";

  ws.onopen = () => logln("WS connected.");
  ws.onerror = () => logln("WS error (see devtools)");
  ws.onclose = (ev) => {
    logln(`WS closed code=${ev.code}${ev.reason ? ' (' + ev.reason + ')' : ''}`);
    if (stopResolver) { stopResolver(); stopResolver = null; }
    if (appState !== 'idle') {
      releaseAudio();
      updateUIState('idle');
    }
  };

  ws.onmessage = (ev) => {
    let data;
    try { data = JSON.parse(ev.data); } catch { return; }
    if (data.error) {
      logln("Server error: " + data.error);
      const st = $('status');
      if (st) st.textContent = data.error;
      return;
    }
    if (data.status === "loading") {
      const st = $('status');
      if (st) st.textContent = "Server is loading the ASR model (first run downloads it)...";
      return;
    }
    if (data.status === "ready") {
      if (appState === "loading") startAudioStream();
      return;
    }
    handleUpdate(data).catch(e => console.error(e));
  };
}

async function handleUpdate(data) {
  // Statuses for every verse that changed (finished verses and the current one).
  if (data.verses) {
    for (const [key, sts] of Object.entries(data.verses)) verseStatuses.set(key, sts);
  }
  if (data.mistakes) lastMistakes = data.mistakes;

  for (const v of data.completed || []) {
    const bits = [];
    if (v.substitutions) bits.push(`${v.substitutions} wrong`);
    if (v.deletions) bits.push(`${v.deletions} skipped`);
    if (v.insertions) bits.push(`${v.insertions} extra`);
    logln(`✔ ${v.surah}:${v.ayah} — ${(v.accuracy * 100).toFixed(0)}%${bits.length ? ' — ' + bits.join(', ') : ''}`);
  }

  if (typeof data.hyp === 'string' && data.hyp !== lastHyp) {
    lastHyp = data.hyp;
    const el = $('hypText');
    if (el) el.textContent = data.hyp.split(' ').slice(-12).join(' ') || '—';
  }

  // The server follows the reciter from verse to verse.
  const moved = typeof data.surah === 'number' && (data.surah !== currentSurah || data.ayah !== currentAyah);
  if (moved && (autoAdvance || data.type === 'final')) {
    await loadActiveAyah(data.surah, data.ayah, true);
  }
  const showingServerVerse = data.surah === currentSurah && data.ayah === currentAyah;

  if (showingServerVerse) {
    if (Array.isArray(data.ref_tokens)) refTokens = data.ref_tokens;
    if (typeof data.current_index === 'number') currentIndex = data.current_index;
    if (data.align) lowCurrent = !!data.align.low;

    if (data.score) {
      const s = data.score;
      const scoreEl = $('scoreLine');
      if (scoreEl) scoreEl.textContent = `Ayah ${s.ayah} — ${s.pct}% match${s.note || ''}`;
    }
    if (data.mistakes && data.mistakes.confidence !== undefined) {
      const d = $('confScore');
      if (d) d.textContent = (data.mistakes.confidence * 100).toFixed(1) + "%";
    }
    if (data.acc) {
      const accPct = $('accPct'), accMatch = $('accMatch'), accTotal = $('accTotal');
      if (accPct) accPct.textContent = (data.acc.accuracy * 100).toFixed(1);
      if (accMatch) accMatch.textContent = data.acc.matched ?? 0;
      if (accTotal) accTotal.textContent = data.acc.total ?? 0;
    }
  }
  debouncedRelayout();

  if (data.type === 'final' && stopResolver) {
    stopResolver();
    stopResolver = null;
  }
}

async function nextAyahOrFinish() {
  const next = currentAyah + 1;
  const toks = await fetchAyahTokens(currentSurah, next);
  if (toks.length) {
    currentAyah = next;
    if ($('ayah')) $('ayah').value = currentAyah;
    await loadActiveAyah(currentSurah, currentAyah);
    logln(`→ Advanced to ${currentSurah}:${currentAyah}`);
  } else {
    if (currentSurah < 114) {
      logln(`✔️ Surah ${currentSurah} completed. Moving to Surah ${currentSurah + 1}...`);
      currentSurah += 1;
      currentAyah = 1;
      if ($('surah')) $('surah').value = currentSurah;
      if ($('ayah')) $('ayah').value = currentAyah;
      if (window.setAyahMaxForSurah) window.setAyahMaxForSurah(currentSurah);
      await loadActiveAyah(currentSurah, currentAyah);
    } else {
      logln(`✔️ Quran completed (Surah 114). Stopping.`);
      autoAdvance = false;
      const tb = $('toggleAdvanceBtn');
      if (tb) tb.textContent = "Auto-Advance: OFF";
    }
  }
}

function concatFloat32(pieces) {
  const total = pieces.reduce((a, arr) => a + arr.length, 0);
  const out = new Float32Array(total);
  let off = 0;
  for (const p of pieces) {
    out.set(p, off);
    off += p.length;
  }
  return out;
}

function float32ToPCM16LE(float32Array) {
  const buffer = new ArrayBuffer(float32Array.length * 2),
    view = new DataView(buffer);
  let offset = 0;
  for (let i = 0; i < float32Array.length; i++, offset += 2) {
    let s = Math.max(-1, Math.min(1, float32Array[i]));
    const v = s < 0 ? s * 0x8000 : s * 0x7fff;
    view.setInt16(offset, v, true);
  }
  return buffer;
}

function downsampleFloat32(f32, inRate, outRate) {
  if (outRate === inRate) return f32;
  // Average the input samples that fall into each output sample (simple anti-aliasing).
  const ratio = inRate / outRate;
  const newLen = Math.floor(f32.length / ratio);
  const down = new Float32Array(newLen);
  for (let i = 0; i < newLen; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(f32.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += f32[j];
    down[i] = sum / Math.max(1, end - start);
  }
  return down;
}

function updateUIState(state) {
  appState = state;
  const btn = $('micBtn');
  const st = $('status');
  if (!btn || !st) return;

  btn.className = `status-${state}`;
  if (state === 'idle') {
    btn.textContent = "🎤 Start Recording";
    st.textContent = "Idle";
  } else if (state === 'loading') {
    btn.textContent = "⏳ Loading Model...";
    st.textContent = "Waiting for server...";
  } else if (state === 'recording') {
    btn.textContent = "⏹ Stop Recording";
    st.textContent = "Recording...";
    const sb = $('showSummaryBtn');
    if (sb) sb.style.display = 'inline-block';
  } else if (state === 'stopping') {
    btn.textContent = "⏳ Finishing...";
    st.textContent = "Checking the last words...";
  }
}

async function toggleMic() {
  if (appState === 'idle') {
    await prepareRecording();
  } else if (appState === 'recording' || appState === 'loading') {
    await stopMic();
  }
}

async function prepareRecording() {
  updateUIState('loading');
  logln("Connecting to server...");

  const sumBtn = $('showSummaryBtn');
  if (sumBtn) sumBtn.style.display = 'none';

  await loadActiveAyah(currentSurah, currentAyah);
  openWS();
}

async function startAudioStream() {
  updateUIState('recording');
  logln("Model ready. Starting microphone...");

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        sampleRate: 16000,
        noiseSuppression: true,
        echoCancellation: true,
        autoGainControl: true,
      }
    });

    audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    const source = audioCtx.createMediaStreamSource(mediaStream);

    processor = audioCtx.createScriptProcessor(BUFFER_SIZE, 1, 1);
    floatQueue = [];
    lastSendTs = performance.now();

    processor.onaudioprocess = (e) => {
      const input = e.inputBuffer.getChannelData(0);
      const down = downsampleFloat32(input, audioCtx.sampleRate, TARGET_SAMPLE_RATE);
      floatQueue.push(down);
      const now = performance.now();
      if (now - lastSendTs >= CHUNK_MS) {
        const batchF32 = concatFloat32(floatQueue);
        floatQueue = [];
        lastSendTs = now;
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(float32ToPCM16LE(batchF32));
      }
    };
    source.connect(processor);
    processor.connect(audioCtx.destination);
    renderMushafPanel(currentWindowAyahs);
  } catch (e) {
    logln("Mic error: " + e.message);
    stopMic();
  }
}

async function releaseAudio() {
  if (processor) {
    try { processor.disconnect(); } catch { }
    processor = null;
  }
  if (audioCtx) {
    try { await audioCtx.close(); } catch (e) { console.error("Error closing AudioContext:", e); }
    audioCtx = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach(t => t.stop());
    mediaStream = null;
  }
}

async function stopMic() {
  // Send the last audio, stop the microphone, then ask the server for the final verdicts.
  if (floatQueue.length && ws && ws.readyState === WebSocket.OPEN) {
    try {
      ws.send(float32ToPCM16LE(concatFloat32(floatQueue)));
      floatQueue = [];
    } catch { }
  }
  await releaseAudio();

  if (ws && ws.readyState === WebSocket.OPEN) {
    updateUIState('stopping');
    const done = new Promise(res => { stopResolver = res; });
    ws.send(JSON.stringify({ type: 'stop' }));
    await Promise.race([done, new Promise(res => setTimeout(res, STOP_TIMEOUT_MS))]);
    stopResolver = null;
    try { ws.close(); } catch { }
  }

  updateUIState('idle');
  renderMushafPanel(currentWindowAyahs);
  logln("Stopped.");
  showSessionSummary();
  const sumBtn = $('showSummaryBtn');
  if (sumBtn) sumBtn.style.display = 'inline-block';
}

const micBtn = $('micBtn');
if (micBtn) micBtn.addEventListener('click', toggleMic);

const toggleBtn = $('toggleAdvanceBtn');
if (toggleBtn) toggleBtn.addEventListener('click', (e) => {
  autoAdvance = !autoAdvance;
  const tb = $('toggleAdvanceBtn');
  if (tb) tb.textContent = autoAdvance ? "Auto-Advance: ON" : "Auto-Advance: OFF";
  logln(`Auto-advance: ${autoAdvance ? 'ON' : 'OFF'}`);
});

const clearTagsBtn = $('clearTagsBtn');
if (clearTagsBtn) clearTagsBtn.addEventListener('click', () => {
  verseStatuses.clear();
  renderMushafPanel(currentWindowAyahs);
  logln("Cleared all classification tags.");
});

const nextBtn = $('nextBtn');
if (nextBtn) nextBtn.addEventListener('click', nextAyahOrFinish);

const apiKeyBtn = $('apiKeyBtn');
if (apiKeyBtn) apiKeyBtn.addEventListener('click', () => {
  const newKey = prompt("Update API Key:", localStorage.getItem("api_key") || "");
  if (newKey !== null) {
    localStorage.setItem("api_key", newKey);
    location.reload(); // Reload to apply new key
  }
});

const profileSelect = $('profileSelect');
if (profileSelect) {
  // Load saved profile
  const savedProfile = localStorage.getItem("profile");
  if (savedProfile) profileSelect.value = savedProfile;

  profileSelect.addEventListener('change', (e) => {
    const newProfile = e.target.value;
    localStorage.setItem("profile", newProfile);
    logln(`Profile changed to: ${newProfile}.`);
    // Applies to the words not judged yet; no need to reconnect.
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'profile', profile: newProfile }));
    }
  });
}

window.addEventListener('hashchange', () => {
  const m = location.hash.match(/^#(\d+):(\d+)$/);
  if (m) {
    if ($('surah')) $('surah').value = m[1];
    if ($('ayah')) $('ayah').value = m[2];
    windowStartAyah = Math.max(1, Number(m[2]) - 1);
    loadActiveAyah(Number(m[1]), Number(m[2])).catch(e => logln('Hash load error: ' + e.message));
  }
});

(function initFromURL() {
  const m = location.hash.match(/^#(\d+):(\d+)$/);
  if (m) {
    currentSurah = Number(m[1]);
    currentAyah = Number(m[2]);
  } else {
    const lsSurah = localStorage.getItem('currentSurah');
    const lsAyah = localStorage.getItem('currentAyah');
    if (lsSurah && lsAyah) {
      currentSurah = Number(lsSurah);
      currentAyah = Number(lsAyah);
    } else {
      currentSurah = 2;
      currentAyah = 1;
    }
  }

  if ($('surah')) $('surah').value = currentSurah;
  if ($('ayah')) $('ayah').value = currentAyah;
})();

windowStartAyah = Math.max(1, currentAyah - 1);

(async function boot() {
  await loadSurahList(); // Load metadata first
  logln(`[boot] surah=${currentSurah} ayah=${currentAyah}`);
  // Initial load
  await loadActiveAyah(currentSurah, currentAyah);
})();

// --- Session Summary Logic ---
const summaryModal = $('summaryModal');
const closeSummaryBtn = $('closeSummaryBtn');
const showSummaryBtn = $('showSummaryBtn');

if (closeSummaryBtn && summaryModal) {
  closeSummaryBtn.addEventListener('click', () => {
    summaryModal.close();
  });
}

if (showSummaryBtn) {
  showSummaryBtn.addEventListener('click', () => {
    showSessionSummary();
  });
}

async function showSessionSummary() {
  if (!summaryModal) return;

  // Fetch authoritative summary from backend
  let sessionData = null;
  try {
    const res = await fetch(`${API_BASE_HTTP}/api/session/${sessionId}/summary`);
    if (res.ok) {
      sessionData = await res.json();
    }
  } catch (e) {
    console.error("Failed to fetch session summary:", e);
  }

  // Use backend data if available, otherwise fallback (or show error/empty)
  // Logic below adapts backend structure to UI

  if (!sessionData || sessionData.error) {
    console.warn("Session data error:", sessionData);
    $('summaryDetails').innerHTML = `<p>Session data not available yet (Server: ${sessionData ? sessionData.error : 'No response'}).<br><small>Try recording a verse first.</small></p>`;
    summaryModal.showModal();
    return;
  }

  // sessionData.verses is a list of VerseResult
  const verses = sessionData.verses || [];

  // Ensure stats exist
  if (!sessionData.stats) {
    sessionData.stats = { matches: 0, substitutions: 0, deletions: 0, insertions: 0, count: 0, accuracy: 0.0 };
  }

  const accuracy = (sessionData.stats.accuracy * 100).toFixed(1);
  const profile = sessionData.profile || localStorage.getItem("profile") || "medium";
  const versesCount = verses.length;
  const totalTokens = sessionData.stats.count; // Words judged

  // Generate Verse Breakdown HTML
  let versesHtml = '<div class="verse-list">';
  verses.forEach(v => {
    const key = `${v.surah}:${v.ayah}`;

    // Store in local map for Detail View fallback/sync 
    // (Ensure frontend map is up to date for detail popup)
    verseStatuses.set(key, v.token_statuses);

    const vAcc = (v.accuracy * 100).toFixed(0);
    const m = v.mistakes;
    const partial = v.complete === false ? ` <small title="Stopped before the end of this ayah">(${v.recited}/${v.total} words)</small>` : '';

    versesHtml += `
      <div class="verse-item" onclick="showAyahDetail(${v.surah}, ${v.ayah})">
        <span class="verse-id">${v.surah}:${v.ayah}${partial}</span>
        <div class="verse-stats">
          <span class="stat-badge" title="Accuracy" style="color: ${vAcc > 90 ? '#4caf50' : '#ff9800'}">${vAcc}%</span>
          ${m.substitutions > 0 ? `<span class="stat-badge" style="color: #ff5252" title="Wrong Word">W:${m.substitutions}</span>` : ''}
          ${m.deletions > 0 ? `<span class="stat-badge" style="color: #ff5252" title="Skipped Word">S:${m.deletions}</span>` : ''}
          ${m.insertions > 0 ? `<span class="stat-badge" style="color: #f97316" title="Extra Word">E:${m.insertions}</span>` : ''}
        </div>
      </div>
    `;
  });
  versesHtml += '</div>';

  const html = `
    <div class="summary-grid">
      <div class="summary-item">
        <span class="summary-label">Profile</span>
        <span class="summary-value" style="text-transform: capitalize;">${profile}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">Overall Accuracy</span>
        <span class="summary-value" style="color: ${accuracy > 90 ? '#4caf50' : '#ff9800'}">${accuracy}%</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">Verses Recited</span>
        <span class="summary-value">${versesCount}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">Total Words</span>
        <span class="summary-value">${totalTokens}</span>
      </div>
    </div>
    
    <div style="margin-top: 1rem; border-top: 1px solid rgba(255,255,255,0.1); padding-top: 1rem;">
      <h3 style="font-size: 1rem; color: var(--text-secondary); margin-bottom: 0.5rem;">Mistake Breakdown (Total)</h3>
      <div class="summary-grid">
        <div class="summary-item">
          <span class="summary-label">Wrong Words</span>
          <span class="summary-value" style="color: #ff5252">${sessionData.stats.substitutions}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Skipped</span>
          <span class="summary-value" style="color: #ff5252">${sessionData.stats.deletions}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">Extra</span>
          <span class="summary-value" style="color: #f97316">${sessionData.stats.insertions}</span>
        </div>
      </div>
    </div>

    <h3 style="font-size: 1rem; color: var(--text-secondary); margin-top: 1.5rem; margin-bottom: 0.5rem;">Verse Breakdown (Click for Details)</h3>
    ${versesHtml}
  `;

  $('summaryDetails').innerHTML = html;
  summaryModal.showModal();
}

// --- Ayah Detail Logic ---
const ayahDetailModal = $('ayahDetailModal');
const closeAyahDetailBtn = $('closeAyahDetailBtn');
if (closeAyahDetailBtn && ayahDetailModal) {
  closeAyahDetailBtn.addEventListener('click', () => {
    ayahDetailModal.close();
  });
}

async function showAyahDetail(surah, ayah) {
  if (!ayahDetailModal) return;

  const key = `${surah}:${ayah}`;
  const statuses = verseStatuses.get(key);
  if (!statuses) return;

  const tokens = await fetchAyahTokens(surah, ayah);
  if (!tokens.length) return;

  $('ayahDetailTitle').textContent = `Surah ${surah}, Ayah ${ayah}`;

  // Render Content
  const contentEl = $('ayahDetailContent');
  contentEl.innerHTML = '';

  const ayahSpan = document.createElement('span');
  ayahSpan.className = 'ayah-span';

  tokens.forEach((tok, idx) => {
    const span = document.createElement('span');
    span.className = 'token';

    applyStatus(span, statuses[idx]);
    span.textContent = tok;
    ayahSpan.appendChild(span);
    ayahSpan.appendChild(document.createTextNode(' '));
  });
  contentEl.appendChild(ayahSpan);

  // Stats (final verdicts only)
  let vTotal = 0, vMatches = 0;
  let vMistakes = { s: 0, d: 0, n: 0 };

  statuses.forEach(item => {
    const status = (typeof item === 'object') ? item.status : item;
    const final = (typeof item === 'object') ? item.final !== false : true;
    if (!final || status === 'pending') { vMistakes.n++; return; }
    vTotal++;
    if (status === 'match') vMatches++;
    else if (status === 'substitution') vMistakes.s++;
    else if (status === 'deletion') vMistakes.d++;
  });
  const vAcc = vTotal > 0 ? ((vMatches / vTotal) * 100).toFixed(1) : 0;

  const statsHtml = `
    <div class="summary-item">
      <span class="summary-label">Accuracy</span>
      <span class="summary-value" style="color: ${vAcc > 90 ? '#4caf50' : '#ff9800'}">${vAcc}%</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">Substitutions</span>
      <span class="summary-value" style="color: #ff5252">${vMistakes.s}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">Deletions</span>
      <span class="summary-value" style="color: #ff5252">${vMistakes.d}</span>
    </div>
    <div class="summary-item">
      <span class="summary-label">Not recited</span>
      <span class="summary-value">${vMistakes.n}</span>
    </div>
  `;

  $('ayahDetailStats').innerHTML = statsHtml;
  ayahDetailModal.showModal();
}
