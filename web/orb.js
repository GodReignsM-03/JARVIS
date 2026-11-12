// The orb (v2): a sphere of light streaks orbiting a bright core, with sweeping arcs.
// States: idle, listening, thinking, speaking, error. Plain canvas, no libraries.
(function () {
  const canvas = document.getElementById("orb");
  const ctx = canvas.getContext("2d");
  const small = matchMedia("(max-width: 820px)").matches;
  const N = small ? 650 : 1300;

  // Each streak travels a great circle around the sphere: pos(t) = b*cos(t) + c*sin(t)
  const streaks = [];
  for (let i = 0; i < N; i++) {
    let ax = [Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5];
    let al = Math.hypot(...ax); ax = ax.map((v) => v / al);
    let b = [Math.random() - 0.5, Math.random() - 0.5, Math.random() - 0.5];
    const d = b[0] * ax[0] + b[1] * ax[1] + b[2] * ax[2];
    b = b.map((v, k) => v - d * ax[k]); const bl = Math.hypot(...b); b = b.map((v) => v / bl);
    const c = [ax[1] * b[2] - ax[2] * b[1], ax[2] * b[0] - ax[0] * b[2], ax[0] * b[1] - ax[1] * b[0]];
    streaks.push({ b, c, t: Math.random() * Math.PI * 2, w: (0.25 + Math.random()) * (Math.random() < 0.5 ? 1 : -1),
      r: 0.78 + Math.random() * 0.26, len: 0.05 + Math.random() * 0.12, warm: Math.random() < 0.18 });
  }
  const arcs = [0, 1, 2].map((i) => ({ rot: i * 1.1, tilt: 0.25 + i * 0.22, speed: 0.07 + i * 0.03, span: 1.6 + i * 0.5 }));

  const STATES = {
    idle:      { speed: 0.35, glow: 0.55, core: 0.55, spread: 0.0 },
    listening: { speed: 0.55, glow: 0.85, core: 0.80, spread: 0.04 },
    thinking:  { speed: 1.60, glow: 0.80, core: 0.95, spread: -0.05 },
    speaking:  { speed: 0.70, glow: 1.00, core: 1.00, spread: 0.0 },
    error:     { speed: 0.20, glow: 0.50, core: 0.40, spread: 0.0 },
  };
  let state = "idle", cur = { ...STATES.idle }, level = 0, spin = 0, last = performance.now();

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2), r = canvas.getBoundingClientRect();
    canvas.width = r.width * dpr; canvas.height = r.height * dpr;
  }
  addEventListener("resize", resize); resize();

  function frame(now) {
    const dt = Math.min((now - last) / 1000, 0.05); last = now;
    const tg = STATES[state];
    for (const k in tg) cur[k] += (tg[k] - cur[k]) * Math.min(1, dt * 3);
    spin += dt * 0.08;
    const w = canvas.width, h = canvas.height, cx = w / 2, cy = h / 2;
    const R = Math.min(w, h) * 0.40 * (1 + cur.spread + level * 0.08);
    ctx.clearRect(0, 0, w, h);

    // deep blue halo
    let g = ctx.createRadialGradient(cx, cy, R * 0.2, cx, cy, R * 1.35);
    g.addColorStop(0, `rgba(40,110,170,${0.22 * cur.glow})`);
    g.addColorStop(1, "rgba(10,30,60,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);

    const cs = Math.cos(spin), sn = Math.sin(spin), tilt = 0.4, ct = Math.cos(tilt), st = Math.sin(tilt);
    const proj = (p, r) => {
      let x = p[0] * cs - p[2] * sn, z = p[0] * sn + p[2] * cs, y = p[1];
      const y2 = y * ct - z * st; z = y * st + z * ct; y = y2;
      return [cx + x * R * r, cy + y * R * r, z];
    };
    const pos = (s, t) => [s.b[0] * Math.cos(t) + s.c[0] * Math.sin(t), s.b[1] * Math.cos(t) + s.c[1] * Math.sin(t),
                           s.b[2] * Math.cos(t) + s.c[2] * Math.sin(t)];

    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";
    const lw = Math.max(1, w / 900);
    for (const s of streaks) {
      s.t += s.w * cur.speed * dt * (1 + level * 1.5);
      const r = s.r * (1 + level * 0.06 * Math.sin(now / 120 + s.r * 40));
      const a = proj(pos(s, s.t), r), b = proj(pos(s, s.t - s.len * Math.sign(s.w)), r);
      const depth = (a[2] + 1.4) / 2.4;
      const alpha = (0.12 + depth * 0.7) * cur.glow;
      ctx.strokeStyle = s.warm ? `rgba(255,236,170,${alpha})` : `rgba(150,${200 + depth * 40 | 0},255,${alpha})`;
      ctx.lineWidth = lw * (0.6 + depth * 0.9);
      ctx.beginPath(); ctx.moveTo(b[0], b[1]); ctx.lineTo(a[0], a[1]); ctx.stroke();
    }

    // sweeping arcs
    for (const arc of arcs) {
      arc.rot += arc.speed * dt * (0.6 + cur.speed);
      ctx.save(); ctx.translate(cx, cy); ctx.rotate(arc.rot);
      ctx.strokeStyle = `rgba(255,240,190,${0.7 * cur.glow})`; ctx.lineWidth = lw * 2.2;
      ctx.shadowColor = "rgba(255,230,160,0.8)"; ctx.shadowBlur = 8 * lw;
      ctx.beginPath(); ctx.ellipse(0, 0, R * 0.98, R * arc.tilt, 0, 0, arc.span); ctx.stroke();
      ctx.restore();
    }

    // bright core
    const coreR = R * (0.12 + level * 0.06);
    g = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR * 3);
    g.addColorStop(0, `rgba(255,255,245,${1.0 * cur.core})`);
    g.addColorStop(0.12, `rgba(255,250,215,${0.95 * cur.core})`);
    g.addColorStop(0.35, `rgba(255,232,150,${0.45 * cur.core})`);
    g.addColorStop(1, "rgba(120,200,255,0)");
    ctx.fillStyle = g; ctx.beginPath(); ctx.arc(cx, cy, coreR * 3, 0, Math.PI * 2); ctx.fill();
    if (state === "error") { ctx.fillStyle = "rgba(255,120,80,0.15)"; ctx.fillRect(0, 0, w, h); }

    ctx.globalCompositeOperation = "source-over";
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);

  window.Orb = { setState(s) { if (STATES[s]) state = s; }, setLevel(v) { level = Math.max(0, Math.min(1, v)); } };
})();
