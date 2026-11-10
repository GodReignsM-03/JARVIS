// Jarvis client: listening, the "end of thought" buffer, interrupting, and speaking.
// ---------------------------------------------------------------------------
// FINISH_MS: how long a pause must last before Jarvis treats your sentence as finished.
// Too low cuts you off mid-thought; too high feels sluggish. Tune after a day of real use.
const FINISH_MS = 700;   // pause after unconfirmed words
const FINAL_MS = 350;    // shorter pause once the browser has confirmed the phrase is finished
const FOLLOW_UP_MS = 8000;   // after Jarvis answers, you can reply without saying "Jarvis" again
const WAKE = /\b(?:hey|hi|ok|okay)?\s*,?\s*jarvis\b[\s,.!?]*/i;
const INTERRUPT = /\b(stop|wait|hold on|jarvis|enough|quiet)\b/i;
const FILLER_MS = 1500;      // if he hasn't started answering by now, he acknowledges you
const FILLERS = ["One moment, sir.", "Right away, sir.", "Just a moment."];
// ---------------------------------------------------------------------------

const MUTE = new URLSearchParams(location.search).get("mute") === "1";
const SESSION = Math.random().toString(36).slice(2);
const $ = (id) => document.getElementById(id);

let audioCtx = null, analyser = null;
let mode = "tap";             // "tap" or "wake"
let phase = "idle";           // idle | listening | thinking | speaking | error
let awakeUntil = 0;           // wake mode: accepting a command until this time
let recog = null, recogOn = false, recogWanted = false;
let heard = "", finishTimer = null;
let gen = 0;                  // bumps on every interrupt; stale audio/requests are dropped
let chatAbort = null, currentSource = null, playQueue = Promise.resolve();
let lastHeardAt = 0;          // last moment speech recognition gave us words
let timing = null;            // per-question stopwatch

// ---------- UI helpers ----------
function setPhase(p, label) {
  phase = p;
  Orb.setState(p);
  const s = $("status");
  s.className = "status " + p;
  s.textContent = label || p;
}
function captionYou(t) { $("caption-you").textContent = t ? "“" + t + "”" : ""; }
function captionJarvis(t, append) {
  const el = $("caption-jarvis");
  el.textContent = append && el.textContent ? el.textContent + " " + t : t;
}

// ---------- Speaking ----------
async function fetchSpeech(text, myGen) {
  const r = await fetch("/api/tts", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }) });
  if (!r.ok) throw new Error("voice unavailable");
  if (timing && timing.gen === myGen && timing.ttsMs == null) timing.ttsMs = +r.headers.get("X-TTS-ms") || 0;
  const buf = await r.arrayBuffer();
  if (myGen !== gen) return null;
  return audioCtx.decodeAudioData(buf);
}

function playBuffer(buffer, myGen) {
  return new Promise((resolve) => {
    if (!buffer || myGen !== gen) return resolve();
    const src = audioCtx.createBufferSource();
    src.buffer = buffer;
    src.connect(analyser);
    currentSource = src;
    src.onended = () => { if (currentSource === src) currentSource = null; resolve(); };
    setPhase("speaking");
    src.start();
    if (timing && timing.gen === myGen && timing.brainAt && !timing.voiceAt) { timing.voiceAt = performance.now(); showTiming(); }
  });
}

// Queue a sentence: fetch its audio right away (in parallel), play in order.
function say(text, myGen = gen) {
  if (MUTE) return playQueue;
  const audio = fetchSpeech(text, myGen).catch(() => { $("d-voice").textContent = "offline"; return null; });
  playQueue = playQueue.then(() => audio).then((b) => playBuffer(b, myGen));
  return playQueue;
}

function interrupt() {
  gen++;
  if (chatAbort) chatAbort.abort();
  chatAbort = null;
  if (currentSource) { try { currentSource.stop(); } catch (_) {} currentSource = null; }
  playQueue = Promise.resolve();
  Orb.setLevel(0);
}

