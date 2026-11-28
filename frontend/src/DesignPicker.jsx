import React from "react";
import { Blend, Palette } from "lucide-react";

// Each palette carries a canvas and two accents in both color modes.
const palettes = [
  ["original", "تصميم الصورة", "Reference design", ["#000b19", "#27def7", "#009eff"], ["#edf5fd", "#006984", "#1559a8"]],
  ["noir", "نوار", "Noir", ["#0a140f", "#aff768", "#4edcbc"], ["#ecf4e8", "#346713", "#087762"]],
  ["atlas", "أطلس", "Atlas", ["#101a32", "#86a8ff", "#68dedb"], ["#eaf1ff", "#214cbd", "#007873"]],
  ["paper", "ورق", "Paper", ["#231817", "#f2a07e", "#efd38b"], ["#fff5e5", "#993f29", "#795908"]],
  ["velvet", "مخمل", "Velvet", ["#220e1b", "#f4a3c6", "#e6a2ff"], ["#f9e9ed", "#9b2654", "#77439d"]],
  ["orbit", "مدار", "Orbit", ["#171134", "#c3a5ff", "#81b5ff"], ["#eee9ff", "#6031bb", "#275eac"]],
  ["dune", "كثبان", "Dune", ["#251d10", "#f4cf75", "#e99775"], ["#f8edcd", "#76500d", "#a04231"]],
  ["fjord", "مضيق", "Fjord", ["#102430", "#9bdaf4", "#a9b7ff"], ["#eaf7fa", "#235f7e", "#4355a7"]],
  ["jade", "يشم", "Jade", ["#10281f", "#8be1ac", "#ecd483"], ["#e5f5ed", "#206447", "#796008"]],
  ["citrus", "حمضيات", "Citrus", ["#302013", "#ffab59", "#f7dd59"], ["#fff3d8", "#97400b", "#6d6507"]],
  ["ink", "حبر", "Ink", ["#15171b", "#d3d7df", "#a2c6f5"], ["#f3f4f4", "#40444e", "#3e648c"]],
  ["lagoon", "بحيرة", "Lagoon", ["#0b2528", "#76e7cf", "#ff9e8b"], ["#e3f6f1", "#006961", "#ac4336"]],
  ["iris", "سوسن", "Iris", ["#231a34", "#d4bdfb", "#e5a0cf"], ["#f5efff", "#6749a1", "#9a3f76"]],
  ["rose", "ورد", "Rose", ["#2c1420", "#ffa7b5", "#f9c991"], ["#fff0ed", "#a1254d", "#885318"]],
  ["ember", "جمر", "Ember", ["#211b19", "#eab48b", "#f58d7c"], ["#f5e9df", "#894526", "#a63b33"]],
  ["signal", "إشارة", "Signal", ["#13272a", "#f4e569", "#77dbd1"], ["#f5f4dd", "#69600e", "#20726c"]],
];

const byId = new Map(palettes.map((palette) => [palette[0], palette]));

export function validDesign(value, fallback = "original") {
  return byId.has(value) ? value : fallback;
}

export function applyPalette(root, design, mix, theme) {
  const mode = theme === "light" ? 4 : 3;
  const [canvas, accent, companion] = byId.get(design)[mode];
  root.style.setProperty("--palette-canvas", canvas);
  root.style.setProperty("--palette-accent", accent);
  root.style.setProperty("--palette-companion", mix === "auto" ? companion : byId.get(mix)[mode][1]);
  return canvas;
}

export function DesignPicker({ lang, design, mix, onChange, onMix }) {
  const ar = lang === "ar";
  const options = palettes.map(([id, nameAr, nameEn]) =>
    <option key={id} value={id}>{ar ? nameAr : nameEn}</option>);
  return (
    <div className="palette-controls">
      <label className="design-picker">
        <Palette size={16} aria-hidden="true" />
        <span>{ar ? "الألوان" : "Palette"}</span>
        <select aria-label={ar ? "لوحة الألوان" : "Color palette"} value={design} onChange={(event) => onChange(event.target.value)}>
          {options}
        </select>
      </label>
      <label className="design-picker palette-mix">
        <Blend size={16} aria-hidden="true" />
        <span>{ar ? "دمج مع" : "Mix with"}</span>
        <select aria-label={ar ? "دمج مع لوحة ألوان" : "Mix with a color palette"} value={mix} onChange={(event) => onMix(event.target.value)}>
          <option value="auto">{ar ? "تلقائي" : "Auto"}</option>
          {options}
        </select>
      </label>
    </div>
  );
}

