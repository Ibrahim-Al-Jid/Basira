import React, { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { ArrowUpRight, ClipboardCheck, FileText, FolderOpen, Plus, ScanLine, UploadCloud } from "lucide-react";
import { post } from "./data";
import "./platform.css";

const api = "/api/platform";
const kinds = {
  html: ["HTML", "HTML"],
  repository: ["لقطة مستودع ZIP", "Repository ZIP"],
  har: ["لقطة استجابات HAR", "HTTP capture (HAR)"],
  config: ["لقطة إعدادات JSON", "Configuration JSON"],
};
const extensions = { html: ".html,.htm", repository: ".zip", har: ".har", config: ".json" };
const states = {
  queued: ["في الانتظار", "Queued"], running: ["قيد التنفيذ", "Running"],
  completed: ["مكتمل", "Completed"], partial: ["جزئي", "Partial"],
  failed: ["فشل", "Failed"], cancelled: ["أُلغي", "Cancelled"],
};
function eventDetail(event) {
  if (event.kind === "running") {
    const attempt = event.detail.match(/\d+/)?.[0];
    return attempt ? `Execution attempt ${attempt} started.` : "Execution started.";
  }
  return ({
    "تم تسجيل الطلب للفحص.": "Scan request queued.",
    "اكتمل الفحص.": "Scan completed.",
    "اتلغى الفحص.": "Scan cancelled.",
    "التقرير التجريبي جاهز.": "The partial report is ready.",
    "وصلت المهمة للحد الأقصى لمحاولات التشغيل.": "The scan reached its retry limit.",
    "تعذّر تنفيذ الفحص.": "The scan could not be completed.",
  })[event.detail] || event.detail;
}
const isActive = (state) => state === "queued" || state === "running";
const translate = (lang) => (ar, en) => lang === "en" ? en : ar;
const label = (table, value, t) => table[value] ? t(...table[value]) : value;
const number = (value, lang) => new Intl.NumberFormat(lang === "ar" ? "ar-EG" : "en").format(value);
const newScanLink = (id) => id ? `/new-scan?project=${id}` : "/new-scan";
const errorText = (err, t) => t(err.message, ({
  401: "Check your credentials or sign in again.",
  403: "This account cannot perform the requested action.",
  404: "This item is unavailable.",
  409: "This item already exists or its state changed.",
  422: "Check the form values and try again.",
  429: "Too many requests. Wait a moment and try again.",
})[err.status] || (/^[\x00-\x7f]+$/.test(err.message) ? err.message : "The request could not be completed."));
const projectApi = (id) => `${api}/projects/${id}`;
const scanLink = (project, scan) => `/projects/${project}/scans/${scan}`;
const reportLink = (project, report = "") => `/reports${report && "/" + report}?project=${project}`;
const json = (method, body) => ({ ...post(body), method });

async function action(path, options) {
  const response = await fetch(path, options);
  if (response.status === 204) return null;
  const value = await response.json().catch(() => null);
  if (!response.ok) {
    const fallback = response.status === 429 ? "محاولات كتير في وقت قصير. استنى شوية وحاول تاني." : "تعذّر تنفيذ الطلب.";
    throw Object.assign(Error(typeof value?.detail === "string" ? value.detail : fallback), { status: response.status });
  }
  return value;
}

function encoded(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.onerror = () => reject(Error("تعذّر قراءة الملف."));
    reader.readAsDataURL(file);
  });
}

function Panel({ title, children }) {
  return <section className="card project-panel"><h2>{title}</h2>{children}</section>;
}

