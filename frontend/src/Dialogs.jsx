import React, { useEffect, useRef, useState } from "react";
import {
  Check,
  KeyRound,
  LoaderCircle,
  Search,
  X,
} from "lucide-react";
import {
  agents,
  fetchJson,
  post,
  roleOf,
} from "./data";
import { AgentIcon, networkLabel } from "./Network";

const dialogCopy = {
  ar: {
    close: "إغلاق", settings: "إعدادات الموديل", shared: "موديل واحد لكل وكلاء التشغيل",
    key: "مفتاح API", fetch: "جلب الموديلات", emptyModels: "لم يُرجع OpenRouter أي موديلات متاحة.",
    requestFailed: "تعذّر جلب الموديلات من OpenRouter. راجع المفتاح وحاول مرة تانية.",
    storage: "المفتاح بيُحفظ في ذاكرة التبويب وبيتمسح عند تحديث الصفحة.",
    catalog: "كتالوج الموديلات", freeOnly: "المجانية فقط", search: "بحث في الموديلات",
    searchHint: "ابحث بالاسم أو المزوّد", select: "اختيار الموديل", free: "مجاني", paid: "مدفوع",
    noMatches: "لا توجد موديلات مطابقة.", charge: "استخدام الموديل المدفوع بيُحاسَب على حساب OpenRouter الخاص بك.",
    choose: "استخدام الموديل", disconnect: "قطع الاتصال",
    input: "المدخل", procedure: "الإجراء", output: "المخرج", tool: "الأداة",
    memory: "الذاكرة", sharedState: "حالة الفحص المشتركة داخل LangGraph",
    model: "الموديل", local: "تشغيل محلي", decision: "مصدر القرار", system: "النظام",
    last: "آخر حدث", tasks: "المهام المنفذة", roleTasks: "المهام اللي نفّذها الدور",
    stats: (task) => `${task.checks} قاعدة منطبقة · ${task.matched} قاعدة مطابقة · ${task.duration_ms} مللي ثانية`,
  },
  en: {
    close: "Close", settings: "Model settings", shared: "One model for the scan",
    key: "API key", fetch: "Fetch models", emptyModels: "OpenRouter returned no available models.",
    requestFailed: "Couldn't fetch models from OpenRouter. Check your key and try again.",
    storage: "The key stays in this tab's memory and clears when you reload the page.",
    catalog: "Model catalog", freeOnly: "Free models only", search: "Search models",
    searchHint: "Search by name or provider", select: "Choose a model", free: "Free", paid: "Paid",
    noMatches: "No matching models.", charge: "Paid model usage is charged to your OpenRouter account.",
    choose: "Use model", disconnect: "Disconnect",
    input: "Input", procedure: "Action", output: "Output", tool: "Tool",
    memory: "Memory", sharedState: "Shared scan state in LangGraph",
    model: "Model", local: "Local scan", decision: "Decision source", system: "System",
    last: "Latest event", tasks: "Completed tasks", roleTasks: "Tasks completed by this role",
    stats: (task) => `${task.checks} applicable checks · ${task.matched} matches · ${task.duration_ms} ms`,
  },
};

const englishDetails = {
  orchestrator: ["Review scope and memory summary", "Chooses the review route and hands off to planning.", "Routing decision", "LangGraph"],
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
export function Settings({ config, save, close, lang = "ar" }) {
  const t = dialogCopy[lang];
  const [key, setKey] = useState(config?.key || ""),
    [models, setModels] = useState(config?.models || []),
    [model, setModel] = useState(config?.model || ""),
    [free, setFree] = useState(!config?.paid),
    [search, setSearch] = useState(""),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  const filtered = models.filter(
    (m) =>
      (!free || m.free) &&
      (!search ||
        (m.name + " " + m.id).toLowerCase().includes(search.toLowerCase())),
  );
  const chosen = models.find((m) => m.id === model);
  async function connect() {
    setError("");
    setLoading(true);
    try {
      const body = await fetchJson("/api/models", post({ key: key.trim() }));
      setModels(body.models);
      setModel("");
      if (!body.models.length) setError({ code: "emptyModels" });
    } catch (e) {
      setError({ code: "requestFailed", detail: e.message });
      setModels([]);
      setModel("");
    } finally {
      setLoading(false);
    }
  }
  return (
    <Modal title={t.settings} close={close} lang={lang}>
      <div className="provider-label">
        <span className="tile lilac">
          <KeyRound />
        </span>
        <div>
          <strong dir="ltr">OpenRouter</strong>
          <small>{t.shared}</small>
        </div>
      </div>
      <label htmlFor="key">{t.key}</label>
      <div className="field-row">
        <input
          id="key"
          dir="ltr"
          type="password"
          autoComplete="off"
          placeholder="sk-or-…"
          value={key}
          disabled={loading}
          onChange={(e) => {
            setKey(e.target.value);
            setModels([]);
            setModel("");
            setError("");
          }}
        />
        <button
          disabled={!key.trim() || loading}
          className="btn"
          onClick={connect}
        >
          {loading ? <LoaderCircle className="spin" size={16} /> : null}{t.fetch}
        </button>
      </div>
      <p className="hint">
        {t.storage}
      </p>
      {models.length > 0 && (
        <>
          <div className="catalog-head">
            <h3>{t.catalog}</h3>
            <label className="check">
              <input
                type="checkbox"
                checked={free}
                onChange={(e) => {
                  setFree(e.target.checked);
                  if (e.target.checked && !chosen?.free) setModel("");
                }}
              />{" "}
              {t.freeOnly}
            </label>
          </div>
          <div className="search">
            <Search size={16} />
            <input
              aria-label={t.search}
              placeholder={t.searchHint}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div
            className="model-list"
            role="radiogroup"
            aria-label={t.select}
          >
            {filtered.map((m) => (
              <label
                key={m.id}
                className={"model-choice " + (model === m.id ? "selected" : "")}
              >
                <input
                  name="model"
                  type="radio"
                  checked={model === m.id}
                  onChange={() => setModel(m.id)}
                />
                <span>
                  <strong dir="ltr">{m.name}</strong>
                  <small dir="ltr">{m.id}</small>
                </span>
                <b>{m.free ? t.free : t.paid}</b>
              </label>
            ))}
            {!filtered.length && (
              <p className="hint">{t.noMatches}</p>
            )}
          </div>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error.detail && (lang === "ar" || !/[\u0600-\u06ff]/u.test(error.detail)) ? error.detail : t[error.code]}
        </p>
      )}
      {chosen && !chosen.free && (
        <p className="hint">
          {t.charge}
        </p>
      )}
      <div className="modal-actions">
        <button
          className="btn primary"
          disabled={!chosen || !key.trim() || loading}
          onClick={() => {
            save({ key: key.trim(), model, models, paid: !chosen.free });
            close();
          }}
        >
          {t.choose} <Check size={16} />
        </button>
        {config && (
          <button
            className="btn"
            onClick={() => {
              save(null);
              close();
            }}
          >
            {t.disconnect}
          </button>
        )}
      </div>
    </Modal>
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
