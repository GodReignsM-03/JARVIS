// Jarvis client: listening, the "end of thought" buffer, interrupting, and speaking.
// ---------------------------------------------------------------------------
// FINISH_MS: how long a pause must last before Jarvis treats your sentence as finished.
// Too low cuts you off mid-thought; too high feels sluggish. Tune after a day of real use.
const FINISH_MS = 700;   // pause after unconfirmed words
const FINAL_MS = 350;    // shorter pause once the browser has confirmed the phrase is finished
const FOLLOW_UP_MS = 8000;   // after Jarvis answers, you can reply without saying "Jarvis" again
const WAKE = /\b(?:hey|hi|ok|okay)?\s*,?\s*jarvis\b[\s,.!?]*/i;
const INTERRUPT = /\b(stop|wait|hold on|jarvis|enough|quiet)\b/i;
const FILLER_MS = 0;         // spoken "One moment, sir." while thinking: OFF (owner's preference). Set e.g. 1500 to turn on.
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
  const r = document.querySelector(".reactor");
  if (r) {
    r.classList.toggle("active", p === "speaking" || p === "thinking" || p === "listening");
    $("reactor-label").textContent = { idle: "Standing by", listening: "Listening · just talk", thinking: "Thinking",
      speaking: "Speaking", error: "Attention" }[p] || p;
  }
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

// Live subtitles: reveal a phrase word by word over the time its audio plays (longer words take longer).
function revealWords(text, seconds, myGen) {
  const words = text.split(/\s+/).filter(Boolean);
  const total = words.reduce((n, w) => n + w.length + 2, 0);
  let i = 0;
  const next = () => {
    if (myGen !== gen || i >= words.length) return;
    captionJarvis(words[i], true);
    const ms = (seconds * 1000 * (words[i].length + 2)) / total;
    i++;
    setTimeout(next, ms);
  };
  next();
}

function playBuffer(buffer, myGen, caption) {
  return new Promise((resolve) => {
    if (myGen !== gen) return resolve();
    if (!buffer) { if (caption) captionJarvis(caption, true); return resolve(); }  // no voice: show the words at once
    const src = audioCtx.createBufferSource();
    src.buffer = buffer;
    src.connect(analyser);
    currentSource = src;
    src.onended = () => { if (currentSource === src) currentSource = null; resolve(); };
    setPhase("speaking");
    src.start();
    if (caption) revealWords(caption, buffer.duration, myGen);
    if (timing && timing.gen === myGen && timing.brainAt && !timing.voiceAt) { timing.voiceAt = performance.now(); showTiming(); }
  });
}