// Stopwatch: from the moment you stopped talking to the moment Jarvis's voice starts.
function showTiming() {
  const t = timing, f = (ms) => (ms / 1000).toFixed(2) + " s";
  if (!t || !t.voiceAt) return;
  $("m-total").textContent = f(t.voiceAt - t.heardAt);
  $("m-pause").textContent = f(t.sentAt - t.heardAt);
  $("m-brain").textContent = t.brainAt ? f(t.brainAt - t.sentAt) : "—";
  $("m-voice").textContent = t.brainAt ? f(t.voiceAt - t.brainAt) + (t.ttsMs != null ? " (" + f(t.ttsMs) + " making audio)" : "") : "—";
}

// A soft two-note chime the instant he hears you, so there's never dead air.
function chime() {
  if (MUTE || !audioCtx) return;
  const t = audioCtx.currentTime;
  [[880, 0], [1320, 0.09]].forEach(([f, d]) => {
    const o = audioCtx.createOscillator(), g = audioCtx.createGain();
    o.type = "sine"; o.frequency.value = f;
    g.gain.setValueAtTime(0, t + d);
    g.gain.linearRampToValueAtTime(0.06, t + d + 0.015);
    g.gain.exponentialRampToValueAtTime(0.0001, t + d + 0.22);
    o.connect(g); g.connect(audioCtx.destination);
    o.start(t + d); o.stop(t + d + 0.25);
  });
}

// Feed Jarvis's voice level into the orb.
function meter() {
  if (analyser) {
    const data = new Uint8Array(analyser.fftSize);
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (const v of data) { const x = (v - 128) / 128; sum += x * x; }
    Orb.setLevel(phase === "speaking" ? Math.min(1, Math.sqrt(sum / data.length) * 4) : 0);
  }
  requestAnimationFrame(meter);
}

// ---------- Talking to the brain ----------
async function ask(text, heardAt) {
  interrupt();
  const myGen = gen;
  timing = { gen: myGen, heardAt: heardAt || performance.now(), sentAt: performance.now() };
  captionYou(text);
  captionJarvis("");
  setPhase("thinking");
  chime();
  chatAbort = new AbortController();
  let gotAny = false;
  const filler = setTimeout(() => {
    if (!gotAny && myGen === gen) say(FILLERS[Math.floor(Math.random() * FILLERS.length)], myGen);
  }, FILLER_MS);
  try {
    const r = await fetch("/api/chat", { method: "POST", signal: chatAbort.signal,
      headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, session: SESSION }) });
    if (!r.ok) throw new Error("server error " + r.status);
    const reader = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i).replace(/^data: /, "");
        buf = buf.slice(i + 2);
        if (!line.trim() || myGen !== gen) continue;
        const ev = JSON.parse(line);
        if (ev.type === "sentence") {
          if (!gotAny && timing && timing.gen === myGen) timing.brainAt = performance.now();
          gotAny = true;
          clearTimeout(filler);
          captionJarvis(ev.text, true);
          say(ev.text, myGen);
        } else if (ev.type === "error") {
          captionJarvis(ev.message);
          setPhase("error", "error");
          say(ev.message, myGen);
        } else if (ev.type === "done") {
          $("m-tokens").textContent = ev.usage.input + " / " + ev.usage.output;
          $("m-cache").textContent = ev.usage.cache_read + " read";
          $("m-spend").textContent = "$" + ev.month_usd.toFixed(2) + (ev.fast ? " · fast" : "");
        }
      }
    }
  } catch (e) {
    clearTimeout(filler);
    if (e.name === "AbortError") return;
    captionJarvis("I can't reach my server, sir.");
    setPhase("error", "offline");
    return;
  }
  await playQueue;
  if (myGen !== gen) return;
  if (mode === "wake") awakeUntil = Date.now() + FOLLOW_UP_MS;
  afterTurn();
}

function afterTurn() {
  if (phase === "error") return;
  if (mode === "wake") setPhase(Date.now() < awakeUntil ? "listening" : "idle", Date.now() < awakeUntil ? "listening" : "say “Jarvis”");
  else setPhase("idle", "tap the orb");
}

