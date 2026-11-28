import React, { useEffect, useRef, useState } from "react";
import { Camera, Mesh, Program, Renderer, Sphere, Transform, Vec3 } from "ogl";
import HeroGlobe from "./HeroGlobe";

// Real-time WebGL planet (ogl, ~30 kB). Everything is procedural: no texture download.
// Lit by one sun, with ocean glints, clouds, night-side city lights and an atmosphere.
const noise = `
float h(vec3 p){ p = fract(p * .3183099 + .1); p *= 17.; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
float vn(vec3 x){ vec3 i = floor(x), f = fract(x); f = f * f * (3. - 2. * f);
  return mix(mix(mix(h(i), h(i + vec3(1,0,0)), f.x), mix(h(i + vec3(0,1,0)), h(i + vec3(1,1,0)), f.x), f.y),
             mix(mix(h(i + vec3(0,0,1)), h(i + vec3(1,0,1)), f.x), mix(h(i + vec3(0,1,1)), h(i + vec3(1,1,1)), f.x), f.y), f.z); }
float fbm(vec3 p){ float a = .5, s = 0.; for (int i = 0; i < 5; i++) { s += a * vn(p); p = p * 2.03 + 7.1; a *= .5; } return s; }
`;
const vertex = `
attribute vec3 position; attribute vec3 normal;
uniform mat4 modelViewMatrix, projectionMatrix; uniform mat3 normalMatrix;
varying vec3 vPos, vN, vView;
void main(){ vPos = position; vN = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(position, 1.); vView = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }
`;
const planetFragment = `precision highp float;
varying vec3 vPos, vN, vView; uniform vec3 uSun; uniform float uTime, uLight;
${noise}
void main(){
  vec3 p = normalize(vPos), n = normalize(vN);
  float land = smoothstep(.5, .56, fbm(p * 2.2 + 3.));
  float lat = abs(p.y), ice = smoothstep(.78, .9, lat + (fbm(p * 5.) - .5) * .18);
  float dry = fbm(p * 4. + 9.);
  vec3 ocean = mix(vec3(.01,.08,.2), vec3(.02,.28,.5), fbm(p * 3.) );
  vec3 ground = mix(vec3(.05,.34,.3), vec3(.5,.42,.25), smoothstep(.35, .7, dry));
  vec3 col = mix(ocean, ground, land); col = mix(col, vec3(.9,.95,1.), ice);
  float cloud = smoothstep(.58, .82, fbm(p * 3.4 + vec3(uTime * .012, 0., 0.) + 20.));
  float d = dot(n, normalize(uSun));
  float day = smoothstep(-.08, .3, d);
  vec3 lit = col * (.08 + .92 * max(d, 0.)) * uLight;
  lit = mix(lit, vec3(1.) * (.1 + .9 * max(d, 0.)), cloud * .42 * day);
  vec3 hv = normalize(normalize(uSun) + vView);
  lit += (1. - land) * (1. - ice) * pow(max(dot(n, hv), 0.), 70.) * .7 * day;
  float city = step(.74, fbm(p * 26.)) * land * (1. - day) * (1. - ice) * smoothstep(.45, .6, fbm(p * 5. + 4.));
  lit += vec3(1., .78, .35) * city * .9;
  float rim = pow(1. - max(dot(n, vView), 0.), 3.);
  lit += vec3(.1,.55,1.) * rim * (.15 + .6 * day);
  gl_FragColor = vec4(lit, 1.);
}`;
const atmosphereFragment = `precision highp float;
varying vec3 vN, vView; uniform vec3 uColor;
void main(){ float d = dot(-normalize(vN), normalize(vView));
  float i = pow(clamp(d / .5, 0., 1.), 3.2) * .9;
  gl_FragColor = vec4(uColor * i, i); }`;