// Queue a sentence: fetch its audio right away (in parallel), play in order.
// caption=true: the words appear on screen in time with the voice.
function say(text, myGen = gen, caption = false) {
  if (MUTE) { if (caption) captionJarvis(text, true); return playQueue; }
  const audio = fetchSpeech(text, myGen).catch(() => { $("d-voice").textContent = "offline"; return null; });
  playQueue = playQueue.then(() => audio).then((b) => playBuffer(b, myGen, caption ? text : null));
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

// Receipts: a small line for every action the database confirmed (or that failed).
const RECEIPT = {
  create_reminder: (r) => `Reminder saved: ${r.text}, ${r.due}`,
  update_reminder: (r) => `Reminder changed: ${r.text}, ${r.due}`,
  cancel_reminder: (r) => `Reminder #${r.id} cancelled`,
  log_routine: (r) => `Logged: ${r.routine}`,
  set_routine_interval: (r) => `${r.routine}: every ${r.every_days} days`,
  log_water: (r) => `Water today: ${r.today_ml} / ${r.goal_ml} ml`,
  set_water_goal: (r) => `Water goal: ${r.goal_ml} ml`,
  remember: (r) => `Remembered: ${r.fact}`,
  forget: (r) => `Forgotten #${r.id}`,
  save_note: (r) => `Note saved (${r.tag})`,
  set_nudges: (r) => `${r.kind} nudges ${r.on ? "on" : "off"}`,
  calendar_add: (r) => `Added to calendar: ${r.title}, ${r.when}`,
  calendar_move: (r) => `Moved: ${r.title}, ${r.when}`,
  calendar_delete: (r) => `Deleted from calendar: ${r.title}`,
};
function addReceipt(ev) {
  const fmt = RECEIPT[ev.tool];
  if (!fmt && ev.ok) return;  // look-ups (lists, status) don't need a receipt
  const el = document.createElement("div");
  el.className = "receipt" + (ev.ok ? "" : " fail");
  el.textContent = ev.ok ? "✓ " + fmt(ev.result) : "✗ Didn't work: " + (ev.result.error || ev.tool);
  $("receipts").appendChild(el);
}

// ---------- HUD panels (real data from the server) ----------
function esc(t) { const d = document.createElement("div"); d.textContent = t; return d.innerHTML; }
function fill(id, items, render, empty) {
  const el = $(id);
  el.innerHTML = items.length ? items.map((x) => "<li>" + render(x) + "</li>").join("") : `<li class="empty">${empty}</li>`;
}
async function refreshPanels() {
  try {
    const d = await (await fetch("/api/dashboard")).json();
    // "Thu 12 Nov 2026, 6:21 PM" -> "Thu 6:21 PM"
    const shortWhen = (s) => { const [day, time] = s.split(", "); return day.split(" ")[0] + " " + (time || ""); };
    fill("p-reminders", d.reminders, (r) => `<b>${esc(shortWhen(r.due))}</b><span>${esc(r.text)}</span>`, "Nothing scheduled.");
    fill("p-overdue", d.overdue, (r) => `<b>${Math.round(r.days_since)} days</b><span>${esc(r.routine)}</span>`, "All caught up.");
    const logText = (a) => (a.detail ? `${a.action}: ${a.detail}` : a.action).replace(/ -> .*$/, "").slice(0, 60);
    fill("p-log", d.activity, (a) => `<b>${esc(a.when.split(", ").pop())}</b><span>${esc(logText(a))}</span>`, "Nothing yet.");
    if (d.calendar_connected) {
      fill("p-calendar", d.calendar_today, (e) => `<b>${esc(e.when.includes("all day") ? "All day" : e.when.split(", ").pop().split(" to ")[0])}</b><span>${esc(e.title)}</span>`, "Nothing today.");
    }
    $("cal-btn").hidden = !!d.calendar_connected;
    const w = d.water;
    $("p-water").textContent = `${w.today_ml} / ${w.goal_ml} ml`;
    $("p-water-bar").style.width = Math.min(100, (100 * w.today_ml) / w.goal_ml) + "%";
    $("s-water").textContent = `${(w.today_ml / 1000).toFixed(1)} / ${(w.goal_ml / 1000).toFixed(1)} L`;
    $("s-next").textContent = d.reminders.length ? d.reminders[0].text.slice(0, 22) : "—";
    $("m-spend").textContent = "$" + d.month_usd.toFixed(2);
  } catch (_) {}
}
setInterval(() => {
  $("s-time").textContent = new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}, 1000);

// ---------- Google Calendar setup ----------
$("cal-btn").addEventListener("click", () => { $("cal-setup").hidden = false; });
$("cal-close").addEventListener("click", () => { $("cal-setup").hidden = true; });
$("cal-copy").addEventListener("click", async () => {
  try {
    const text = await (await fetch("/api/calendar/script")).text();
    await navigator.clipboard.writeText(text);
    $("cal-copied").textContent = "Copied.";
  } catch (e) { $("cal-copied").textContent = "Couldn't copy: " + e.message; }
});
$("cal-connect").addEventListener("click", async () => {
  $("cal-msg").textContent = "Testing the connection…";
  try {
    const r = await (await fetch("/api/calendar/connect", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: $("cal-url").value }) })).json();
    if (r.ok) {
      $("cal-msg").textContent = "Connected: " + (r.calendars || []).join(", ");
      captionJarvis("Your calendar is connected, sir.");
      say("Your calendar is connected, sir.");
      setTimeout(() => { $("cal-setup").hidden = true; refreshPanels(); }, 1500);
    } else $("cal-msg").textContent = "Not connected: " + (r.error || "unknown problem");
  } catch (e) { $("cal-msg").textContent = "Not connected: " + e.message; }
});