function AccountAccess({ onAuthenticated, lang }) {
  const t = translate(lang);
  const [options, setOptions] = useState(null);
  const [optionsError, setOptionsError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState("login");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const activeRequest = useRef(null);
  const titleId = useId();
  const passwordId = useId();
  const hintId = useId();
  const register = mode === "register";

  useEffect(() => {
    const controller = new AbortController();
    action(api + "/auth/options", { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setOptions(value); },
      (err) => { if (!controller.signal.aborted) setOptionsError(errorText(err, t)); },
    );
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => () => activeRequest.current?.abort(), []);

  function changeMode(next) {
    if (next === mode) return;
    setMode(next);
    setError("");
    setShowPassword(false);
  }

  async function submit(event) {
    event.preventDefault();
    if (activeRequest.current) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const password = data.get("password");
    const length = [...password].length;
    if (length > 128 || (register && length < 12)) {
      setError(register ? t("كلمة المرور لازم تكون بين ١٢ و١٢٨ حرف.", "Use a password with 12 to 128 characters.")
        : t("الحد الأقصى لكلمة المرور ١٢٨ حرف.", "Your password can have up to 128 characters."));
      return;
    }
    setError("");
    setBusy(true);
    const controller = new AbortController();
    activeRequest.current = controller;
    try {
      const account = await action(`${api}/auth/password/${mode}`, {
        ...post({ email: data.get("email").trim(), password }),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (!account?.id || typeof account.display_name !== "string") throw Error("رد تسجيل الدخول غير صالح.");
      form.reset();
      onAuthenticated(account);
    } catch (err) {
      if (!controller.signal.aborted) setError(errorText(err, t));
    } finally {
      activeRequest.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <section className="card project-panel project-account" aria-labelledby={titleId}>
      <header className="project-account-heading">
        <h1 id={titleId}>{t("حساب المشاريع", "Sign in to Marsad")}</h1>
        <p>{t("سجّل الدخول عشان تستخدم مشاريع الفرق وتتابع الفحوصات والتقارير.", "Sign in to manage projects, run scans and access reports.")}</p>
      </header>
      {!options && !optionsError && <p role="status">{t("جاري تحميل طرق تسجيل الدخول…", "Loading sign-in options…")}</p>}
      {optionsError && (
        <div className="project-account-feedback">
          <p className="error" role="alert">{optionsError}</p>
          <button className="btn" type="button" onClick={() => {
            setOptionsError("");
            setAttempt((value) => value + 1);
          }}>{t("إعادة المحاولة", "Retry")}</button>
        </div>
      )}
      {options?.password && (
        <>
          {options.registration && (
            <div className="project-account-modes" role="group" aria-label={t("نوع الحساب", "Account mode")}>
              <button type="button" aria-pressed={!register} disabled={busy} onClick={() => changeMode("login")}>{t("عندي حساب", "I have an account")}</button>
              <button type="button" aria-pressed={register} disabled={busy} onClick={() => changeMode("register")}>{t("إنشاء حساب", "Create an account")}</button>
            </div>
          )}
          <form className="project-form project-account-form" onSubmit={submit} aria-busy={busy}>
            <label>{t("البريد الإلكتروني", "Email")}
              <input name="email" type="email" autoComplete="username" dir="ltr" maxLength={254} required disabled={busy} />
            </label>
            <label htmlFor={passwordId}>{t("كلمة المرور", "Password")}</label>
            <div className="project-password-field">
              <input key={mode} id={passwordId} name="password" type={showPassword ? "text" : "password"} dir="ltr"
                autoComplete={register ? "new-password" : "current-password"}
                aria-describedby={register ? hintId : undefined}
                maxLength={256} required disabled={busy} />
              <button className="btn" type="button" aria-controls={passwordId} disabled={busy}
                onClick={() => setShowPassword((value) => !value)}>
                {showPassword ? t("إخفاء كلمة المرور", "Hide password") : t("إظهار كلمة المرور", "Show password")}
              </button>
            </div>
            {register && <p id={hintId} className="project-account-hint">{t("من ١٢ إلى ١٢٨ حرف.", "12 to 128 characters.")}</p>}
            {error && <p className="error" role="alert">{error}</p>}
            <button className="btn primary" disabled={busy}>
              {register ? t("إنشاء الحساب", "Create account") : t("تسجيل الدخول", "Sign in")}
            </button>
            {busy && <p role="status" className="project-account-hint">{register ? t("جاري إنشاء الحساب…", "Creating your account…") : t("جاري تسجيل الدخول…", "Signing in…")}</p>}
          </form>
        </>
      )}
      {options?.oidc && <a className="btn" href={api + "/auth/login"}>{t("الدخول بحساب المؤسسة", "Sign in with your organization")}</a>}
      {options && !options.password && !options.oidc && <p role="status">{t("تسجيل الدخول للمشاريع غير متاح حاليًا.", "Project sign-in is currently unavailable.")}</p>}
      <a className="project-account-lab" href="/demo">{t("جرّب المختبر المحلي", "Try the local demo")}</a>
    </section>
  );
}

function ScanStatus({ projectId, scanId, lang }) {
  const t = translate(lang);
  const [scan, setScan] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [canScan, setCanScan] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    let cursor = 0;
    setScan(null);
    setEvents([]);
    setError("");
    setCanScan(false);
    action(api + "/projects", { signal: controller.signal }).then(
      ({ projects }) => {
        if (!controller.signal.aborted) setCanScan(projects.some((item) => item.id === projectId && item.role !== "viewer"));
      },
      () => {},
    );
    async function poll() {
      try {
        const view = await action(`${projectApi(projectId)}/scans/${scanId}?after=${cursor}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setScan(view);
        setError("");
        if (view.events.length) {
          cursor = view.events.at(-1).sequence;
          setEvents((current) => [...current, ...view.events]);
        }
        if (cursor < view.cursor || isActive(view.state)) timer = setTimeout(poll, 1200);
      } catch (err) {
        if (err.name !== "AbortError") setError(err);
      }
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [projectId, scanId, reload]);
  async function cancel() {
    setCancelling(true);
    try {
      await action(projectApi(projectId) + "/scans/" + scanId + "/cancel", { method: "POST" });
      setReload((count) => count + 1);
    } catch (err) { setError(err); }
    finally { setCancelling(false); }
  }
  return (
    <div className="project-workspace">
      <a className="workspace-back" href={"/scans?project=" + projectId}>{t("سجل الفحوصات", "Scan history")}</a>
      <h1>{t("متابعة الفحص", "Scan progress")}</h1>
      {error && <p className="workspace-error" role="alert">{errorText(error, t)} <button className="btn" onClick={() => setReload((n) => n + 1)}>{t("إعادة المحاولة", "Retry")}</button></p>}
      {!scan && !error && <p role="status">{t("جاري تحميل حالة الفحص…", "Loading scan status…")}</p>}
      {scan && <Panel title={label(states, scan.state, t)}>
        <p role="status" className="workspace-scan-status"><bdi>{scan.artifact.name}</bdi><span className="workspace-badge">{label(states, scan.state, t)}</span></p>
        <p>{t("محاولة", "Attempt")} {number(scan.attempt, lang)}</p>
        {scan.report_available && <a className="btn primary" href={reportLink(projectId, scan.id)}>{t("فتح التقرير", "Open report")}</a>}
        {canScan && isActive(scan.state) &&
          <button className="btn" onClick={cancel} disabled={cancelling}>{t("إلغاء الفحص", "Cancel scan")}</button>}
        {!!events.length && <ol className="workspace-timeline" aria-label={t("سجل الفحص", "Scan events")}>{events.map((item) => <li key={item.sequence}>
          <b>{label(states, item.kind, t)}</b>
          <p dir="auto">{t(item.detail, eventDetail(item))}</p>
          <time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString(lang === "ar" ? "ar-EG" : "en")}</time>
        </li>)}</ol>}
      </Panel>}
    </div>
  );
}

function ProjectSelector({ projects, value, onChange, t, required = false }) {
  return <label>{t("المشروع الحالي", "Project")}
    <select value={value || ""} onChange={(event) => onChange(event.target.value)} required={required}>
      <option value="">{t("اختار مشروع", "Select a project")}</option>
      {projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select>
  </label>;
}

function ScanList({ project, scans, lang, t }) {
  return scans.length ? <ul className="workspace-scan-list">{scans.map((item) => <li key={item.id}>
    <a href={scanLink(project, item.id)} className="workspace-scan-title">
      <FileText aria-hidden="true" size={17} /><bdi>{item.artifact.name}</bdi>
    </a>
    <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString(lang === "ar" ? "ar-EG" : "en")}</time>
    <span className="workspace-badge" data-state={item.state}>{label(states, item.state, t)}</span>
  </li>)}</ul> : <p>{t("لسه مفيش فحوصات للمشروع ده.", "This project has no scans yet.")}</p>;
}

function NewScan({ projects, project, snapshot, choose, navigate, lang }) {
  const t = translate(lang);
  const [step, setStep] = useState(0);
  const [kind, setKind] = useState("");
  const [source, setSource] = useState(null);
  const [enrich, setEnrich] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const heading = useRef(null);
  const request = useRef(null);
  const idempotency = useRef(crypto.randomUUID());
  const title = useId();
  const policy = snapshot?.policy;
  const candidates = projects.filter((item) => item.role !== "viewer");
  const access = candidates.some((item) => item.id === project?.id);
  const labels = [t("المشروع", "Project"), t("الملف", "Source"), t("المراجعة", "Review")];

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { if (step > 0) heading.current?.focus(); }, [step]);

  function updateEvidence(update) {
    update();
    setError("");
    idempotency.current = crypto.randomUUID();
  }

  async function launch(event) {
    event.preventDefault();
    if (request.current || !access || !source || !policy?.allowed_kinds.includes(kind)) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    try {
      const content = await encoded(source);
      const options = post({ kind, name: source.name, content, enrich });
      options.headers["Idempotency-Key"] = idempotency.current;
      const saved = await action(projectApi(project.id) + "/scans", { ...options, signal: controller.signal });
      if (!controller.signal.aborted) navigate(scanLink(project.id, saved.id));
    } catch (err) {
      if (!controller.signal.aborted) setError(errorText(err, t));
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  if (!candidates.length) return <Panel title={t("اختار مشروع للفحص", "Choose a project to scan")}>
    <p>{t("محتاج مشروع عندك فيه صلاحية تشغيل الفحص.", "Create a project or ask for permission to run scans in an existing project.")}</p>
    <a className="btn primary" href="/projects">{t("فتح المشاريع", "Open projects")}</a>
  </Panel>;

  return <section className="card project-panel workspace-wizard" aria-labelledby={title}>
    <ol className="workspace-steps" aria-label={t("خطوات الفحص", "Scan steps")}>{labels.map((text, index) =>
      <li key={index} aria-current={step === index ? "step" : undefined}><span>{number(index + 1, lang)}</span>{text}</li>)}</ol>
    <h2 id={title} ref={heading} tabIndex={-1}>{labels[step]}</h2>
    {error && <p className="workspace-error" role="alert">{error}</p>}
    {step === 0 && <form className="project-form" onSubmit={(event) => {
      event.preventDefault();
      if (access && policy) {
        setKind(policy.allowed_kinds[0] || "");
        setStep(1);
      }
    }}>
      <ProjectSelector projects={candidates} value={access ? project.id : ""} onChange={choose} t={t} required />
      {access && !policy && <p role="status">{t("بنحمّل سياسة المشروع…", "Loading project policy…")}</p>}
      <button className="btn primary" disabled={!access || !policy}>{t("متابعة إلى الملف", "Continue to source")}</button>
    </form>}
    {step === 1 && <form className="project-form" onSubmit={(event) => {
      event.preventDefault();
      if (!source?.size || source.size > 2_000_000) {
        setError(t("اختار ملف حجمه من ١ بايت لحد ٢ ميجابايت.", "Choose a file between 1 byte and 2 MB."));
        return;
      }
      setError("");
      setStep(2);
    }}>
      <label>{t("نوع المدخل", "Input type")}
        <select name="kind" value={kind} onChange={(event) => updateEvidence(() => {
          setKind(event.target.value);
          setSource(null);
        })}>
          {policy?.allowed_kinds.map((option) => <option key={option} value={option}>{label(kinds, option, t)}</option>)}
        </select>
      </label>
      <label className="workspace-upload"><UploadCloud size={25} aria-hidden="true"/>
        <span>{t("اختيار ملف", "Choose file")}</span>
        <input key={kind} name="file" type="file" accept={extensions[kind]} required={!source}
          onChange={(event) => updateEvidence(() => setSource(event.target.files[0] || null))} />
      </label>
      {source && <p dir="auto"><bdi>{source.name}</bdi> · <bdi>{number(source.size, lang)} {t("بايت", "bytes")}</bdi></p>}
      <p className="workspace-hint">{t("الحد الأقصى ٢ ميجابايت. الملف بيتحلّل من غير زيارة رابط الهدف.", "Maximum 2 MB. File analysis does not visit the target URL.")}</p>
      <div className="workspace-actions">
        <button className="btn" type="button" onClick={() => setStep(0)}>{t("رجوع", "Back")}</button>
        <button className="btn primary">{t("مراجعة الفحص", "Review scan")}</button>
      </div>
    </form>}
    {step === 2 && <form className="project-form" onSubmit={launch} aria-busy={busy}>
      <dl className="workspace-summary">
        <div><dt>{t("المشروع", "Project")}</dt><dd><bdi>{project?.name}</bdi></dd></div>
        <div><dt>{t("الملف", "File")}</dt><dd><bdi>{source?.name}</bdi></dd></div>
        <div><dt>{t("نوع المدخل", "Input type")}</dt><dd>{label(kinds, kind, t)}</dd></div>
        <div><dt>{t("عنوان مرجعي للهدف", "Target reference")}</dt><dd><bdi>{policy?.base_url || t("غير محدد", "Unspecified")}</bdi></dd></div>
        <div><dt>{t("نطاق الفحص", "Scan scope")}</dt><dd>{t("الملف المرفوع فقط", "Uploaded file only")}</dd></div>
      </dl>
      <label className="project-check">
        <input type="checkbox" checked={enrich} disabled={busy} onChange={(event) => updateEvidence(() => setEnrich(event.target.checked))}/>
        {t("ترتيب أولويات بالموديل عند توفره", "Prioritize results with a model if available")}
      </label>
      <div className="workspace-actions">
        <button className="btn" type="button" disabled={busy} onClick={() => setStep(1)}>{t("رجوع", "Back")}</button>
        <button className="btn primary" disabled={busy || !policy}>{busy ? t("جاري إرسال الفحص…", "Submitting scan…") : t("إرسال الفحص", "Submit scan")}</button>
      </div>
    </form>}
  </section>;
}

function Dashboard({ location, navigate, user, onLogout, lang }) {
  const t = translate(lang);
  const route = location.pathname.replace(/\/$/, "") || "/";
  const inProjects = route === "/projects";
  const inOverview = route === "/dashboard";
  const inScan = route === "/new-scan";
  const inHistory = route === "/scans";
  const inSettings = route === "/settings";
  const [organizations, setOrganizations] = useState([]);
  const [projects, setProjects] = useState([]);
  const [error, setError] = useState("");
  const [snapshotState, setSnapshot] = useState(null);
  const [memoryState, setMemory] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const selection = new URLSearchParams(location.search).get("project");
  const selected = selection || ((inOverview || inHistory || inSettings) ? projects[0]?.id : "");
  const project = projects.find((item) => item.id === selected);
  function choose(id) {
    setError("");
    navigate(id ? route + "?project=" + id : route);
  }
  const path = project ? projectApi(project.id) : null;
  const activePath = useRef(path);
  const snapshot = snapshotState?.path === path ? snapshotState : null;
  const memory = memoryState?.path === path ? memoryState.value : null;
  const manage = project && ["owner", "admin"].includes(project.role);
  useLayoutEffect(() => { activePath.current = path; }, [path]);

  async function loadMemory() {
    const value = await action(path + "/memory");
    if (activePath.current === path) setMemory({ path, value });
  }

  async function refreshDashboard(signal) {
    const [orgs, work] = await Promise.all([
      action(api + "/organizations", { signal }), action(api + "/projects", { signal }),
    ]);
    if (!signal?.aborted) {
      setOrganizations(orgs.organizations);
      setProjects(work.projects);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError("");
    refreshDashboard(controller.signal).catch((err) => {
      if (!controller.signal.aborted) setError(errorText(err, t));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [retry]);
  useEffect(() => {
    setSnapshot(null);
    setMemory(null);
    if (!path) return;
    const controller = new AbortController();
    const signal = controller.signal;
    Promise.all([action(path + "/policy", { signal }), action(path + "/scans", { signal })])
      .then(([policy, scans]) => {
        if (!signal.aborted && activePath.current === path) setSnapshot({ ...policy, path, scans: scans.scans });
      })
      .catch((err) => { if (!signal.aborted) setError(errorText(err, t)); });
    return () => controller.abort();
  }, [path, retry]);
  async function submit(event, operation) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setError("");
    setBusy(true);
    try { await operation(form); }
    catch (err) { setError(errorText(err, t)); }
    finally { setBusy(false); }
  }
  const title = {
    "/dashboard": t("نظرة عامة", "Overview"), "/projects": t("المشاريع", "Projects"),
    "/new-scan": t("فحص جديد", "New scan"), "/scans": t("الفحوصات", "Scans"),
    "/settings": t("الإعدادات", "Settings"),
  }[route];
  return <div className="project-workspace">
    <div className="project-header">
      <div><h1>{title}</h1>{inOverview && <p>{t("أهلًا،", "Welcome,")} <bdi>{user.display_name}</bdi></p>}</div>
      <div className="workspace-actions">
        {!inScan && !inSettings && <a className="btn primary" href={newScanLink(project?.role !== "viewer" ? project?.id : "")}><Plus size={17} aria-hidden="true" />{t("فحص جديد", "New scan")}</a>}
        <button className="btn" disabled={busy} onClick={async () => {
          setBusy(true);
          setError("");
          try { await action(api + "/auth/logout", { method: "POST" }); onLogout(); }
          catch (err) { setError(errorText(err, t)); }
          finally { setBusy(false); }
        }}>{t("تسجيل الخروج", "Sign out")}</button>
      </div>
    </div>
    {error && <p className="workspace-error" role="alert">{error} <button className="btn" onClick={() => setRetry((value) => value + 1)}>{t("إعادة المحاولة", "Retry")}</button></p>}
    {loading && <p role="status">{t("بنحمّل المشاريع…", "Loading projects…")}</p>}
    {!loading && inOverview && <>
      <div className="workspace-overview">
        <a href="/projects" className="card workspace-metric"><FolderOpen size={22} aria-hidden="true" /><strong>{number(projects.length, lang)}</strong><span>{t("المشاريع المتاحة", "Available projects")}</span></a>
        <a href="/projects" className="card workspace-metric"><ClipboardCheck size={22} aria-hidden="true" /><strong>{number(organizations.length, lang)}</strong><span>{t("المؤسسات", "Organizations")}</span></a>
        <a href={project ? "/scans?project=" + project.id : "/scans"} className="card workspace-metric"><ScanLine size={22} aria-hidden="true" /><strong>{snapshot ? number(snapshot.scans.filter((item) => isActive(item.state)).length, lang) : "—"}</strong><span>{t("فحوصات بتشتغل في المشروع المختار", "Active scans in the selected project")}</span></a>
      </div>
      <Panel title={t("نشاط المشروع", "Project activity")}>
        {projects.length ? <ProjectSelector projects={projects} value={project?.id} onChange={choose} t={t} /> : <a className="btn primary" href="/projects">{t("أنشئ أول مشروع", "Create your first project")}</a>}
        {project && snapshot && <ScanList project={project.id} scans={snapshot.scans.slice(0, 5)} lang={lang} t={t} />}
      </Panel>
    </>}
    {!loading && inScan && <NewScan key={selected || "new"} projects={projects} project={project} snapshot={snapshot} choose={choose} navigate={navigate} lang={lang} />}
    {!loading && inHistory && <Panel title={t("سجل الفحوصات", "Scan history")}>
      {projects.length ? <ProjectSelector projects={projects} value={project?.id} onChange={choose} t={t} /> : <a className="btn" href="/projects">{t("فتح المشاريع", "Open projects")}</a>}
      {project && !snapshot && !error && <p role="status">{t("بنحمّل الفحوصات…", "Loading scans…")}</p>}
      {project && snapshot && <ScanList project={project.id} scans={snapshot.scans} lang={lang} t={t} />}
    </Panel>}
    {inSettings && <Panel title={t("الحساب", "Account")}>
      <p><bdi>{user.display_name}</bdi></p>
      <dl className="workspace-summary"><div><dt>{t("معرّف المستخدم", "Account ID")}</dt><dd><bdi>{user.id}</bdi></dd></div></dl>
    </Panel>}
    {inSettings && <Panel title={t("الأدوات التقنية", "Technical tools")}>
      <a className="workspace-back" href="/checks">{t("كتالوج فحوصات المشاريع", "Security check catalog")} <ArrowUpRight size={15} aria-hidden="true"/></a>
      <a className="workspace-back" href="/demo?settings=models">{t("موديلات المختبر", "Demo models")} <ArrowUpRight size={15} aria-hidden="true"/></a>
    </Panel>}
    {inSettings && !loading && <details className="card project-panel workspace-advanced">
      <summary>{t("خيارات ترحيل التقارير", "Report migration")}</summary>
      {projects.length ? <ProjectSelector projects={projects} value={project?.id} onChange={choose} t={t} /> : <p>{t("أنشئ مشروع عشان تربط بيه تقرير.", "Create a project to import an existing report.")}</p>}
      {project?.role === "viewer" && <p>{t("استيراد التقرير يحتاج صلاحية المحلل أو الإدارة.", "Report import requires analyst or management access.")}</p>}
      {project && project.role !== "viewer" && <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
        const id = encodeURIComponent(data.get("id").trim());
        await action(path + "/reports/" + id + "/claim", post({ confirm: true }));
        if (activePath.current === path) navigate(reportLink(project.id, id));
      })}>
        <label>{t("معرّف التقرير", "Report ID")}<input name="id" dir="ltr" required pattern="[a-f0-9]{32}" /></label>
        <label className="project-check"><input type="checkbox" required /> {t("أوافق على إضافة نسخة للمشروع", "Add a copy of this report to the project")}</label>
        <button className="btn" disabled={busy}>{t("ربط التقرير", "Import report")}</button>
      </form>}
    </details>}
    {inProjects && !loading && <Panel title={t("المؤسسات والمشاريع", "Organizations and projects")}>
      <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
        await action(api + "/organizations", post({ name: data.get("name") }));
        await refreshDashboard();
      })}>
        <label>{t("اسم المؤسسة", "Organization name")}<input name="name" maxLength={120} required /></label>
        <button className="btn" disabled={busy}>{t("إنشاء مؤسسة", "Create organization")}</button>
      </form>
      {organizations.some((org) => ["owner", "admin"].includes(org.role)) && (
        <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          const created = await action(api + "/organizations/" + data.get("org") + "/projects", post({ name: data.get("name") }));
          await refreshDashboard();
          navigate("/projects?project=" + created.id);
        })}>
          <label>{t("المؤسسة", "Organization")}<select name="org">{organizations.filter((org) => ["owner", "admin"].includes(org.role))
            .map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}</select></label>
          <label>{t("اسم المشروع", "Project name")}<input name="name" maxLength={120} required /></label>
          <button className="btn" disabled={busy}>{t("إنشاء مشروع", "Create project")}</button>
        </form>
      )}
      <ProjectSelector projects={projects} value={project?.id} onChange={choose} t={t} />
    </Panel>}
    {inProjects && project && !snapshot && !error && <p role="status">{t("بنحمّل تفاصيل المشروع…", "Loading project details…")}</p>}
    {inProjects && project && snapshot && <div className="project-grid" key={project.id}>
      <Panel title={t("فحوصات المشروع", "Project scans")}>
        <div className="workspace-actions">
          <a className="btn" href={reportLink(project.id)}>{t("تقارير المشروع", "Project reports")}</a>
        </div>
        <ScanList project={project.id} scans={snapshot.scans.slice(0, 5)} lang={lang} t={t} />
        {snapshot.scans.length > 5 && <a href={"/scans?project=" + project.id}>{t("كل فحوصات المشروع", "All project scans")}</a>}
      </Panel>
      {manage && <Panel title={t("سياسة المدخلات والهدف", "Input policy and target")}>
        <p>{t("عنوان الهدف للربط بس. الفحص بيحلل الملفات اللي رفعتها.", "The target is a reference. Scans analyze the files you upload.")}</p>
        <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          const policy = await action(path + "/policy", json("PUT", {
            allowed_kinds: data.getAll("kinds"), base_url: data.get("url") || null,
            rules: JSON.parse(data.get("rules") || "{}"),
          }));
          if (activePath.current === path) setSnapshot((old) => old?.path === path ? { ...old, ...policy } : old);
        })}>
          <label>{t("عنوان الهدف", "Target reference URL")}<input name="url" type="url" dir="ltr" defaultValue={snapshot.policy.base_url || ""} /></label>
          <fieldset><legend>{t("أنواع المدخل المسموحة", "Allowed input types")}</legend>
            {Object.entries(kinds).map(([id, titles]) => <label className="project-check" key={id}>
              <input type="checkbox" name="kinds" value={id} defaultChecked={snapshot.policy.allowed_kinds.includes(id)} /> {t(...titles)}
            </label>)}
          </fieldset>
          <label>{t("خيارات القواعد (JSON)", "Rule options (JSON)")}<textarea name="rules" dir="ltr" rows={4}
            defaultValue={JSON.stringify(Object.fromEntries(Object.entries(snapshot.policy)
              .filter(([key]) => !["allowed_kinds", "base_url"].includes(key))), null, 2)} /></label>
          <button className="btn" disabled={busy}>{t("حفظ السياسة", "Save policy")}</button>
        </form>
      </Panel>}
      <Panel title={t("ذاكرة المشروع", "Project knowledge")}>
        <button className="btn" onClick={async () => {
          try { await loadMemory(); }
          catch (err) { setError(errorText(err, t)); }
        }}>{t("تحميل سياق المشروع", "Load project context")}</button>
        {memory && <dl className="spec">{Object.entries({
          working: t("حالة التشغيل", "Current run"), episodic: t("تاريخ الفحوصات", "Scan history"), semantic: t("المراجع", "References"),
          procedural: t("القواعد", "Rules"), project: t("سياسة المشروع", "Project policy"), finding: t("تاريخ النتائج", "Finding history"),
        }).map(([id, title]) => <React.Fragment key={id}>
          <dt>{title}</dt><dd>{Array.isArray(memory[id]) ? memory[id].length : memory[id].version}</dd>
        </React.Fragment>)}</dl>}
        {memory?.semantic?.map((note) => <article key={note.id}><h3>{note.title}</h3><p>{note.note}</p>
          <p dir="auto">{note.reference}</p>{manage && <button className="btn" onClick={async () => {
            try { await action(path + "/memory/knowledge/" + note.id, { method: "DELETE" });
              await loadMemory(); }
            catch (err) { setError(errorText(err, t)); }
          }}>{t("إلغاء المرجع", "Revoke reference")}</button>}</article>)}
        {manage && <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          await action(path + "/memory/knowledge", post(Object.fromEntries(data)));
          await loadMemory();
        })}>
          <label>{t("العنوان", "Title")}<input name="title" maxLength={160} required /></label>
          <label>{t("المصدر", "Reference")}<input name="reference" maxLength={500} required /></label>
          <label>{t("المعلومة", "Note")}<textarea name="note" maxLength={2000} required /></label>
          <button className="btn" disabled={busy}>{t("إضافة مرجع", "Add reference")}</button>
        </form>}
      </Panel>
      {manage && <Panel title={t("إدارة صلاحيات الوصول", "Manage access")}>
        <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          const userId = encodeURIComponent(data.get("user_id").trim());
          const target = data.get("target");
          const remove = data.get("change") === "revoke";
          const endpoint = target === "project" ? path + "/grants" : api + "/organizations/" + project.org_id + "/members";
          await action(endpoint + (remove ? "/" + userId : ""), remove ? { method: "DELETE" } : post(
            target === "project" ? { user_id: userId } : { user_id: userId, role: data.get("role") },
          ));
          await refreshDashboard();
        })}>
          <label>{t("معرّف المستخدم", "Account ID")}<input name="user_id" dir="ltr" required pattern="[a-f0-9]{32}" /></label>
          <label>{t("النطاق", "Scope")}<select name="target"><option value="project">{t("إذن المشروع", "Project grant")}</option>
            {project.role === "owner" && <option value="org">{t("عضوية المؤسسة", "Organization membership")}</option>}</select></label>
          <label>{t("الدور عند إضافة العضوية", "Membership role")}<select name="role"><option value="viewer">Viewer</option>
            <option value="analyst">Analyst</option><option value="admin">Admin</option></select></label>
          <label>{t("الإجراء", "Action")}<select name="change"><option value="grant">{t("إضافة أو تعديل", "Grant or update")}</option><option value="revoke">{t("إبطال", "Revoke")}</option></select></label>
          <button className="btn" disabled={busy}>{t("حفظ الصلاحية", "Save access")}</button>
        </form>
      </Panel>}
    </div>}
  </div>;
}

function ProjectAccount({ location, navigate, lang }) {
  const t = translate(lang);
  const [failure, setFailure] = useState(null);
  const [retry, setRetry] = useState(0);
  const [user, setUser] = useState(undefined);
  const signingIn = /^\/signin\/?$/.test(location.pathname);
  useEffect(() => {
    const controller = new AbortController();
    setFailure(null);
    action(api + "/auth/me", { signal: controller.signal }).then(
      (account) => { if (!controller.signal.aborted) setUser(account); },
      (err) => {
        if (!controller.signal.aborted) {
          if (err.status === 401) setUser(null);
          else setFailure(err);
        }
      },
    );
    return () => controller.abort();
  }, [retry]);
  useEffect(() => {
    if (user && signingIn) navigate("/dashboard", { replace: true });
  }, [user, signingIn, navigate]);

  if (failure) return <p className="workspace-error" role="alert">{errorText(failure, t)} <button className="btn" onClick={() => setRetry((value) => value + 1)}>{t("إعادة المحاولة", "Retry")}</button></p>;
  if (user === undefined) return <p role="status">{t("جاري التحقق من الجلسة…", "Checking your session…")}</p>;
  if (!user) return <AccountAccess onAuthenticated={setUser} lang={lang} />;
  if (signingIn) return <p role="status">{t("بنفتح مساحة العمل…", "Opening your workspace…")}</p>;
  const match = /^\/projects\/([a-f0-9]{32})\/scans\/([a-f0-9]{32})\/?$/.exec(location.pathname);
  if (match) return <ScanStatus key={match[2]} projectId={match[1]} scanId={match[2]} lang={lang} />;
  return <Dashboard location={location} navigate={navigate} user={user} onLogout={() => setUser(null)} lang={lang} />;
}

export function Platform({ location, navigate, lang = "ar" }) {
  return <ProjectAccount location={location} navigate={navigate} lang={lang} />;
}
