import React, { useEffect, useRef } from "react";

// Decorative rotating globe for the entry page. Plain canvas 2D, no library.
// Static when the user prefers reduced motion; paused when off screen or hidden.
const NODES = [[30, 31], [51, 0], [40, -74], [1, 103], [-23, -46], [35, 139], [-33, 151], [25, 55]];
const ARCS = [[0, 1], [1, 2], [0, 3], [2, 4], [3, 5], [5, 6], [7, 0], [1, 7]];

function toVec(lat, lon) {
  const a = (lat * Math.PI) / 180, o = (lon * Math.PI) / 180;
  return [Math.cos(a) * Math.sin(o), Math.sin(a), Math.cos(a) * Math.cos(o)];
}
function slerp(a, b, t) {
  const d = Math.min(1, Math.max(-1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
  const w = Math.acos(d), s = Math.sin(w) || 1;
  const k1 = Math.sin((1 - t) * w) / s, k2 = Math.sin(t * w) / s;
  const lift = 1 + 0.16 * Math.sin(Math.PI * t) * (w / Math.PI);
  return [(a[0] * k1 + b[0] * k2) * lift, (a[1] * k1 + b[1] * k2) * lift, (a[2] * k1 + b[2] * k2) * lift];
}

export default function HeroGlobe() {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const dots = [];
    const n = 520, golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < n; i += 1) {
      const y = 1 - (i / (n - 1)) * 2, r = Math.sqrt(1 - y * y), th = golden * i;
      dots.push([Math.cos(th) * r, y, Math.sin(th) * r]);
    }
    const nodes = NODES.map(([la, lo]) => toVec(la, lo));
    const tilt = 0.38;
    let w = 0, h = 0, raf = 0, visible = true, angle = 0.6, last = 0;
    let accent = "34,211,238", second = "56,189,248";

    const readColors = () => {
      const light = document.documentElement.dataset.theme === "light";
      accent = light ? "0,105,132" : "39,222,247";
      second = light ? "21,89,168" : "0,158,255";
    };
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const box = canvas.getBoundingClientRect();
      w = box.width; h = box.height;
      canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    const project = (v, cy, sy, cx, sx, R, cxp, cyp) => {
      const x1 = v[0] * cy + v[2] * sy, z1 = -v[0] * sy + v[2] * cy;
      const y2 = v[1] * cx - z1 * sx, z2 = v[1] * sx + z1 * cx;
      return [cxp + x1 * R, cyp - y2 * R, z2];
    };
    const draw = (time) => {
      ctx.clearRect(0, 0, w, h);
      const R = Math.min(w, h) * 0.38, cxp = w / 2, cyp = h / 2;
      const cy = Math.cos(angle), sy = Math.sin(angle), cx = Math.cos(tilt), sx = Math.sin(tilt);
      const glow = ctx.createRadialGradient(cxp, cyp, R * 0.9, cxp, cyp, R * 1.28);
      glow.addColorStop(0, `rgba(${accent},0.22)`); glow.addColorStop(1, `rgba(${accent},0)`);
      ctx.fillStyle = glow; ctx.beginPath(); ctx.arc(cxp, cyp, R * 1.28, 0, 7); ctx.fill();
      const body = ctx.createRadialGradient(cxp - R * 0.3, cyp - R * 0.35, R * 0.1, cxp, cyp, R);
      body.addColorStop(0, `rgba(${second},0.28)`); body.addColorStop(1, `rgba(${second},0.04)`);
      ctx.fillStyle = body; ctx.beginPath(); ctx.arc(cxp, cyp, R, 0, 7); ctx.fill();
      ctx.strokeStyle = `rgba(${accent},0.55)`; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(cxp, cyp, R, 0, 7); ctx.stroke();
      for (const d of dots) {
        const p = project(d, cy, sy, cx, sx, R, cxp, cyp);
        const a = p[2] > 0 ? 0.35 + 0.65 * p[2] : 0.08;
        ctx.fillStyle = `rgba(${second},${a.toFixed(2)})`;
        ctx.fillRect(p[0] - 1.1, p[1] - 1.1, 2.2, 2.2);
      }
      ctx.lineWidth = 1.2;
      ARCS.forEach(([i, j], k) => {
        const pts = [];
        for (let t = 0; t <= 1.001; t += 0.05) pts.push(project(slerp(nodes[i], nodes[j], t), cy, sy, cx, sx, R, cxp, cyp));
        ctx.strokeStyle = `rgba(${accent},0.45)`; ctx.beginPath();
        let pen = false;
        for (const p of pts) { if (p[2] > -0.05) { pen ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]); pen = true; } else pen = false; }
        ctx.stroke();
        const t = ((time / 2600 + k * 0.37) % 1);
        const q = project(slerp(nodes[i], nodes[j], t), cy, sy, cx, sx, R, cxp, cyp);
        if (q[2] > 0) { ctx.fillStyle = `rgba(${accent},0.95)`; ctx.beginPath(); ctx.arc(q[0], q[1], 2.2, 0, 7); ctx.fill(); }
      });
      nodes.forEach((v, i) => {
        const p = project(v, cy, sy, cx, sx, R, cxp, cyp);
        if (p[2] <= 0) return;
        const pulse = (time / 1800 + i * 0.21) % 1;
        ctx.strokeStyle = `rgba(${accent},${(0.6 * (1 - pulse)).toFixed(2)})`;
        ctx.beginPath(); ctx.arc(p[0], p[1], 3 + pulse * 11, 0, 7); ctx.stroke();
        ctx.fillStyle = `rgb(${accent})`; ctx.beginPath(); ctx.arc(p[0], p[1], 3, 0, 7); ctx.fill();
      });
    };
    const frame = (time) => {
      raf = 0;
      if (!visible || document.hidden || media.matches) return;
      angle += Math.min(80, time - last) * 0.00022; last = time;
      draw(time);
      raf = requestAnimationFrame(frame);
    };
    const start = () => {
      if (raf) return;
      if (media.matches) { draw(0); return; }
      last = performance.now(); raf = requestAnimationFrame(frame);
    };
    readColors(); resize(); draw(0); start();
    const ro = new ResizeObserver(() => { resize(); draw(performance.now()); });
    ro.observe(canvas);
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) start(); });
    io.observe(canvas);
    const onVis = () => { if (!document.hidden) start(); };
    const onMotion = () => { readColors(); if (media.matches) { cancelAnimationFrame(raf); raf = 0; draw(0); } else start(); };
    const theme = new MutationObserver(() => { readColors(); if (media.matches) draw(0); });
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    document.addEventListener("visibilitychange", onVis);
    media.addEventListener("change", onMotion);
    return () => {
      cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); theme.disconnect();
      document.removeEventListener("visibilitychange", onVis);
      media.removeEventListener("change", onMotion);
    };
  }, []);
  return <canvas ref={ref} className="hero-globe" aria-hidden="true" />;
}
