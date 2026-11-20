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
  labelOf,
  post,
  roleOf,
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
export function Agent({ node, event, model, tasks = [], close }) {
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
          ["الموديل", model || "تشغيل محلي"],
          ...(event?.source ? [["مصدر القرار", event.source === "model" ? "الموديل" : "النظام"]] : []),
          ...(event?.detail ? [["آخر حدث", event.detail]] : []),
        ].map(([k, v]) => (
          <React.Fragment key={k}>
            <dt>{k}</dt>
            <dd dir="auto">{String(v)}</dd>
          </React.Fragment>
        ))}
      </dl>
      {!!tasks.length && <section className="trace" aria-label="المهام المنفذة">
        <h3>المهام اللي نفّذها الدور</h3>
        <ul>{tasks.map((task) => <li key={task.id}>
          <bdi>{task.tool}</bdi>
          <p>{task.checks} قاعدة منطبقة · {task.matched} قاعدة مطابقة · {task.duration_ms} مللي ثانية</p>
        </li>)}</ul>
      </section>}
    </Modal>
  );
}
