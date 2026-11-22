import React, { useEffect, useId, useRef, useState } from "react";
import { KeyRound } from "lucide-react";
import { action, api, errorText, json, translate } from "./platformClient";

const path = api + "/account/model-connection";

export function ProviderSettings({ lang }) {
  const t = translate(lang);
  const [state, setState] = useState(null);
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [models, setModels] = useState(null);
  const [freeOnly, setFreeOnly] = useState(true);
  const [search, setSearch] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState("");
  const [attempt, setAttempt] = useState(0);
  const modelId = useId();
  const panel = useRef(null);
  const query = search.trim().toLowerCase();
  const visible = (models || []).filter((item) => (!freeOnly || item.free)
    && (item.id.toLowerCase().includes(query) || item.name.toLowerCase().includes(query)));
  const selected = visible.some((item) => item.id === model) ? model : "";
  const keyPayload = key.trim() ? { api_key: key.trim() } : {};

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    action(path, { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setState(value); },
      (failure) => { if (!controller.signal.aborted) setError(failure); },
    );
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => {
    if (window.location.hash === "#model-connection") panel.current?.scrollIntoView();
  }, []);

  async function run(operation) {
    setPending(true);
    setError(null);
    setNotice("");
    try { await operation(); }
    catch (failure) { setError(failure); }
    finally { setPending(false); }
  }

  function loadModels() {
    run(async () => {
      const { models } = await action(path + "/models", json("POST", keyPayload));
      setModels(models);
      setModel(state.connection?.model || "");
    });
  }

  function onSubmit(event) {
    event.preventDefault();
    if (!selected || pending) return;
    run(async () => {
      setState(await action(path, json("PUT", { model: selected, ...keyPayload })));
      setKey("");
      setNotice(t("اتحفظ اتصال OpenRouter.", "OpenRouter connection saved."));
    });
  }

  return <section ref={panel} id="model-connection" className="card project-panel provider-settings" aria-labelledby="provider-title">
    <h2 id="provider-title"><KeyRound size={19} aria-hidden="true" />{t("اتصال الموديل", "Model connection")}</h2>
    {error && <p role="alert" className="workspace-error">{errorText(error, t)}</p>}
    {!state && !error && <p role="status">{t("بنحمّل إعدادات المزوّد…", "Loading provider settings…")}</p>}
    {((!state && error) || (state && !state.available)) && <div className="workspace-actions">
      {state && <p>{t("بوابة OpenRouter غير متاحة حاليًا.", "The OpenRouter gateway is currently unavailable.")}</p>}
      <button className="btn" type="button" onClick={() => setAttempt((value) => value + 1)}>{t("إعادة المحاولة", "Retry")}</button>
    </div>}
    {state?.available && <>
      {state.connection && <p>{t("الموديل المحفوظ", "Saved model")} <bdi>{state.connection.model}</bdi></p>}
      <form className="project-form" onSubmit={onSubmit} aria-busy={pending}>
        <label>{t("مفتاح API لـ OpenRouter", "OpenRouter API key")}
          <input name="openrouter-key" type="password" dir="ltr" autoComplete="off" spellCheck={false}
            maxLength={256} value={key} disabled={pending} onChange={(event) => {
              setKey(event.target.value);
              setModels(null);
              setModel("");
            }} />
        </label>
        {state.connection && <p className="workspace-hint">{t("سيبي الحقل فاضي لاستخدام المفتاح المحفوظ.", "Leave the field empty to use the saved key.")}</p>}
        <button className="btn" type="button" onClick={loadModels} disabled={pending || (!key.trim() && !state.connection)}>
          {t("عرض الموديلات المتاحة", "Show available models")}
        </button>
        {models && <>
          <label className="project-check">
            <input type="checkbox" checked={freeOnly} onChange={(event) => setFreeOnly(event.target.checked)} disabled={pending} />
            {t("الموديلات المجانية فقط", "Free models only")}
          </label>
          <div className="provider-model-picker">
            <label>{t("بحث في الموديلات", "Search models")}
              <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} disabled={pending} />
            </label>
            <div>
              <label htmlFor={modelId}>{t("الموديل", "Model")}</label>
              <select id={modelId} name="model" value={selected}
                onChange={(event) => setModel(event.target.value)} disabled={pending || !visible.length}>
                <option value="">{t("اختاري موديل", "Choose a model")}</option>
                {visible.map((item) => <option key={item.id} value={item.id} dir="ltr">
                  {item.name === item.id ? item.id : `${item.name} · ${item.id}`}
                </option>)}
              </select>
            </div>
          </div>
          {!visible.length && <p role="status">{t("مفيش موديلات مطابقة للفلتر الحالي.", "No models match the current filters.")}</p>}
          <button className="btn primary" disabled={pending || !selected}>{t("حفظ اتصال الموديل", "Save model connection")}</button>
        </>}
        {notice && <p role="status">{notice}</p>}
      </form>
      {state.connection && <button type="button" className="btn danger-action" disabled={pending} onClick={() => run(async () => {
        setState(await action(path, { method: "DELETE" }));
        setKey("");
        setModel("");
        setModels(null);
        setNotice(t("اتحذف اتصال OpenRouter.", "OpenRouter connection removed."));
      })}>{t("حذف الاتصال", "Remove connection")}</button>}
    </>}
  </section>;
}