export default function Planet({ onFail }) {
  const host = useRef(null);
  useEffect(() => {
    const el = host.current;
    if (!el) return undefined;
    let renderer;
    try { renderer = new Renderer({ alpha: true, antialias: true, dpr: Math.min(window.devicePixelRatio || 1, 2), premultipliedAlpha: true }); }
    catch { onFail(); return undefined; }
    const gl = renderer.gl;
    if (!gl || gl.isContextLost()) { onFail(); return undefined; }
    gl.clearColor(0, 0, 0, 0);
    const canvas = gl.canvas;
    canvas.className = "planet-canvas";
    el.appendChild(canvas);
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const camera = new Camera(gl, { fov: 28 }); camera.position.set(0, 0, 8.4);
    const scene = new Transform();
    const planetProgram = new Program(gl, { vertex, fragment: planetFragment,
      uniforms: { uSun: { value: new Vec3(-1.4, .5, 1.1) }, uTime: { value: 0 }, uLight: { value: 1 } } });
    const planet = new Mesh(gl, { geometry: new Sphere(gl, { radius: 1.5, widthSegments: 96, heightSegments: 64 }), program: planetProgram });
    planet.setParent(scene);
    const atmosphere = new Mesh(gl, { geometry: new Sphere(gl, { radius: 1.5 * 1.12, widthSegments: 64, heightSegments: 48 }),
      program: new Program(gl, { vertex, fragment: atmosphereFragment, transparent: true, cullFace: gl.FRONT,
        blendFunc: { src: gl.ONE, dst: gl.ONE_MINUS_SRC_ALPHA }, uniforms: { uColor: { value: new Vec3(.15, .6, 1) } } }) });
    atmosphere.setParent(scene);
    const light = () => { planetProgram.uniforms.uLight.value = document.documentElement.dataset.theme === "light" ? 1.12 : 1; };
    light();
    const resize = () => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height) return;
      renderer.setSize(b.width, b.height); camera.perspective({ aspect: b.width / b.height });
    };
    let raf = 0, visible = true, last = performance.now(), vx = 0, spin = media.matches ? 0 : .12, drag = null;
    planet.rotation.x = .38; planet.rotation.y = 2.2;
    const render = () => { renderer.render({ scene, camera }); };
    const frame = (time) => {
      raf = 0;
      if (!visible || document.hidden) return;
      const dt = Math.min(.05, (time - last) / 1000); last = time;
      if (!drag) { planet.rotation.y += (spin + vx) * dt; vx *= Math.pow(.04, dt); }
      planetProgram.uniforms.uTime.value = time / 1000;
      render();
      if (!media.matches || Math.abs(vx) > .002 || drag) raf = requestAnimationFrame(frame);
    };
    const kick = () => { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } };
    const down = (e) => { drag = { x: e.clientX, y: e.clientY }; vx = 0; canvas.setPointerCapture?.(e.pointerId); canvas.classList.add("is-grabbing"); kick(); };
    const move = (e) => {
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag = { x: e.clientX, y: e.clientY };
      planet.rotation.y += dx * .008; vx = dx * .5;
      planet.rotation.x = Math.max(-.9, Math.min(.9, planet.rotation.x + dy * .005));
      kick();
    };
    const up = () => { drag = null; canvas.classList.remove("is-grabbing"); kick(); };
    canvas.addEventListener("pointerdown", down); canvas.addEventListener("pointermove", move);
    canvas.addEventListener("pointerup", up); canvas.addEventListener("pointercancel", up);
    const lost = (e) => { e.preventDefault(); onFail(); };
    canvas.addEventListener("webglcontextlost", lost);
    const ro = new ResizeObserver(() => { resize(); render(); });
    ro.observe(el);
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; if (visible) kick(); });
    io.observe(el);
    const onVis = () => { if (!document.hidden) kick(); };
    const onMotion = () => { spin = media.matches ? 0 : .12; kick(); };
    const theme = new MutationObserver(() => { light(); render(); });
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    document.addEventListener("visibilitychange", onVis); media.addEventListener("change", onMotion);
    resize(); render(); kick();
    return () => {
      cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); theme.disconnect();
      document.removeEventListener("visibilitychange", onVis); media.removeEventListener("change", onMotion);
      canvas.removeEventListener("webglcontextlost", lost);
      gl.getExtension("WEBGL_lose_context")?.loseContext(); canvas.remove();
    };
  }, []);
  return <div ref={host} className="planet" />;
}

export function PlanetOrFallback() {
  const [failed, setFailed] = useState(false);
  return failed ? <HeroGlobe /> : <Planet onFail={() => setFailed(true)} />;
}
