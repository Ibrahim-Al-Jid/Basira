import React from "react";
import {
  CircleDot,
  GitBranch,
  GitFork,
  Layers3,
  Maximize2,
  Minimize2,
  ScanLine,
  ShieldCheck,
  Waypoints,
  FileText,
} from "lucide-react";
import { agents, labelOf, roleOf } from "./data";

const icons = {
  orchestrator: Waypoints,
  planning: GitFork,
  analysis: ScanLine,
  validation: ShieldCheck,
  reporting: FileText,
};
const englishBranches = { scripts: "Scripts", forms: "Forms", document: "Document" };
const graphCopy = {
  ar: {
    title: "شبكة التنفيذ", reduce: "تصغير الشبكة", expand: "تكبير الشبكة",
    connecting: "جارٍ الاتصال بالمحرك", waiting: "بانتظار بدء الفحص",
    stopped: "توقف التشغيل", running: "قيد التنفيذ", building: "جارٍ بناء الشبكة",
    done: "انتهى التشغيل", empty: "تظهر الوصلات مع انتقال المهام بين الوكلاء",
  },
  en: {
    title: "Execution graph", reduce: "Collapse graph", expand: "Expand graph",
    connecting: "Connecting to the engine", waiting: "Waiting for a scan",
    stopped: "Scan stopped", running: "Running", building: "Building the execution graph",
    done: "Scan finished", empty: "Connections appear as tasks move between agents",
  },
};

export function networkLabel(node, lang = "ar") {
  if (lang !== "en") return labelOf(node);
  return englishBranches[node.split(":")[1]] || agents[roleOf(node)]?.[1] || node;
}

export function AgentIcon({ role, size = 20 }) {
  const Icon = icons[role] || CircleDot;
  return <Icon size={size} strokeWidth={1.65} />;
}
function Orbit() {
  return (
    <svg className="orbit" viewBox="0 0 680 230" aria-hidden="true">
      <defs>
        <radialGradient id="halo">
          <stop stopColor="#8268ef" stopOpacity=".65" />
          <stop offset=".55" stopColor="#6754ad" stopOpacity=".22" />
          <stop offset="1" stopColor="#63529b" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="track">
          <stop stopColor="#53536f" stopOpacity=".1" />
          <stop offset=".45" stopColor="#9a8dbf" stopOpacity=".85" />
          <stop offset="1" stopColor="#736088" stopOpacity=".15" />
        </linearGradient>
      </defs>
      <ellipse cx="340" cy="125" rx="240" ry="105" fill="url(#halo)" />
      <g
        fill="none"
        stroke="url(#track)"
        strokeWidth="1.2"
        transform="rotate(-14 340 125)"
      >
        {[0, 1, 2, 3, 4].map((i) => (
          <ellipse
            key={i}
            cx="340"
            cy="125"
            rx={70 + i * 35}
            ry={24 + i * 11}
          />
        ))}
      </g>
      <g fill="none" stroke="#827693" strokeWidth=".8" opacity=".6">
        <path d="M76 155l73-17 38 6 43-14M452 89l44-15 46 6 62-20" />
        <path d="M115 104l40 6 17-12M488 154l44-8 38 8" />
      </g>
      <g fill="#b9a7f2">
        <circle cx="149" cy="138" r="3" />
        <circle cx="496" cy="74" r="3" />
        <circle cx="163" cy="155" r="2.8" />
        <circle cx="456" cy="67" r="2" />
      </g>
      <g fill="#caff80">
        <circle cx="228" cy="130" r="3" />
        <circle cx="493" cy="106" r="2.8" />
      </g>
      <g transform="translate(340 118)">
        <path
          d="M-36-13 0-32 36-13v24L0 32-36 11Z"
          fill="#48405e"
          stroke="#ad9bc6"
        />
        <path d="m-36-13 36 21 36-21M0 8v24" fill="none" stroke="#9f8eb7" />
        <path d="m-36-18 36-20 36 20L0 3Z" fill="#89809c" stroke="#d8d0e3" />
        <path d="m-21-18 21-12 21 12L0-6Z" fill="#caff80" />
        <path d="M-7-18 0-22 7-18 0-14Z" fill="#4c5249" />
      </g>
    </svg>
  );
}
export function Network({
  events,
  busy,
  error,
  expanded,
  setExpanded,
  onAgent,
  lang = "ar",
}) {
  const t = graphCopy[lang];
  const nodes = new Map();
  events.forEach((e) => nodes.set(e.node, { ...nodes.get(e.node), ...e }));
  const items = [...nodes.values()];
  const last = items.filter((n) => n.status === "start").at(-1);
  const ranks = Object.keys(agents);
  const loc = new Map();
  for (const [idx, role] of ranks.entries()) {
    const members = items.filter((n) => roleOf(n.node) === role);
    members.forEach((n, i) =>
      loc.set(n.node, {
        x: 8 + idx * 21,
        y: members.length > 1 ? 30 + 40 * i : 50,
      }),
    );
  }
  return (
    <section
      className={"net-card" + (expanded ? " expanded" : "")}
      aria-label={t.title}
    >
      <div className="net-head">
        <div className="net-title">
          <span className="net-title-icon">
            <GitBranch size={18} />
          </span>
          <div>
            <h2>{t.title}</h2>
            {lang === "ar" && <small dir="ltr">EXECUTION GRAPH</small>}
          </div>
        </div>
        <button
          className="square dark"
          aria-label={expanded ? t.reduce : t.expand}
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
        </button>
      </div>
      <div className={"net-stage " + (!items.length ? "idle" : "")}>
        <span className="corner tr" />
        <span className="corner bl" />
        {!items.length ? (
          <div className="orbital">
            <Orbit />
            <div className="standby">
              <i /> {busy ? t.connecting : t.waiting}
            </div>
          </div>
        ) : (
          <div className="map" dir="ltr">
            <svg
              viewBox="0 0 1000 240"
              preserveAspectRatio="none"
              aria-hidden="true"
            >
              {items.flatMap((n) =>
                (n.parents || []).map((p) => {
                  const a = loc.get(p),
                    b = loc.get(n.node);
                  if (!a || !b) return null;
                  const mid = (a.x + b.x) * 5;
                  return (
                    <path
                      key={p + n.node}
                      d={`M${a.x * 10} ${a.y * 2.4} C${mid} ${a.y * 2.4},${mid} ${b.y * 2.4},${b.x * 10} ${b.y * 2.4}`}
                      fill="none"
                      stroke={n.status === "done" ? "#a8dc82" : "#a091cf"}
                      strokeWidth="2"
                      vectorEffect="non-scaling-stroke"
                    />
                  );
                }),
              )}
            </svg>
            {items.map((n) => {
              const pos = loc.get(n.node);
              if (!pos) return null;
              return (
                <button
                  key={n.node}
                  className={"node " + n.status}
                  style={{ left: pos.x + "%", top: pos.y + "%" }}
                  onClick={() => onAgent(n.node)}
                  aria-label={networkLabel(n.node, lang)}
                >
                  <AgentIcon role={roleOf(n.node)} />
                  <small>{networkLabel(n.node, lang)}</small>
                </button>
              );
            })}
          </div>
        )}
      </div>
      <div className="net-foot">
        <span className={"event-light " + (busy ? "live" : "")} />
        <span>
          {error
            ? t.stopped
            : last && busy
              ? t.running + " · " + networkLabel(last.node, lang)
              : busy
                ? t.building
                : items.length
                  ? t.done
                  : t.empty}
        </span>
        <span className="langgraph" dir="ltr">
          <Layers3 size={13} /> LangGraph
        </span>
      </div>
    </section>
  );
}
