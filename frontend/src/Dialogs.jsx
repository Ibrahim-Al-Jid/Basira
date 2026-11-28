import React, { useEffect, useRef } from "react";
import { X } from "lucide-react";
import { agents, roleOf } from "./data";
import { AgentIcon, networkLabel } from "./Network";

const dialogCopy = {
  ar: {
    close: "إغلاق",
    input: "المدخل", procedure: "الإجراء", output: "المخرج", tool: "الأداة",
    memory: "الذاكرة", sharedState: "حالة الفحص المشتركة داخل LangGraph",
    model: "الموديل", local: "تشغيل محلي", decision: "مصدر القرار", system: "النظام",
    last: "آخر حدث", tasks: "المهام المنفذة", roleTasks: "المهام اللي نفّذها الدور",
    stats: (task) => `${task.checks} قاعدة منطبقة · ${task.matched} قاعدة مطابقة · ${task.duration_ms} مللي ثانية`,
  },
  en: {
    close: "Close",
    input: "Input", procedure: "Action", output: "Output", tool: "Tool",
    memory: "Memory", sharedState: "Shared scan state in LangGraph",
    model: "Model", local: "Local scan", decision: "Decision source", system: "System",
    last: "Latest event", tasks: "Completed tasks", roleTasks: "Tasks completed by this role",
    stats: (task) => `${task.checks} applicable checks · ${task.matched} matches · ${task.duration_ms} ms`,
  },
};

const englishDetails = {
  orchestrator: ["Review scope and memory summary", "Chooses the review route and hands off to the Scout.", "Routing decision", "LangGraph"],
  planning: ["Routing instructions and available rules", "Assigns the review to the appropriate analysis branches.", "A scoped scan plan", "Rule catalog"],
  analysis: ["Scan plan and the results of checking element attributes", "Reviews findings from the local checks within its branch.", "Matching rule IDs for the branch", "Local HTML checker"],
  validation: ["HTML evidence and analysis branch results", "Verifies each match against its rule and local evidence.", "Verified observations", "Evidence matching"],
  reporting: ["Verified observations and scan metrics", "Summarizes findings and repair priorities in both languages.", "Arabic and English report", "Report builder"],
};

export function Modal({ title, children, close, wide = false, lang = "ar" }) {
  const ref = useRef(null);
  useEffect(() => {
    const d = ref.current;
    d.showModal();
    return () => d.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className={"modal " + (wide ? "wide" : "")}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
    >
      <div className="modal-body">
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="square" aria-label={dialogCopy[lang].close} onClick={close}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
export function Agent({ node, event, model, tasks = [], close, lang = "ar" }) {
  const t = dialogCopy[lang];
  const role = roleOf(node),
    data = agents[role];
  if (!data) return null;
  const [input, procedure, output, tool] = lang === "en" ? englishDetails[role] : data.slice(2);
  const detail = (lang === "en" && event?.detail_en) || event?.detail;
  return (
    <Modal title={networkLabel(node, lang)} close={close} lang={lang}>
      <div className="provider-label">
        <span className="tile lilac">
          <AgentIcon role={role} />
        </span>
        <strong dir="ltr">{data[1]}</strong>
      </div>
      <dl className="spec">
        {[
          [t.input, input],
          [t.procedure, procedure],
          [t.output, output],
          [t.tool, tool],
          [t.memory, t.sharedState],
          [t.model, model || t.local],
          ...(event?.source ? [[t.decision, event.source === "model" ? t.model : t.system]] : []),
          ...(detail ? [[t.last, detail]] : []),
        ].map(([k, v]) => (
          <React.Fragment key={k}>
            <dt>{k}</dt>
            <dd dir="auto">{String(v)}</dd>
          </React.Fragment>
        ))}
      </dl>
      {!!tasks.length && <section className="trace" aria-label={t.tasks}>
        <h3>{t.roleTasks}</h3>
        <ul>{tasks.map((task) => <li key={task.id}>
          <bdi>{task.tool}</bdi>
          <p>{t.stats(task)}</p>
        </li>)}</ul>
      </section>}
    </Modal>
  );
}
