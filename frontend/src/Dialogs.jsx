import React, { useEffect, useRef, useState } from "react";
import {
  Check,
  Download,
  KeyRound,
  LoaderCircle,
  Search,
  Upload,
  X,
} from "lucide-react";
import {
  agents,
  dateText,
  fetchJson,
  labelOf,
  num,
  post,
  roleOf,
  sample,
} from "./data";
import { AgentIcon } from "./Network";

export function Modal({ title, children, close, wide = false }) {
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
          <button className="square" aria-label="إغلاق" onClick={close}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
export function Settings({ config, save, close }) {
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
      if (!body.models.length) setError("لم يُرجع OpenRouter أي موديلات متاحة.");
    } catch (e) {
      setError(e.message);
      setModels([]);
      setModel("");
    } finally {
      setLoading(false);
    }
  }
  return (
    <Modal title="إعدادات الموديل" close={close}>
      <div className="provider-label">
        <span className="tile lilac">
          <KeyRound />
        </span>
        <div>
          <strong dir="ltr">OpenRouter</strong>
          <small>موديل واحد لكل وكلاء التشغيل</small>
        </div>
      </div>
      <label htmlFor="key">مفتاح API</label>
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
          {loading ? <LoaderCircle className="spin" size={16} /> : null}جلب
          الموديلات
        </button>
      </div>
      <p className="hint">
        المفتاح بيُحفظ في ذاكرة التبويب وبيتمسح عند تحديث الصفحة.
      </p>
      {models.length > 0 && (
        <>
          <div className="catalog-head">
            <h3>كتالوج الموديلات</h3>
            <label className="check">
              <input
                type="checkbox"
                checked={free}
                onChange={(e) => {
                  setFree(e.target.checked);
                  if (e.target.checked && !chosen?.free) setModel("");
                }}
              />{" "}
              المجانية فقط
            </label>
          </div>
          <div className="search">
            <Search size={16} />
            <input
              aria-label="بحث في الموديلات"
              placeholder="ابحث بالاسم أو المزوّد"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div
            className="model-list"
            role="radiogroup"
            aria-label="اختيار الموديل"
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
                <b>{m.free ? "مجاني" : "مدفوع"}</b>
              </label>
            ))}
            {!filtered.length && (
              <p className="hint">لا توجد موديلات مطابقة.</p>
            )}
          </div>
        </>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {chosen && !chosen.free && (
        <p className="hint">
          استخدام الموديل المدفوع بيُحاسَب على حساب OpenRouter الخاص بك.
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
          استخدام الموديل <Check size={16} />
        </button>
        {config && (
          <button
            className="btn"
            onClick={() => {
              save(null);
              close();
            }}
          >
            قطع الاتصال
          </button>
        )}
      </div>
    </Modal>
  );
}
export function Source({ source, setSource, close }) {
  const [draft, setDraft] = useState(source),
    [error, setError] = useState("");
  const file = useRef();
  const loadFile = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      if (f.size > 1000000) throw Error("اختار ملف أصغر من ١ ميجابايت.");
      setDraft(await f.text());
      setError("");
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <Modal title="مصدر الفحص" wide close={close}>
      <p className="hint">
        الصق كود HTML أو حمّل ملف من جهازك. يراجع المحرك تصريحات السكربتات
        والنماذج في المصدر.
      </p>
      <label htmlFor="html">كود HTML</label>
      <textarea
        id="html"
        dir="ltr"
        value={draft}
        spellCheck={false}
        onChange={(e) => setDraft(e.target.value)}
      />
      <div className="source-tools">
        <button className="btn" onClick={() => file.current.click()}>
          <Upload size={15} />
          استيراد ملف
        </button>
        <input
          ref={file}
          type="file"
          hidden
          accept=".html,.htm,text/html"
          onChange={loadFile}
        />
        <button
          className="subtle"
          onClick={() => {
            setDraft(sample);
            setError("");
          }}
        >
          استرجاع العينة
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <div className="modal-actions">
        <button
          className="btn primary"
          disabled={!draft.trim()}
          onClick={() => {
            setSource(draft);
            close();
          }}
        >
          تطبيق المصدر <Check size={15} />
        </button>
      </div>
    </Modal>
  );
}
export function Agent({ node, event, model, close }) {
  const role = roleOf(node),
    data = agents[role];
  if (!data) return null;
  return (
    <Modal title={labelOf(node)} close={close}>
      <div className="provider-label">
        <span className="tile lilac">
          <AgentIcon role={role} />
        </span>
        <strong dir="ltr">{data[1]}</strong>
      </div>
      <dl className="spec">
        {[
          ["المدخل", data[2]],
          ["الإجراء", data[3]],
          ["المخرج", data[4]],
          ["الأداة", data[5]],
          ["الذاكرة", "حالة الفحص المشتركة داخل LangGraph"],
          ["الموديل", model || "يُحدّد قبل بدء الفحص"],
          ...(event?.detail ? [["آخر حدث", event.detail]] : []),
        ].map(([k, v]) => (
          <React.Fragment key={k}>
            <dt>{k}</dt>
            <dd dir="auto">{String(v)}</dd>
          </React.Fragment>
        ))}
      </dl>
    </Modal>
  );
}
export function Report({ report, close }) {
  const [language, setLanguage] = useState("ar"),
    ar = language === "ar",
    findings = report.findings || [],
    metrics = report.metrics || {},
    b = metrics.benchmark;
  return (
    <Modal title="تقرير الفحص" wide close={close}>
      <div className="report-meta">
        <span>{dateText(report.created_at)}</span>
        <span dir="ltr">{report.model}</span>
      </div>
      <div className="switch">
        <button
          className={ar ? "selected" : ""}
          onClick={() => setLanguage("ar")}
        >
          العربية
        </button>
        <button
          className={!ar ? "selected" : ""}
          onClick={() => setLanguage("en")}
        >
          English
        </button>
      </div>
      <div dir={ar ? "rtl" : "ltr"} lang={language}>
        <p className="summary">{ar ? report.summary_ar : report.summary_en}</p>
        <div className="measure">
          <span>
            {ar ? "الملاحظات" : "Findings"} <b>{findings.length}</b>
          </span>
          <span>
            {ar ? "استدعاءات الموديل" : "Model calls"}{" "}
            <b>{metrics.modelCalls ?? "—"}</b>
          </span>
        </div>
        {b && (
          <p className="benchmark">
            {ar ? "العينة المرجعية" : "Reference fixture"} · {b.matched}/
            {b.expected} · {ar ? "إضافية" : "Unexpected"} {b.unexpected}
          </p>
        )}
        {findings.map((f, i) => (
          <article className="finding" key={i}>
            <div>
              <strong>{ar ? f.title_ar || f.title : f.title}</strong>
              <small>
                {ar ? "سطر" : "Line"} {f.line}
              </small>
            </div>
            <code dir="ltr">{f.evidence}</code>
            <p>{ar ? f.remediation_ar || f.remediation : f.remediation}</p>
          </article>
        ))}
      </div>
      <div className="modal-actions">
        {["ar", "en"].map((l) => (
          <a
            key={l}
            className={"btn " + (l === language ? "primary" : "")}
            href={
              "/api/reports/" +
              encodeURIComponent(report.id) +
              "/download?lang=" +
              l
            }
            download
          >
            <Download size={15} />
            {l === "ar" ? "تحميل التقرير العربي" : "Download English report"}
          </a>
        ))}
      </div>
    </Modal>
  );
}