// ---------- Listening ----------
function setupRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { $("d-mode").textContent = "No speech recognition — type instead"; return; }
  recog = new SR();
  recog.lang = "en-US";
  recog.continuous = true;
  recog.interimResults = true;

  recog.onresult = (e) => {
    let interim = "", finals = "";
    for (let i = e.resultIndex; i < e.results.length; i++) {
      const t = e.results[i][0].transcript;
      if (e.results[i].isFinal) finals += t + " "; else interim += t;
    }
    const live = (finals + interim).trim();
    if (live) lastHeardAt = performance.now();

    // While Jarvis talks, only interrupt words count (his own voice can leak into the mic).
    if (phase === "speaking" || phase === "thinking") {
      if (INTERRUPT.test(live)) { interrupt(); captionYou(""); setPhase("listening"); heard = ""; }
      return;
    }
    if (mode === "wake" && Date.now() > awakeUntil) {
      const m = live.match(WAKE);
      if (!m) return;
      awakeUntil = Date.now() + FOLLOW_UP_MS;
      setPhase("listening");
      heard = "";
      finals = finals.slice(finals.search(WAKE)).replace(WAKE, "");
    }
    heard += finals;
    if (live) captionYou(heard.trim() || interim);
    // The pause that truly ends your thought sends the whole combined sentence.
    clearTimeout(finishTimer);
    finishTimer = setTimeout(() => {
      const text = heard.trim();
      heard = "";
      if (!text) return;
      if (mode === "tap") stopListening();
      ask(text, lastHeardAt);
    }, finals.trim() && !interim ? FINAL_MS : FINISH_MS);
  };
  recog.onend = () => { recogOn = false; if (recogWanted) startRecog(); };
  recog.onerror = (e) => {
    if (e.error === "not-allowed") { recogWanted = false; setPhase("error", "mic blocked"); captionJarvis("I need microphone permission, sir."); }
  };
}
function startRecog() {
  if (!recog || recogOn) return;
  try { recog.start(); recogOn = true; } catch (_) {}
}
function startListening() { recogWanted = true; startRecog(); heard = ""; setPhase("listening"); }
function stopListening() { recogWanted = mode === "wake"; if (!recogWanted && recog) recog.stop(); }

// ---------- Controls ----------
$("orb").addEventListener("click", () => {
  if (phase === "speaking" || phase === "thinking") { interrupt(); afterTurn(); return; }
  if (mode === "wake") { awakeUntil = Date.now() + FOLLOW_UP_MS; setPhase("listening"); return; }
  if (phase === "listening") { stopListening(); afterTurn(); } else startListening();
});

function setMode(m) {
  mode = m;
  try { localStorage.setItem("jarvis.mode", m); } catch (_) {}
  const b = $("wake-toggle");
  b.setAttribute("aria-pressed", m === "wake");
  b.textContent = m === "wake" ? "“Hey Jarvis” on" : "“Hey Jarvis” off";
  $("d-mode").textContent = m === "wake" ? "Hey Jarvis (while open)" : "Tap to talk";
  if (m === "wake") { recogWanted = true; startRecog(); setPhase("idle", "say “Jarvis”"); }
  else { recogWanted = false; if (recog) recog.stop(); setPhase("idle", "tap the orb"); }
}
$("wake-toggle").addEventListener("click", () => setMode(mode === "wake" ? "tap" : "wake"));

$("type-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const t = $("type-input").value.trim();
  $("type-input").value = "";
  if (t) ask(t);
});

// ---------- Boot ----------
// Browsers block audio until you interact, so the greeting fires on the first tap.
async function boot() {
  $("boot").classList.add("hidden");
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 512;
  analyser.connect(audioCtx.destination);
  meter();
  setupRecognition();
  try {
    const h = await (await fetch("/api/health")).json();
    $("d-model").textContent = (h.brain_configured ? h.model : h.model + " (no key)") + (h.fast ? " · fast" : "");
    $("d-voice").textContent = h.voice_loaded ? "Jarvis H · AI 2.5" : "not installed";
  } catch (_) { $("d-model").textContent = "server offline"; }
  captionJarvis("Hello, sir.");
  await say("Hello, sir.");
  let saved = "wake";
  try { saved = localStorage.getItem("jarvis.mode") || "wake"; } catch (_) {}
  setMode(recog ? saved : "tap");   // "Hey Jarvis" is on by default
}
$("boot").addEventListener("click", boot, { once: true });
