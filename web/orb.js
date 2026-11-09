// The orb: a rotating sphere of glowing particles. States: idle, listening, thinking, speaking, error.
// No libraries; plain canvas so it runs smoothly on a phone.
(function () {
  const canvas = document.getElementById("orb");
  const ctx = canvas.getContext("2d");
  const N = 900;
  const pts = [];
  // Fibonacci sphere: evenly spread points
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2;
    const r = Math.sqrt(1 - y * y);
    const t = i * Math.PI * (3 - Math.sqrt(5));
    pts.push({ x: Math.cos(t) * r, y, z: Math.sin(t) * r, j: Math.random() * Math.PI * 2 });
  }

  const STATES = {
    idle:      { speed: 0.12, glow: 0.45, spread: 0.00, hue: 192 },
    listening: { speed: 0.25, glow: 0.85, spread: 0.04, hue: 190 },
    thinking:  { speed: 0.90, glow: 0.70, spread: -0.06, hue: 205 },
    speaking:  { speed: 0.30, glow: 1.00, spread: 0.00, hue: 188 },
    error:     { speed: 0.10, glow: 0.60, spread: 0.00, hue: 30 },
  };
  let state = "idle";
  let cur = { ...STATES.idle };
  let level = 0;          // live audio level 0..1 (mic or Jarvis's voice)
  let angle = 0;
  let last = performance.now();

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
  }
  window.addEventListener("resize", resize);
  resize();

  function frame(now) {
    const dt = Math.min((now - last) / 1000, 0.05);
    last = now;
    const target = STATES[state];
    for (const k of ["speed", "glow", "spread", "hue"]) cur[k] += (target[k] - cur[k]) * Math.min(1, dt * 4);
    angle += cur.speed * dt;

    const w = canvas.width, h = canvas.height;
    const R = Math.min(w, h) * 0.34 * (1 + cur.spread + level * 0.12);
    ctx.clearRect(0, 0, w, h);

    // core glow
    const g = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, R * 1.25);
    g.addColorStop(0, `hsla(${cur.hue},100%,70%,${0.18 * cur.glow + level * 0.25})`);
    g.addColorStop(1, "hsla(200,100%,50%,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);

    const ca = Math.cos(angle), sa = Math.sin(angle);
    const tilt = 0.35, ct = Math.cos(tilt), st = Math.sin(tilt);
    ctx.globalCompositeOperation = "lighter";
    for (const p of pts) {
      const wob = 1 + Math.sin(now / 600 + p.j) * 0.015 + level * 0.08 * Math.sin(now / 90 + p.j * 3);
      let x = p.x * ca - p.z * sa, z = p.x * sa + p.z * ca, y = p.y;
      const y2 = y * ct - z * st; z = y * st + z * ct; y = y2;
      const depth = (z + 1.6) / 2.6;               // 0..1, near = bright
      const sx = w / 2 + x * R * wob, sy = h / 2 + y * R * wob;
      const size = (0.6 + depth * 1.6) * (w / 600);
      ctx.fillStyle = `hsla(${cur.hue},100%,${55 + depth * 30}%,${(0.15 + depth * 0.75) * cur.glow})`;
      ctx.beginPath();
      ctx.arc(sx, sy, size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  window.Orb = {
    setState(s) { if (STATES[s]) state = s; },
    setLevel(v) { level = Math.max(0, Math.min(1, v)); },
  };
})();
