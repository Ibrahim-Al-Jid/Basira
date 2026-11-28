import React, { useEffect, useRef, useState } from "react";
import { Camera, Geometry, Mesh, Program, Renderer, Sphere, Texture, Transform, Vec3 } from "ogl";
import HeroGlobe from "./HeroGlobe";

// Real-time WebGL Earth (ogl). Public-domain NASA imagery (day, night lights, clouds, water mask, relief),
// lit by one sun with a soft terminator, ocean glint, cloud shadows, night lights and atmosphere scattering.
const vertex = `
attribute vec3 position; attribute vec3 normal; attribute vec2 uv;
uniform mat4 modelViewMatrix, projectionMatrix; uniform mat3 normalMatrix;
varying vec3 vN, vView; varying vec2 vUv;
void main(){ vN = normalize(normalMatrix * normal); vUv = uv;
  vec4 mv = modelViewMatrix * vec4(position, 1.); vView = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }
`;
const planetFragment = `precision highp float;
varying vec3 vN, vView; varying vec2 vUv;
uniform sampler2D uDay, uNight, uClouds, uWater, uRelief; uniform vec3 uSun; uniform float uLight, uShift;
void main(){
  vec3 n = normalize(vN), v = normalize(vView), s = normalize(uSun);
  vec2 uv = vec2(vUv.x, vUv.y);
  float e = 1. / 512.;
  float hx = texture2D(uRelief, uv + vec2(e, 0.)).r - texture2D(uRelief, uv - vec2(e, 0.)).r;
  float hy = texture2D(uRelief, uv + vec2(0., e)).r - texture2D(uRelief, uv - vec2(0., e)).r;
  vec3 up = abs(n.y) > .99 ? vec3(1., 0., 0.) : vec3(0., 1., 0.);
  vec3 tx = normalize(cross(up, n)), ty = cross(n, tx);
  vec3 nb = normalize(n - (tx * hx + ty * hy) * 2.2);
  float d = dot(nb, s), dn = dot(n, s);
  float day = smoothstep(-.14, .3, dn);
  float water = texture2D(uWater, uv).r;
  vec3 alb = texture2D(uDay, uv).rgb;
  // cloud shadow: sample the cloud layer shifted away from the sun
  float shadow = texture2D(uClouds, uv + vec2(-.004, .0) * (s.x > 0. ? 1. : -1.)).r;
  alb *= 1. - .38 * shadow;
  vec3 lit = alb * (max(d, 0.) * 1.05 + .02) * uLight;
  // warm twilight band along the terminator
  float tw = smoothstep(.0, .2, dn) * (1. - smoothstep(.2, .5, dn));
  lit = mix(lit, lit * vec3(1.25, .85, .65), tw * .6);
  // ocean glint
  vec3 hv = normalize(s + v);
  lit += water * pow(max(dot(n, hv), 0.), 90.) * .85 * day * vec3(1., .96, .88);
  lit += water * pow(max(dot(n, hv), 0.), 12.) * .08 * day;
  // night lights
  vec3 night = texture2D(uNight, uv).rgb;
  lit += night * vec3(1.15, .9, .6) * (1. - smoothstep(-.12, .12, dn)) * 1.25;
  // limb scattering on the lit side
  float rim = pow(1. - max(dot(n, v), 0.), 3.2);
  lit += mix(vec3(.12, .32, .8), vec3(.55, .75, 1.), day) * rim * (.2 + .9 * day);
  gl_FragColor = vec4(lit, 1.);
}`;
const cloudFragment = `precision highp float;
varying vec3 vN, vView; varying vec2 vUv;
uniform sampler2D uClouds; uniform vec3 uSun; uniform float uShift;
void main(){
  vec3 n = normalize(vN), s = normalize(uSun);
  float c = texture2D(uClouds, vec2(vUv.x + uShift, vUv.y)).r;
  c = smoothstep(.12, .85, c);
  float d = dot(n, s);
  float lightv = smoothstep(-.1, .35, d) * (.12 + .9 * max(d, 0.)) + .02;
  float a = c * .92;
  gl_FragColor = vec4(vec3(1., .99, .97) * lightv * a, a);
}`;
const atmosphereFragment = `precision highp float;
varying vec3 vN, vView; uniform vec3 uSun;
void main(){
  vec3 n = normalize(vN);
  float d = dot(-n, normalize(vView));
  float limb = pow(clamp(d / .52, 0., 1.), 3.4);
  float sunSide = smoothstep(-.35, .6, dot(n, normalize(uSun)) * -1.0 + .0) ;
  float lit = smoothstep(-.4, .5, -dot(n, normalize(uSun)));
  vec3 blue = vec3(.22, .5, 1.), warm = vec3(1., .55, .3);
  float tw = 1. - abs(dot(-n, normalize(uSun)));
  vec3 col = mix(blue, warm, pow(tw, 6.) * .55);
  float i = limb * (.2 + .95 * lit);
  gl_FragColor = vec4(col * i, i);
}`;
const starVertex = `attribute vec3 position; attribute float size; uniform mat4 modelViewMatrix, projectionMatrix; varying float vS;
void main(){ vS = size; gl_PointSize = size; gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.); }`;
const starFragment = `precision mediump float; varying float vS;
void main(){ float r = length(gl_PointCoord - .5) * 2.; float a = smoothstep(1., .0, r) * (.35 + .12 * vS);
  gl_FragColor = vec4(vec3(.85, .92, 1.) * a, a); }`;

