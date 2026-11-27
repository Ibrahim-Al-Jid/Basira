import React, { useEffect, useId, useRef, useState } from "react";
import { KeyRound } from "lucide-react";
import { action, api, errorText, json, translate } from "./platformClient";

const path = api + "/account/model-connection";
const PROVIDERS = [
  { id: "openrouter", name: "OpenRouter" },
  { id: "openai", name: "OpenAI" },
  { id: "anthropic", name: "Anthropic" },
  { id: "google", name: "Google Gemini" },
  { id: "custom", name: "Custom (OpenAI-compatible)" },
];

export function ProviderSettings({ lang }) {
  const t = translate(lang);
  const [state, setState] = useState(null);
  const [key, setKey] = useState("");
  const [model, setModel] = useState("");
  const [provider, setProvider] = useState("openrouter");
  const [baseUrl, setBaseUrl] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
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
  const providerName = PROVIDERS.find((item) => item.id === provider).name;
  const target = { provider, ...(provider === "custom" ? { base_url: baseUrl.trim() } : {}) };
  const keyPayload = { ...target, ...(key.trim() ? { api_key: key.trim() } : {}) };
  const saved = state?.connection;
  const sameTarget = saved && saved.provider === provider && (saved.base_url || "") === (provider === "custom" ? baseUrl.trim() : "");
  const chosen = visible.find((item) => item.id === selected);
  const needsAck = Boolean(chosen && !chosen.free);
  const ready = provider !== "custom" || baseUrl.trim().startsWith("https://");
  const canList = ready && !pending && (key.trim() || sameTarget);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    action(path, { signal: controller.signal }).then(
      (value) => {
        if (controller.signal.aborted) return;
        setState(value);
        if (value.connection) {
          setProvider(value.connection.provider || "openrouter");
          setBaseUrl(value.connection.base_url || "");
        }
      },
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
      setAcknowledged(false);
      setFreeOnly(models.some((item) => item.free));
      setModel(sameTarget ? state.connection.model : "");
    });
  }

  function onSubmit(event) {
    event.preventDefault();
    if (!selected || pending || (needsAck && !acknowledged)) return;
    run(async () => {
      setState(await action(path, json("PUT", { model: selected, ...keyPayload })));
      setKey("");
      setNotice(t(`اتحفظ الاتصال بـ ${providerName}.`, `${providerName} connection saved.`));
    });
  }

  return <section ref={panel} id="model-connection" className="card project-panel provider-settings" aria-labelledby="provider-title">
    <h2 id="provider-title"><KeyRound size={19} aria-hidden="true" />{t("اتصال الموديل", "Model connection")}</h2>
    {error && <p role="alert" className="workspace-error">{errorText(error, t)}</p>}
    {!state && !error && <p role="status">{t("بنحمّل إعدادات المزوّد…", "Loading provider settings…")}</p>}
    {((!state && error) || (state && !state.available)) && <div className="workspace-actions">
      {state && <p>{state.reason === "not_configured"
        ? t("بوابة الموديل مش متظبطة على السيرفر. شغّل ops/start-local.ps1 -Model وبعدها اعمل إعادة محاولة.", "The model gateway is not set up on this server. Run ops/start-local.ps1 -Model, then retry.")
        : state.reason === "unreachable"
          ? t("بوابة الموديل متظبطة بس مش بترد. تأكد إن حاوية model-gateway شغالة في Docker وجرّب تاني.", "The model gateway is set up but not answering. Check that the model-gateway container is running in Docker, then retry.")
          : t("بوابة الموديل غير متاحة حاليًا.", "The model gateway is currently unavailable.")}</p>}
      <button className="btn" type="button" onClick={() => setAttempt((value) => value + 1)}>{t("إعادة المحاولة", "Retry")}</button>
    </div>}
    {state?.available && <>
      {saved && <p>{t("المحفوظ حاليًا", "Currently saved")}: <bdi>{(PROVIDERS.find((item) => item.id === saved.provider) || PROVIDERS[0]).name} / {saved.model}</bdi>{" "}
        <span className="workspace-hint">{t("المفتاح محفوظ ومخفي (", "Key stored and hidden (")}<bdi>********</bdi>{t(")", ")")}</span></p>}
      <form className="project-form" onSubmit={onSubmit} aria-busy={pending}>
        <label>{t("المزوّد", "Provider")}
          <select name="provider" value={provider} disabled={pending} onChange={(event) => {
            setProvider(event.target.value);
            setKey("");
            setModels(null);
            setModel("");
          }}>
            {PROVIDERS.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </label>
        {provider === "custom" && <label>{t("عنوان الـ API (https فقط)", "API base URL (https only)")}
          <input name="base-url" type="url" dir="ltr" placeholder="https://api.example.com/v1" autoComplete="off" spellCheck={false}
            maxLength={300} value={baseUrl} disabled={pending} onChange={(event) => { setBaseUrl(event.target.value); setModels(null); setModel(""); }} />
        </label>}
        <label>{t(`مفتاح API لـ ${providerName}`, `${providerName} API key`)}
          <input name="openrouter-key" type="password" dir="ltr" autoComplete="off" spellCheck={false}
            maxLength={256} value={key} disabled={pending} onChange={(event) => {
              setKey(event.target.value);
              setModels(null);
              setModel("");
            }} />
        </label>
        {sameTarget && <p className="workspace-hint">{t("سيب الحقل فاضي لاستخدام المفتاح المحفوظ.", "Leave the field empty to use the saved key.")}</p>}
        {saved && !sameTarget && <p className="workspace-hint">{t("غيّرت المزوّد أو العنوان، فلازم تدخل المفتاح من جديد.", "You changed the provider or address, so enter the key again.")}</p>}
        <button className="btn" type="button" onClick={loadModels} disabled={!canList}>
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
                <option value="">{t("اختار موديل", "Choose a model")}</option>
                {visible.map((item) => <option key={item.id} value={item.id} dir="ltr">
                  {item.name === item.id ? item.id : `${item.name} · ${item.id}`}
                </option>)}
              </select>
            </div>
          </div>
          {!visible.length && <p role="status">{t("مفيش موديلات مطابقة للفلتر الحالي.", "No models match the current filters.")}</p>}
          {needsAck && <label className="project-check">
            <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} disabled={pending} />
            {t(`الموديل ده مش مجاني أو سعره مش معروف. الاستخدام بيتحاسب على حسابك عند ${providerName}، وأنا فاهم كده.`,
              `This model is not free or its price is unknown. Usage is billed to your ${providerName} account and I understand that.`)}
          </label>}
          <button className="btn primary" disabled={pending || !selected || (needsAck && !acknowledged)}>{t("حفظ اتصال الموديل", "Save model connection")}</button>
        </>}
        {notice && <p role="status">{notice}</p>}
      </form>
      {saved && <button type="button" className="btn danger-action" disabled={pending} onClick={() => run(async () => {
        setState(await action(path, { method: "DELETE" }));
        setKey("");
        setModel("");
        setModels(null);
        setNotice(t("اتحذف اتصال الموديل.", "Model connection removed."));
      })}>{t("حذف الاتصال", "Remove connection")}</button>}
    </>}
  </section>;
}