// ---------- Notifications (reminders reach the phone when Jarvis is closed) ----------
function b64ToBytes(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}
const isIOS = /iPhone|iPad|iPod/.test(navigator.userAgent);
const isStandalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;

async function setupNotifications() {
  if (!("serviceWorker" in navigator)) return;
  const reg = await navigator.serviceWorker.register("/sw.js");
  const btn = $("notify-btn");
  if (!("PushManager" in window)) {
    if (isIOS && !isStandalone) { btn.textContent = "Reminders: add to Home Screen"; btn.hidden = false; }
    return;
  }
  if (Notification.permission === "granted") { await subscribePush(reg); return; }
  if (Notification.permission === "denied") { btn.textContent = "Reminders blocked in settings"; btn.hidden = false; }
}

// Subscribes this device for reminders (silently, once permission exists). Safe to call repeatedly.
async function subscribePush(reg) {
  reg = reg || await navigator.serviceWorker.ready;
  if (await reg.pushManager.getSubscription()) return true;
  const { key } = await (await fetch("/api/push/key")).json();
  const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) });
  const r = await (await fetch("/api/push/subscribe", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(sub) })).json();
  return r.ok;
}

$("notify-btn").addEventListener("click", async () => {
  const btn = $("notify-btn");
  if (!("PushManager" in window)) {
    captionJarvis("On iPhone, tap Share, then Add to Home Screen, and open me from there. Then this button turns reminders on.");
    return;
  }
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") { captionJarvis("Notifications weren't allowed, sir. You can change that in Settings."); return; }
    const reg = await navigator.serviceWorker.ready;
    const { key } = await (await fetch("/api/push/key")).json();
    const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key) });
    const r = await (await fetch("/api/push/subscribe", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(sub) })).json();
    if (r.ok) { btn.hidden = true; captionJarvis("Reminders are on, sir. You should see a test notification now."); }
    else captionJarvis("I saved the setting, but the test notification didn't go through, sir.");
  } catch (e) {
    captionJarvis("I couldn't turn notifications on, sir: " + e.message);
  }
});

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
  $("receipts").textContent = "";
  setPhase("thinking");
  chime();
  chatAbort = new AbortController();
  let gotAny = false;
  const filler = FILLER_MS > 0 ? setTimeout(() => {
    if (!gotAny && myGen === gen) say(FILLERS[Math.floor(Math.random() * FILLERS.length)], myGen);
  }, FILLER_MS) : null;
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
          say(ev.text, myGen, true);
        } else if (ev.type === "action") {
          addReceipt(ev);
        } else if (ev.type === "error") {
          captionJarvis(ev.message);
          setPhase("error", "error");
          say(ev.message, myGen);
        } else if (ev.type === "done") {
          $("m-tokens").textContent = ev.usage.input + " / " + ev.usage.output;
          $("m-cache").textContent = ev.usage.cache_read + " read";
          $("m-spend").textContent = "$" + ev.month_usd.toFixed(2) + (ev.fast ? " · fast" : "");
          refreshPanels();
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
  b.textContent = m === "wake" ? "Mic on · say “Jarvis”" : "Mic off · tap the orb";
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
  // Browsers only allow the notification question during a tap, so it rides along with "Tap to wake".
  const permAsk = ("Notification" in window && "PushManager" in window && Notification.permission === "default")
    ? Notification.requestPermission() : null;
  $("boot").classList.add("hidden");
  audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  analyser = audioCtx.createAnalyser();
  analyser.fftSize = 512;
  analyser.connect(audioCtx.destination);
  meter();
  setupRecognition();
  fetch("/api/timezone", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tz: Intl.DateTimeFormat().resolvedOptions().timeZone }) }).catch(() => {});
  if (permAsk) permAsk.then(() => setupNotifications()).catch(() => {}); else setupNotifications().catch(() => {});
  refreshPanels();
  setInterval(refreshPanels, 30000);
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