const load = (url) => new Promise((resolve, reject) => {
  const image = new Image();
  image.onload = () => resolve(image); image.onerror = reject; image.src = url;
});

export default function Planet({ onFail }) {
  const host = useRef(null);
  useEffect(() => {
    const el = host.current;
    if (!el) return undefined;
    let renderer;
    const small = window.matchMedia("(max-width: 700px)").matches;
    try { renderer = new Renderer({ alpha: true, antialias: !small, dpr: Math.min(window.devicePixelRatio || 1, small ? 1.5 : 2), premultipliedAlpha: true }); }
    catch { onFail(); return undefined; }
    const gl = renderer.gl;
    if (!gl || gl.isContextLost()) { onFail(); return undefined; }
    gl.clearColor(0, 0, 0, 0);
    const canvas = gl.canvas;
    canvas.className = "planet-canvas";
    el.appendChild(canvas);
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const camera = new Camera(gl, { fov: 28 }); camera.position.set(0, 0, 7.3);
    const scene = new Transform();
    const sun = new Vec3(-1.5, .45, 1.1);
    const tex = (image, wrap = true) => new Texture(gl, { image, generateMipmaps: true, minFilter: gl.LINEAR_MIPMAP_LINEAR,
      wrapS: wrap ? gl.REPEAT : gl.CLAMP_TO_EDGE, anisotropy: 4 });
    let raf = 0, visible = true, last = performance.now(), vx = 0, spin = media.matches ? 0 : .09, drag = null, alive = true;
    let planet, clouds, stars, planetProgram, cloudProgram;
    const light = () => { if (planetProgram) planetProgram.uniforms.uLight.value = document.documentElement.dataset.theme === "light" ? 1.1 : 1; };
    const resize = () => {
      const b = el.getBoundingClientRect();
      if (!b.width || !b.height) return;
      renderer.setSize(b.width, b.height); camera.perspective({ aspect: b.width / b.height });
    };
    const render = () => { if (planet) renderer.render({ scene, camera }); };
    const frame = (time) => {
      raf = 0;
      if (!visible || document.hidden || !planet) return;
      const dt = Math.min(.05, (time - last) / 1000); last = time;
      if (!drag) { planet.rotation.y += (spin + vx) * dt; vx *= Math.pow(.04, dt); }
      clouds.rotation.y = planet.rotation.y; clouds.rotation.x = planet.rotation.x;
      cloudProgram.uniforms.uShift.value = (time / 1000) * .0009;
      stars.rotation.y = time / 1000 * .004;
      render();
      if (!media.matches || Math.abs(vx) > .002 || drag) raf = requestAnimationFrame(frame);
    };
    const kick = () => { if (!raf && alive) { last = performance.now(); raf = requestAnimationFrame(frame); } };
    const down = (e) => { drag = { x: e.clientX, y: e.clientY }; vx = 0; canvas.setPointerCapture?.(e.pointerId); canvas.classList.add("is-grabbing"); kick(); };
    const move = (e) => {
      if (!drag || !planet) return;
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
    const onMotion = () => { spin = media.matches ? 0 : .09; kick(); };
    const theme = new MutationObserver(() => { light(); render(); });
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    document.addEventListener("visibilitychange", onVis); media.addEventListener("change", onMotion);

    Promise.all(["day", "night", "clouds", "water", "relief"].map((name) => load(`/planet/${name}.webp`))).then(([day, night, cloudImg, water, relief]) => {
      if (!alive) return;
      const uDay = tex(day), uNight = tex(night), uClouds = tex(cloudImg), uWater = tex(water), uRelief = tex(relief);
      planetProgram = new Program(gl, { vertex, fragment: planetFragment,
        uniforms: { uDay: { value: uDay }, uNight: { value: uNight }, uClouds: { value: uClouds }, uWater: { value: uWater }, uRelief: { value: uRelief },
          uSun: { value: sun }, uLight: { value: 1 }, uShift: { value: 0 } } });
      planet = new Mesh(gl, { geometry: new Sphere(gl, { radius: 1.5, widthSegments: 128, heightSegments: 96 }), program: planetProgram });
      planet.setParent(scene);
      cloudProgram = new Program(gl, { vertex, fragment: cloudFragment, transparent: true, depthWrite: false,
        blendFunc: { src: gl.ONE, dst: gl.ONE_MINUS_SRC_ALPHA }, uniforms: { uClouds: { value: uClouds }, uSun: { value: sun }, uShift: { value: 0 } } });
      clouds = new Mesh(gl, { geometry: new Sphere(gl, { radius: 1.5 * 1.012, widthSegments: 96, heightSegments: 64 }), program: cloudProgram });
      clouds.setParent(scene);
      const shell = new Mesh(gl, { geometry: new Sphere(gl, { radius: 1.5 * 1.1, widthSegments: 64, heightSegments: 48 }),
        program: new Program(gl, { vertex, fragment: atmosphereFragment, transparent: true, cullFace: gl.FRONT, depthWrite: false,
          blendFunc: { src: gl.ONE, dst: gl.ONE_MINUS_SRC_ALPHA }, uniforms: { uSun: { value: sun } } }) });
      shell.setParent(scene);
      const count = small ? 260 : 520, pos = new Float32Array(count * 3), size = new Float32Array(count);
      for (let i = 0; i < count; i += 1) {
        const u = Math.random() * 2 - 1, t = Math.random() * Math.PI * 2, r = Math.sqrt(1 - u * u);
        pos.set([r * Math.cos(t) * 24, u * 24, r * Math.sin(t) * 24], i * 3); size[i] = 1.2 + Math.random() * 2.2;
      }
      stars = new Mesh(gl, { mode: gl.POINTS, geometry: new Geometry(gl, { position: { size: 3, data: pos }, size: { size: 1, data: size } }),
        program: new Program(gl, { vertex: starVertex, fragment: starFragment, transparent: true, depthWrite: false, blendFunc: { src: gl.ONE, dst: gl.ONE_MINUS_SRC_ALPHA } }) });
      stars.setParent(scene);
      planet.rotation.x = .32; planet.rotation.y = 2.3; clouds.rotation.x = .32; clouds.rotation.y = 2.3;
      light(); resize(); render(); el.classList.add("ready"); kick();
    }).catch(() => { if (alive) onFail(); });
    return () => {
      alive = false;
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
