import React from "react";
import "./agent-lanes.css";

export const ROLES = [
  ["orchestrator", "المنسّق", "Coordinator", "يحدد نوع المدخل ويوجّهه", "Identifies the input and routes it"],
  ["planning", "التخطيط", "Planning", "يجهّز الملفات ويثبّت القواعد", "Prepares files and pins the rules"],
  ["analysis", "التحليل", "Analysis", "يشغّل الفحوصات الدفاعية", "Runs the defensive checks"],
  ["validation", "التحقق", "Verification", "يطابق الأدلة مع التغطية", "Checks evidence against coverage"],
  ["reporting", "التقرير", "Reporting", "يجمّع التقرير النهائي", "Assembles the final report"],
];
const STATE = {
  done: ["تم", "Done"], running: ["شغّال", "Running"], waiting: ["منتظر", "Waiting"], skipped: ["لم يُنفَّذ", "Not run"],
};

export function laneStates(events, active) {
  const finished = new Map();
  for (const item of events) {
    if (item.kind !== "agent_done") continue;
    const [role, millis, tools] = item.detail.split("|");
    finished.set(role, { millis: Number(millis), tools: tools ? tools.split(",") : [] });
  }
  let running = active;
  return ROLES.map(([id, ar, en, taskAr, taskEn]) => {
    const result = finished.get(id);
    let state = "skipped";
    if (result) state = "done";
    else if (running) { state = "running"; running = false; }
    else if (active) state = "waiting";
    return { id, ar, en, taskAr, taskEn, state, ...result };
  });
}

export default function AgentLanes({ events, active, t, lang }) {
  const lanes = laneStates(events, active);
  const done = lanes.filter((lane) => lane.state === "done").length;
  return (
    <section className="agent-lanes" aria-label={t("الوكلاء", "Agents")}>
      <h3>{t("الوكلاء وشغلهم", "Agents and their work")}
        <span className="agent-lanes-count">{done}/{lanes.length}</span></h3>
      <ol>
        {lanes.map((lane) => (
          <li key={lane.id} data-state={lane.state}>
            <span className="agent-lane-dot" aria-hidden="true" />
            <div>
              <b>{t(lane.ar, lane.en)}</b>
              <span className="agent-lane-state">{t(...STATE[lane.state])}</span>
              <p>{t(lane.taskAr, lane.taskEn)}</p>
              {lane.state === "done" && <p className="agent-lane-meta">
                <bdi>{lane.millis.toLocaleString(lang === "ar" ? "ar-EG" : "en")} ms</bdi>
                {lane.tools.map((tool) => <code key={tool}>{tool}</code>)}
              </p>}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
