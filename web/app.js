// Jarvis client: listening, the "end of thought" buffer, interrupting, and speaking.
// ---------------------------------------------------------------------------
// FINISH_MS: how long a pause must last before Jarvis treats your sentence as finished.
// Too low cuts you off mid-thought; too high feels sluggish. Tune after a day of real use.
const FINISH_MS = 900;
const FOLLOW_UP_MS = 8000;   // after Jarvis answers, you can reply without saying "Jarvis" again
const WAKE = /\b(?:hey|hi|ok|okay)?\s*,?\s*jarvis\b[\s,.!?]*/i;
const INTERRUPT = /\b(stop|wait|hold on|jarvis|enough|quiet)\b/i;
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
async function ask(text) {
  interrupt();
  const myGen = gen;
  captionYou(text);
  captionJarvis("");
  setPhase("thinking");
  chatAbort = new AbortController();
  let gotAny = false;
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
          gotAny = true;
          captionJarvis(ev.text, true);
          say(ev.text, myGen);
        } else if (ev.type === "error") {
          captionJarvis(ev.message);
          setPhase("error", "error");
          say(ev.message, myGen);
        } else if (ev.type === "done") {
          $("m-first").textContent = ev.first_sentence_s + " s";
          $("m-total").textContent = ev.total_s + " s";
          $("m-tokens").textContent = ev.usage.input + " / " + ev.usage.output;
          $("m-cache").textContent = ev.usage.cache_read + " read";
        }
      }
    }
  } catch (e) {
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
      ask(text);
    }, FINISH_MS);
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

$("wake-toggle").addEventListener("click", (e) => {
  mode = mode === "wake" ? "tap" : "wake";
  e.target.setAttribute("aria-pressed", mode === "wake");
  e.target.textContent = mode === "wake" ? "“Hey Jarvis” on" : "“Hey Jarvis” off";
  $("d-mode").textContent = mode === "wake" ? "Hey Jarvis (while open)" : "Tap to talk";
  if (mode === "wake") { recogWanted = true; startRecog(); setPhase("idle", "say “Jarvis”"); }
  else { recogWanted = false; if (recog) recog.stop(); setPhase("idle", "tap the orb"); }
});

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
    $("d-model").textContent = h.brain_configured ? h.model : h.model + " (no key)";
    $("d-voice").textContent = h.voice_loaded ? "Jarvis H · AI 2.5" : "not installed";
  } catch (_) { $("d-model").textContent = "server offline"; }
  captionJarvis("Hello, sir.");
  await say("Hello, sir.");
  afterTurn();
}
$("boot").addEventListener("click", boot, { once: true });
