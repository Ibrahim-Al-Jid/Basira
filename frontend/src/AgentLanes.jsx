import React from "react";
import "./agent-lanes.css";

export const ROLES = [
  ["orchestrator", "المايسترو", "Maestro", "يحدد نوع المدخل ويوجّهه", "Identifies the input and routes it"],
  ["planning", "الكشّاف", "Scout", "يجهّز الملفات ويثبّت القواعد", "Prepares files and pins the rules"],
  ["analysis", "الصيّاد", "Hunter", "يشغّل الفحوصات الدفاعية", "Runs the defensive checks"],
  ["validation", "المدقّق", "Auditor", "يطابق الأدلة مع التغطية", "Checks evidence against coverage"],
  ["reporting", "الكاتب", "Scribe", "يجمّع التقرير النهائي", "Assembles the final report"],
];
const STATE = {
  done: ["تم", "Done"], running: ["شغّال", "Running"], waiting: ["منتظر", "Waiting"], skipped: ["لم يُنفَّذ", "Not run"],
};

export function laneStates(events, active) {
  const finished = new Map();
  const started = new Set();
  for (const item of events) {
    if (item.kind === "agent_start") started.add(item.detail);
    if (item.kind !== "agent_done") continue;
    const [role, millis, tools] = item.detail.split("|");
    finished.set(role, { millis: Number(millis), tools: tools ? tools.split(",") : [] });
  }
  // The last role that has started is the one running; earlier started roles are finished.
  const last = ROLES.reduce((index, [id], position) => (started.has(id) ? position : index), -1);
  const lanes = ROLES.map(([id, ar, en, taskAr, taskEn], position) => {
    const result = finished.get(id);
    let state = "skipped";
    if (result || (started.has(id) && position < last)) state = "done";
    else if (active && started.has(id)) state = "running";
    else if (active) state = "waiting";
    return { id, ar, en, taskAr, taskEn, state, ...result };
  });
  if (active && !started.size && !finished.size) {
    const first = lanes.find((lane) => lane.state === "waiting");
    if (first) first.state = "running";
  }
  const modelDone = finished.get("model");
  const modelStarted = events.some((item) => item.kind === "stage_start" && item.detail === "model");
  if (modelDone || modelStarted) {
    lanes.push({ id: "model", ar: "الموديل", en: "Model", taskAr: "يرتّب الأولويات (طلب واحد كحد أقصى)",
      taskEn: "Ranks priorities (at most one request)", state: modelDone ? "done" : active ? "running" : "skipped", ...modelDone });
  }
  return lanes;
}

export default function AgentLanes({ events, active, t, lang }) {
  const lanes = laneStates(events, active);
  const done = lanes.filter((lane) => lane.state === "done").length;
  const now = lanes.find((lane) => lane.state === "running");
  const pipeline = lanes.filter((lane) => lane.id !== "model");
  const model = lanes.find((lane) => lane.id === "model");
  const card = (lane) => (
    <li key={lane.id} data-state={lane.state} data-lane={lane.id}>
      <span className="agent-lane-dot" aria-hidden="true" />
      <b>{t(lane.ar, lane.en)}</b>
      <span className="agent-lane-state">{t(...STATE[lane.state])}</span>
      <p>{t(lane.taskAr, lane.taskEn)}</p>
      {lane.state === "done" && lane.millis !== undefined && <p className="agent-lane-meta">
        <bdi>{lane.millis.toLocaleString(lang === "ar" ? "ar-EG" : "en")} ms</bdi>
        {lane.tools.map((tool) => <code key={tool}>{tool}</code>)}
      </p>}
    </li>
  );
  return (
    <section className="agent-lanes" aria-label={t("الوكلاء", "Agents")}>
      <h3>{t("الوكلاء وشغلهم", "Agents and their work")}
        <span className="agent-lanes-count">{done}/{lanes.length}</span></h3>
      <div className="agent-lanes-bar" role="progressbar" aria-label={t("تقدّم الوكلاء", "Agent progress")} aria-valuemin="0" aria-valuemax={lanes.length}
        aria-valuenow={done}><i style={{ inlineSize: `${(done / lanes.length) * 100}%` }} /></div>
      <p className="agent-lanes-now" role="status">
        {now ? t(`دلوقتي: ${now.ar}`, `Now: ${now.en}`) : active ? t("في الانتظار…", "Waiting…") : t("الفحص انتهى", "The scan has ended")}
      </p>
      <ol>{pipeline.map(card)}</ol>
      {model && <ol className="agent-lanes-model">{card(model)}</ol>}
    </section>
  );
}
