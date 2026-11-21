import React, { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Activity, ArrowLeft, ArrowRight, Building2, Eye, EyeOff, FileText, FolderOpen, Mail, Plus, ShieldCheck, UploadCloud } from "lucide-react";
import { post } from "./data";
import { api, action, errorText, json, translate } from "./platformClient";
import { AccountSettings } from "./AccountSettings";
import { ProjectAccess } from "./ProjectAccess";
import { DirectoryLink, ProjectDirectory } from "./ProjectDirectory";
import "./platform.css";
import "./scan-source.css";

const kinds = {
  html: ["HTML", "HTML"],
  repository: ["كود المشروع · ZIP", "Project source · ZIP"],
  har: ["موقع ويب · HAR", "Website evidence · HAR"],
  config: ["لقطة إعدادات JSON", "Configuration JSON"],
  openapi: ["وصف API · OpenAPI", "API description · OpenAPI"],
  zap: ["تقرير ZAP سلبي", "Saved passive ZAP report"],
  github: ["لقطة GitHub", "GitHub snapshot"],
};
const extensions = { html: ".html,.htm", repository: ".zip", har: ".har", config: ".json", openapi: ".json", zap: ".json" };
const sourceHints = {
  repository: ["ارفع نسخة ZIP فيها ملفات الكود والإعدادات.", "Upload a ZIP containing source and configuration files."],
  html: ["ارفع ملف صفحة واحدة.", "Upload an individual page file."],
  har: ["ارفع استجابات محفوظة ومنقّحة من متصفحك.", "Upload a sanitized capture saved from your browser."],
  openapi: ["ارفع وصف OpenAPI 3.0 أو 3.1 بصيغة JSON.", "Upload an OpenAPI 3.0 or 3.1 JSON document."],
  config: ["ارفع حزمة JSON فيها نصوص ملفات الإعدادات.", "Upload a JSON bundle of configuration files."],
  zap: ["ارفع تقرير Traditional JSON محفوظ بعد الرصد السلبي.", "Upload a Traditional JSON report saved from passive observation."],
  github: ["اختار إصدار ثابت من مستودع GitHub المرتبط بالمشروع.", "Select an exact commit from the repository connected to this project."],
};
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
const label = (table, value, t) => table[value] ? t(...table[value]) : value;
const number = (value, lang) => new Intl.NumberFormat(lang === "ar" ? "ar-EG" : "en").format(value);
const newScanLink = (id) => id ? `/new-scan?project=${id}` : "/new-scan";
const projectApi = (id) => `${api}/projects/${id}`;
const scanLink = (project, scan) => `/projects/${project}/scans/${scan}`;
const reportLink = (project, report = "") => `/reports${report && "/" + report}?project=${project}`;
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
  const title = useRef(null);
  const focusTitle = useRef(false);
  const passwordId = useId();
  const hintId = useId();
  const register = mode === "register";
  const DirectionArrow = lang === "ar" ? ArrowLeft : ArrowRight;

  useEffect(() => {
    const controller = new AbortController();
    action(api + "/auth/options", { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setOptions(value); },
      (err) => { if (!controller.signal.aborted) setOptionsError(errorText(err, t)); },
    );
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => () => activeRequest.current?.abort(), []);
  useEffect(() => {
    if (focusTitle.current) title.current?.focus();
  }, [mode]);

  function changeMode(next) {
    if (next === mode) return;
    focusTitle.current = true;
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
        ...post({
          email: data.get("email").trim(), password,
          ...(register ? { first_name: data.get("first_name").trim(), last_name: data.get("last_name").trim() } : {}),
        }),
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
    <section className="account-layout" aria-labelledby={titleId}>
      <aside className="account-context" aria-label={t("مساحة مرصد", "Marsad workspace")}>
        <div className="account-context-mark" aria-hidden="true"><ShieldCheck size={26} strokeWidth={1.7} /></div>
        <div className="account-context-copy">
          <strong>{t("من ملفات المشروع إلى تقرير واضح.", "From project files to a clear report.")}</strong>
          <ul>
            <li><FolderOpen size={18} aria-hidden="true" />{t("نظّم ملفاتك حسب المشروع", "Organize files by project")}</li>
            <li><FileText size={18} aria-hidden="true" />{t("راجع الدليل وخطوات الإصلاح", "Review evidence and fixes")}</li>
          </ul>
        </div>
        <div className="account-context-grid" aria-hidden="true"><i /><i /><i /></div>
      </aside>
      <div className="project-panel project-account">
        <header className="project-account-heading">
          <h1 id={titleId} ref={title} tabIndex={-1}>{register ? t("أنشئ حسابك", "Create your account") : t("سجّل دخولك إلى مرصد", "Sign in to Marsad")}</h1>
          <p>{register ? t("ابدأ مشروعك الأول واحتفظ بتقاريرك في مكان واحد.", "Start your first project and keep your reports in one place.")
            : t("ادخل على مشاريعك وتقاريرك.", "Access your projects and reports.")}</p>
        </header>
        {!options && !optionsError && <p role="status">{t("جاري تحميل طرق تسجيل الدخول…", "Loading sign-in options…")}</p>}
        {optionsError && <div className="project-account-feedback">
          <p className="error" role="alert">{optionsError}</p>
          <button className="btn" type="button" onClick={() => {
            setOptionsError("");
            setAttempt((value) => value + 1);
          }}>{t("إعادة المحاولة", "Retry")}</button>
        </div>}
        {options?.password && <form className="project-form project-account-form" onSubmit={submit} aria-busy={busy}>
          {register && <div className="scan-source-options">
            <label>{t("الاسم الأول", "First name")}
              <input name="first_name" dir="auto" autoComplete="given-name" maxLength={80} required disabled={busy} />
            </label>
            <label>{t("اسم العائلة", "Last name")}
              <input name="last_name" dir="auto" autoComplete="family-name" maxLength={80} required disabled={busy} />
            </label>
          </div>}
          <label>{t("البريد الإلكتروني", "Email")}
            <span className="account-input">
              <Mail size={17} aria-hidden="true" />
              <input name="email" type="email" autoComplete="username" dir="ltr" maxLength={254} required disabled={busy} />
            </span>
          </label>
          <div className="account-password">
            <label htmlFor={passwordId}>{t("كلمة المرور", "Password")}</label>
            <div className="account-input account-secret">
              <input key={mode} id={passwordId} name="password" type={showPassword ? "text" : "password"} dir="ltr"
                autoComplete={register ? "new-password" : "current-password"}
                aria-describedby={register ? hintId : undefined}
                maxLength={256} required disabled={busy} />
              <button type="button" aria-controls={passwordId} disabled={busy}
                aria-label={showPassword ? t("إخفاء كلمة المرور", "Hide password") : t("إظهار كلمة المرور", "Show password")}
                onClick={() => setShowPassword((value) => !value)}>
                {showPassword ? <EyeOff size={19} aria-hidden="true" /> : <Eye size={19} aria-hidden="true" />}
              </button>
            </div>
            {register && <p id={hintId} className="project-account-hint">{t("من ١٢ إلى ١٢٨ حرف.", "12 to 128 characters.")}</p>}
          </div>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn primary account-submit" disabled={busy}>
            {busy ? (register ? t("جاري إنشاء الحساب…", "Creating account…") : t("جاري تسجيل الدخول…", "Signing in…"))
              : (register ? t("إنشاء الحساب", "Create account") : t("تسجيل الدخول", "Sign in"))}
            <DirectionArrow size={18} aria-hidden="true" />
          </button>
        </form>}
        {options?.oidc && <a className="btn account-organization" href={api + "/auth/login"}>
          <Building2 size={18} aria-hidden="true" />{t("الدخول بحساب المؤسسة", "Sign in with your organization")}
        </a>}
        {options && !options.password && !options.oidc && <p role="status">{t("تسجيل الدخول للمشاريع غير متاح حاليًا.", "Project sign-in is currently unavailable.")}</p>}
        {options?.password && options.registration && <div className="account-mode-switch">
          <span>{register ? t("عندك حساب بالفعل؟", "Already have an account?") : t("أول مرة تستخدم مرصد؟", "New to Marsad?")}</span>
          <button type="button" disabled={busy} onClick={() => changeMode(register ? "login" : "register")}>
            {register ? t("عندي حساب", "I have an account") : t("إنشاء حساب", "Create an account")}
          </button>
        </div>}
      </div>
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
      {scan && <Panel title={<bdi>{scan.artifact.name}</bdi>}>
        <p role="status" className="workspace-scan-status"><span className="workspace-badge" data-state={scan.state}>{label(states, scan.state, t)}</span></p>
        {scan.report_available && <a className="btn primary" href={reportLink(projectId, scan.id)}>{t("فتح التقرير", "Open report")}</a>}
        {canScan && isActive(scan.state) &&
          <button className="btn" onClick={cancel} disabled={cancelling}>{t("إلغاء الفحص", "Cancel scan")}</button>}
        {!!events.length && <section className="workspace-management">
          <h3>{t("سجل الفحص", "Scan activity")}</h3>
          <ol className="workspace-timeline" aria-label={t("سجل الفحص", "Scan events")}>{events.map((item) => <li key={item.sequence}>
          <b>{label(states, item.kind, t)}</b>
          <p dir="auto">{t(item.detail, eventDetail(item))}</p>
          <time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString(lang === "ar" ? "ar-EG" : "en")}</time>
          </li>)}</ol>
        </section>}
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

function ScanList({ project, scans, lang, t, emptyMessage }) {
  return scans.length ? <ul className="workspace-scan-list">{scans.map((item) => <li key={item.id}>
    <a href={scanLink(project, item.id)} className="workspace-scan-title">
      <FileText aria-hidden="true" size={17} /><bdi>{item.artifact.name}</bdi>
    </a>
    <time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString(lang === "ar" ? "ar-EG" : "en")}</time>
    <span className="workspace-badge" data-state={item.state}>{label(states, item.state, t)}</span>
  </li>)}</ul> : <p>{emptyMessage || t("لسه مفيش فحوصات للمشروع ده.", "This project has no scans yet.")}</p>;
}

function NewScan({ projects, project, choose, navigate, lang }) {
  const t = translate(lang);
  const [step, setStep] = useState(0);
  const [kind, setKind] = useState("");
  const [source, setSource] = useState(null);
  const [githubSource, setGithubSource] = useState(null);
  const [commit, setCommit] = useState("");
  const [targetReference, setTargetReference] = useState("");
  const [enrich, setEnrich] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [profile, setProfile] = useState(null);
  const [profileFailure, setProfileFailure] = useState(null);
  const [retryProfile, setRetryProfile] = useState(0);
  const [staleProfile, setStaleProfile] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const heading = useRef(null);
  const request = useRef(null);
  const idempotency = useRef(crypto.randomUUID());
  const title = useId();
  const candidates = projects.filter((item) => item.role !== "viewer");
  const access = candidates.some((item) => item.id === project?.id);
  const policyPath = access ? projectApi(project.id) + "/scan-profile" : null;
  const profileValue = profile?.path === policyPath ? profile.value : null;
  const profileError = profileFailure?.path === policyPath ? profileFailure.error : null;
  const model = profileValue?.model_connection;
  const limit = profileValue?.max_bytes;
  const allowedKinds = profileValue?.allowed_kinds ?? [];
  const sourceKinds = allowedKinds.includes("repository") ? [...allowedKinds, "github"] : allowedKinds;
  const useGithub = kind === "github";
  const githubPath = useGithub && access && allowedKinds.includes("repository") ? projectApi(project.id) + "/github-source" : null;
  const githubView = githubSource?.path === githubPath ? githubSource : null;
  const githubConnection = githubView?.value?.available ? githubView.value.connection : null;
  const validCommit = /^[a-f0-9]{40}$/i.test(commit.trim());
  const websiteEvidence = ["har", "openapi", "zap"].includes(kind);
  const requiresAddress = kind === "zap" && !profileValue?.asset_linked;
  const labels = [t("المشروع", "Project"), t("الملف", "Source"), t("المراجعة", "Review")];

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { if (step > 0) heading.current?.focus(); }, [step]);
  useEffect(() => {
    if (!policyPath) return;
    const controller = new AbortController();
    action(policyPath, { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setProfile({ path: policyPath, value }); },
      (error) => { if (!controller.signal.aborted) setProfileFailure({ path: policyPath, error }); },
    );
    return () => controller.abort();
  }, [policyPath, retryProfile]);
  useEffect(() => {
    if (!githubPath) return;
    const controller = new AbortController();
    action(githubPath, { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setGithubSource({ path: githubPath, value }); },
      (error) => { if (!controller.signal.aborted) setGithubSource({ path: githubPath, error }); },
    );
    return () => controller.abort();
  }, [githubPath, retryProfile]);

  function updateEvidence(update) {
    update();
    setAcknowledged(false);
    setError("");
    idempotency.current = crypto.randomUUID();
  }

  async function launch(event) {
    event.preventDefault();
    const ready = useGithub ? githubConnection && validCommit : source && allowedKinds.includes(kind);
    if (request.current || !access || !ready || !acknowledged) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    try {
      const input = useGithub ? { commit: commit.trim().toLowerCase() } : {
        kind, name: source.name, content: await encoded(source),
        ...(websiteEvidence && targetReference.trim() ? { target_reference: targetReference.trim() } : {}),
      };
      if (controller.signal.aborted) return;
      const options = post({
        ...input, scope_version: profileValue.scope_version, acknowledge_scope: true,
        ...(enrich && model ? { model_connection: model.id } : {}),
      });
      options.headers["Idempotency-Key"] = idempotency.current;
      const saved = await action((useGithub ? githubPath : projectApi(project.id)) + "/scans", { ...options, signal: controller.signal });
      if (!controller.signal.aborted) navigate(scanLink(project.id, saved.id));
    } catch (err) {
      if (!controller.signal.aborted) {
        setStaleProfile(err.status === 409);
        setError(errorText(err, t));
      }
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
    {staleProfile && <button className="btn" onClick={() => {
      setStaleProfile(false);
      setProfile(null);
      setAcknowledged(false);
      setError("");
      setStep(0);
      setRetryProfile((value) => value + 1);
      idempotency.current = crypto.randomUUID();
    }}>{t("راجع نطاق الفحص من جديد", "Review the updated scope")}</button>}
    {profileError && <p className="workspace-error" role="alert">{errorText(profileError, t)} <button type="button" className="btn" onClick={() => {
      setProfileFailure(null);
      setRetryProfile((value) => value + 1);
    }}>{t("إعادة المحاولة", "Retry")}</button></p>}
    {step === 0 && <form className="project-form" onSubmit={(event) => {
      event.preventDefault();
      if (access && allowedKinds.length) {
        if (!sourceKinds.includes(kind)) {
          setKind(allowedKinds[0]);
          setSource(null);
        }
        setStep(1);
      }
    }}>
      <ProjectSelector projects={candidates} value={access ? project.id : ""} onChange={(value) => updateEvidence(() => {
        choose(value);
        setKind("");
        setSource(null);
        setCommit("");
        setTargetReference("");
      })} t={t} required />
      {access && !profileValue && !profileError && <p role="status">{t("بنحمّل نطاق الفحص…", "Loading scan scope…")}</p>}
      {profileValue && sourceKinds.length === 1 && <p className="workspace-hint">
        {t("سياسة المشروع بتسمح بنوع مدخل واحد حاليًا.", "The current project policy allows one input type.")}
      </p>}
      <button className="btn primary" disabled={!access || !allowedKinds.length}>{t("متابعة إلى الملف", "Continue to source")}</button>
    </form>}
    {step === 1 && <form className="project-form" onSubmit={(event) => {
      event.preventDefault();
      if (useGithub) {
        if (githubConnection && validCommit) setStep(2);
        return;
      }
      if (!source?.size || source.size > limit) {
        setError(t("اختار ملف بالحجم المسموح.", "Choose a file within the upload limit."));
        return;
      }
      const matching = extensions[kind].split(",").some((extension) => source.name.toLowerCase().endsWith(extension));
      if (!matching) {
        setError(t("امتداد الملف لازم يطابق نوع المدخل.", "The file extension must match the selected input."));
        return;
      }
      setError("");
      setStep(2);
    }}>
      <fieldset className="scan-source-picker">
        <legend>{t("نوع المدخل", "Input type")}</legend>
        <div className="scan-source-options">
          {sourceKinds.map((option) => <label className="scan-kind" key={option}>
            <input type="radio" name="kind" value={option} checked={kind === option}
              onChange={() => updateEvidence(() => {
                setKind(option);
                setSource(null);
                setCommit("");
                setTargetReference("");
              })} />
            <span><strong>{label(kinds, option, t)}</strong><small>{t(...sourceHints[option])}</small></span>
          </label>)}
        </div>
      </fieldset>
      {useGithub ? <>
        {!githubView && <p role="status">{t("بنحمّل اتصال GitHub…", "Loading the GitHub connection…")}</p>}
        {githubView?.error && <p className="workspace-error" role="alert">{errorText(githubView.error, t)}{" "}
          <button type="button" className="btn" onClick={() => {
            setGithubSource(null);
            setRetryProfile((value) => value + 1);
          }}>{t("إعادة المحاولة", "Retry")}</button>
        </p>}
        {githubView?.value && !githubConnection && <p role="status">{t(
          "محتاج اتصال GitHub مُفعّل ومُصرّح للمشروع. صاحب المؤسسة أو المدير يقدر يراجعه من الحساب. تقدر تكمل برفع ZIP.",
          "This project needs an authorized GitHub connection. An organization owner or admin can manage it in Account. You can continue with a ZIP upload."
        )}</p>}
        {githubConnection && <>
          <p>{t("المستودع المرتبط", "Connected repository")} · <bdi>{githubConnection.repository}</bdi></p>
          <label>{t("معرّف الـ commit الكامل", "Full commit SHA")}
            <input name="commit" dir="ltr" autoComplete="off" spellCheck={false} required minLength={40} maxLength={40}
              pattern="[a-fA-F0-9]{40}" value={commit} onChange={(event) => updateEvidence(() => setCommit(event.target.value))} />
          </label>
        </>}
      </> : <>
      <label className="workspace-upload"><UploadCloud size={25} aria-hidden="true"/>
        <span>{t("اختيار ملف", "Choose file")}</span>
        <input key={kind} name="file" type="file" accept={extensions[kind]} required={!source}
          onChange={(event) => updateEvidence(() => setSource(event.target.files[0] || null))} />
      </label>
      {source && <p dir="auto"><bdi>{source.name}</bdi> · <bdi>{number(source.size, lang)} {t("بايت", "bytes")}</bdi></p>}
      <p className="workspace-hint">{t("الحد الأقصى", "Limit")} <bdi>{number(limit / 1_000_000, lang)} {t("ميجابايت", "MB")}</bdi></p>
      {websiteEvidence && <label>{requiresAddress ? t("عنوان الموقع", "Website address") : t("عنوان الموقع · اختياري", "Website address · optional")}
        <input type="url" dir="ltr" value={targetReference} maxLength={250} required={requiresAddress}
          placeholder="https://example.com" onChange={(event) => updateEvidence(() => setTargetReference(event.target.value))} />
        <small className="workspace-hint">{t("العنوان بيربط الدليل بالموقع. التحليل بيستخدم الملف المرفوع.",
          "The address associates the evidence with a site. The scan uses the uploaded file.")}</small>
      </label>}
      </>}
      <div className="workspace-actions">
        <button className="btn" type="button" onClick={() => setStep(0)}>{t("رجوع", "Back")}</button>
        <button className="btn primary" disabled={useGithub && (!githubConnection || !validCommit)}>{t("مراجعة الفحص", "Review scan")}</button>
      </div>
    </form>}
    {step === 2 && <form className="project-form" onSubmit={launch} aria-busy={busy}>
      <dl className="workspace-summary">
        <div><dt>{t("المشروع", "Project")}</dt><dd><bdi>{project?.name}</bdi></dd></div>
        <div><dt>{useGithub ? t("المستودع", "Repository") : t("الملف", "File")}</dt><dd><bdi>{useGithub ? githubConnection?.repository : source?.name}</bdi></dd></div>
        {useGithub && <div><dt>Commit SHA</dt><dd><bdi>{commit}</bdi></dd></div>}
        <div><dt>{t("نوع المدخل", "Input type")}</dt><dd>{label(kinds, kind, t)}</dd></div>
        <div><dt>{t("نطاق الفحص", "Scan scope")}</dt><dd>{useGithub ? t("لقطة واحدة للنسخة المحددة", "One snapshot at the selected commit") : t("الملف المرفوع فقط", "Uploaded file only")}</dd></div>
        {websiteEvidence && targetReference.trim() && <div><dt>{t("مرجع الموقع", "Website reference")}</dt><dd><bdi>{targetReference.trim()}</bdi></dd></div>}
      </dl>
      {model && <label className="project-check">
        <input type="checkbox" checked={enrich} disabled={busy} onChange={(event) => {
          setEnrich(event.target.checked);
          setError("");
          idempotency.current = crypto.randomUUID();
        }} />
        {t("استخدم ترتيب الأولويات الذكي", "Use smart prioritization")}
      </label>}
      <label className="project-check workspace-ack">
        <input name="acknowledge_scope" type="checkbox" checked={acknowledged} disabled={busy} required
          onChange={(event) => setAcknowledged(event.target.checked)} />
        {useGithub ? t("عندي صلاحية لمراجعة لقطة المستودع دي", "I have permission to review this repository snapshot") : t("عندي صلاحية لمراجعة الملف ده", "I have permission to review this file")}
      </label>
      <div className="workspace-actions">
        <button className="btn" type="button" disabled={busy} onClick={() => setStep(1)}>{t("رجوع", "Back")}</button>
        <button className="btn primary" disabled={busy || !profileValue || !acknowledged || staleProfile}>{busy ? t("جاري إرسال الفحص…", "Submitting scan…") : t("إرسال الفحص", "Submit scan")}</button>
      </div>
    </form>}
  </section>;
}

function Dashboard({ location, navigate, user, lang, invitationRevision }) {
  const t = translate(lang);
  const route = location.pathname.replace(/\/$/, "") || "/";
  const inProjects = route === "/projects";
  const inOverview = route === "/dashboard";
  const inScan = route === "/new-scan";
  const inHistory = route === "/scans";
  const [organizations, setOrganizations] = useState([]);
  const [projects, setProjects] = useState([]);
  const [error, setError] = useState("");
  const [snapshotState, setSnapshot] = useState(null);
  const [memoryState, setMemory] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [retry, setRetry] = useState(0);
  const params = new URLSearchParams(location.search);
  const selection = params.get("project");
  const fallback = inOverview || inHistory ? projects[0]?.id : "";
  const selected = selection && (!inOverview || projects.some((item) => item.id === selection))
    ? selection : fallback;
  const project = projects.find((item) => item.id === selected);
  function choose(id) {
    setError("");
    navigate(id ? route + "?project=" + id : route);
  }
  const path = project ? projectApi(project.id) : null;
  const activePath = useRef(path);
  const memory = memoryState?.path === path ? memoryState.value : null;
  const manage = project && ["owner", "admin"].includes(project.role);
  const requestedView = params.get("view");
  const view = requestedView === "references" || (manage && ["management", "access"].includes(requestedView))
    ? requestedView : "activity";
  const policyView = inProjects && view === "management";
  const recentView = inProjects && view === "activity";
  const scansView = inOverview || inHistory || recentView;
  const needsSnapshot = policyView || scansView;
  const snapshotKey = path && [path, route, view].join(":");
  const snapshot = snapshotState?.key === snapshotKey ? snapshotState : null;
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
  }, [retry, invitationRevision]);
  useEffect(() => {
    setSnapshot(null);
    setMemory(null);
    if (!path || !needsSnapshot) return;
    const controller = new AbortController();
    const signal = controller.signal;
    Promise.all([
      policyView ? action(path + "/policy", { signal }) : null,
      scansView ? action(path + "/scans", { signal }) : null,
      recentView ? action(path + "/reports", { signal }) : null,
    ]).then(([policy, scans, reports]) => {
        if (!signal.aborted && activePath.current === path) setSnapshot({
          ...policy, key: snapshotKey, scans: scans?.scans || [], reports: reports?.reports || [],
        });
      })
      .catch((err) => { if (!signal.aborted) setError(errorText(err, t)); });
    return () => controller.abort();
  }, [path, snapshotKey, policyView, scansView, recentView, needsSnapshot, retry]);
  useEffect(() => {
    if (!path || !inProjects || view !== "references") return;
    const controller = new AbortController();
    action(path + "/memory", { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setMemory({ path, value }); },
      (err) => { if (!controller.signal.aborted) setError(errorText(err, t)); },
    );
    return () => controller.abort();
  }, [path, inProjects, view, retry]);
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
  }[route];
  const displayName = (user.display_name || "").trim();
  const showName = displayName && !displayName.includes("@");
  const showNewScan = inOverview ? projects.some((item) => item.role !== "viewer")
    : inProjects && project && project.role !== "viewer";
  return <div className="project-workspace">
    <div className="project-header">
      <div>{inProjects && project && <DirectoryLink className="workspace-back" to={"/projects?org=" + project.org_id} navigate={navigate}>{t("كل المشاريع", "All projects")}</DirectoryLink>}
        <h1>{inProjects && project ? <bdi>{project.name}</bdi> : title}</h1>
        {inOverview && <p>{showName ? <>{t("أهلًا،", "Welcome,")} <bdi>{displayName}</bdi></> : t("أهلًا بيك", "Welcome")}</p>}</div>
      {!loading && showNewScan && <DirectoryLink className="btn primary"
        to={newScanLink(project?.role !== "viewer" ? project?.id : "")} navigate={navigate}>
        <Plus size={17} aria-hidden="true" />{t("فحص جديد", "New scan")}
      </DirectoryLink>}
    </div>
    {error && <p className="workspace-error" role="alert">{error} <button className="btn" onClick={() => setRetry((value) => value + 1)}>{t("إعادة المحاولة", "Retry")}</button></p>}
    {loading && <p role="status">{t("بنحمّل المشاريع…", "Loading projects…")}</p>}
    {!loading && inOverview && !error && <section className="card project-panel workspace-activity" aria-labelledby="overview-activity">
      <div className="directory-heading">
        <div>
          <h2 id="overview-activity"><Activity size={20} aria-hidden="true" />{t("آخر النشاط", "Recent activity")}</h2>
          {projects.length === 1 && <p><bdi>{project?.name}</bdi></p>}
        </div>
        {projects.length > 1 && <ProjectSelector projects={projects} value={project?.id} onChange={choose} t={t} required />}
      </div>
      {!projects.length && <p>{t("النشاط هيظهر هنا لما يتعمل أول فحص من تبويب المشاريع.", "Activity appears here after the first scan from Projects.")}</p>}
      {project && !snapshot && <p role="status">{t("بنحمّل الفحوصات…", "Loading scans…")}</p>}
      {project && snapshot && <ScanList project={project.id} scans={snapshot.scans.slice(0, 4)} lang={lang} t={t} />}
    </section>}
    {!loading && inScan && <NewScan key={selected || "new"} projects={projects} project={project} choose={choose} navigate={navigate} lang={lang} />}
    {!loading && inHistory && <Panel title={t("سجل الفحوصات", "Scan history")}>
      {projects.length ? <ProjectSelector projects={projects} value={project?.id} onChange={choose} t={t} />
        : <p>{t("سجل الفحوصات هيظهر لما يبقى عندك مشروع.", "Scan history appears after you have a project.")}</p>}
      {project && !snapshot && !error && <p role="status">{t("بنحمّل الفحوصات…", "Loading scans…")}</p>}
      {project && snapshot && <ScanList project={project.id} scans={snapshot.scans} lang={lang} t={t} />}
    </Panel>}
    {inProjects && !project && !loading && <ProjectDirectory organizations={organizations} projects={projects}
      selectedOrg={params.get("org")} navigate={navigate} refresh={refreshDashboard} submit={submit} busy={busy} lang={lang} />}
    {inProjects && project && <nav className="project-section-nav" aria-label={t("أقسام المشروع", "Project sections")}>
      {[
        ["activity", t("النشاط والتقارير", "Activity and reports"), true],
        ["management", t("إدارة المشروع", "Project management"), manage],
        ["access", t("الوصول", "Access"), manage],
        ["references", t("المراجع", "References"), true],
      ].filter(([, , allowed]) => allowed).map(([section, name]) =>
        <DirectoryLink key={section} to={"/projects?project=" + project.id + (section === "activity" ? "" : "&view=" + section)}
          navigate={(to) => { setError(""); navigate(to); }} aria-current={view === section ? "page" : undefined}>{name}</DirectoryLink>
      )}
    </nav>}
    {inProjects && project && needsSnapshot && !snapshot && !error && <p role="status">{t("بنحمّل تفاصيل المشروع…", "Loading project details…")}</p>}
    {recentView && project && snapshot && <div className="project-grid" key={project.id}>
      <Panel title={t("الفحوصات الجارية", "Current scans")}>
        <ScanList project={project.id} scans={snapshot.scans.filter((item) => isActive(item.state)).slice(0, 5)}
          lang={lang} t={t} emptyMessage={t("مفيش فحوصات جارية.", "No scans are running.")} />
      </Panel>
      <Panel title={t("آخر التقارير", "Recent reports")}>
        <RecentReports reports={snapshot.reports || []} project={project.id} lang={lang} />
      </Panel>
    </div>}
    {policyView && project && snapshot?.policy && <Panel title={t("سياسة المدخلات والهدف", "Input policy and target")}>
        <p>{t("عنوان الهدف للربط بس. الفحص بيحلل الملفات اللي رفعتها.", "The target is a reference. Scans analyze the files you upload.")}</p>
        <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          const policy = await action(path + "/policy", json("PUT", {
            allowed_kinds: data.getAll("kinds"), base_url: data.get("url") || null, expected_version: snapshot.version,
            rules: Object.fromEntries(Object.entries(snapshot.policy).filter(([key]) => !["allowed_kinds", "base_url", "model_connection"].includes(key))),
          }));
          if (activePath.current === path) setSnapshot((old) => old?.key === snapshotKey ? { ...old, ...policy } : old);
        })}>
          <label>{t("عنوان الهدف", "Target reference URL")}<input name="url" type="url" dir="ltr" defaultValue={snapshot.policy.base_url || ""} /></label>
          <fieldset><legend>{t("أنواع المدخل المسموحة", "Allowed input types")}</legend>
            {Object.entries(kinds).filter(([id]) => id !== "github").map(([id, titles]) => <label className="project-check" key={id}>
              <input type="checkbox" name="kinds" value={id} defaultChecked={snapshot.policy.allowed_kinds.includes(id)} /> {t(...titles)}
            </label>)}
          </fieldset>
          <button className="btn" disabled={busy}>{t("حفظ السياسة", "Save policy")}</button>
        </form>
    </Panel>}
    {inProjects && project && view === "access" && <section className="card project-panel project-access-panel">
      <ProjectAccess key={project.id} project={project} lang={lang} active />
    </section>}
    {inProjects && project && view === "references" && <Panel title={t("مراجع المشروع", "Project references")}>
        {!memory && !error && <p role="status">{t("بنحمّل المراجع…", "Loading references…")}</p>}
        {memory && !memory.semantic?.length && <p>{t("لسه مفيش مراجع محفوظة.", "There are no saved references yet.")}</p>}
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
    </Panel>}
  </div>;
}

function RecentReports({ reports, project, lang }) {
  const t = translate(lang);
  return <>
    {reports.length ? <ul className="workspace-scan-list">{reports.slice(0, 3).map((report) => <li key={report.id}>
      <a className="workspace-scan-title" href={reportLink(project, report.id)}>
        <FileText size={17} aria-hidden="true" />
        <bdi>{report.input_artifact?.name || report.source?.name || t("فتح التقرير", "Open report")}</bdi>
      </a>
      <time dateTime={report.created_at}>{new Date(report.created_at).toLocaleDateString(lang === "ar" ? "ar-EG" : "en")}</time>
      <span className="workspace-badge" data-state={report.status}>{label(states, report.status || "completed", t)}</span>
    </li>)}</ul> : <p>{t("التقارير هتظهر هنا بعد اكتمال أول فحص.", "Reports appear here after your first completed scan.")}</p>}
    {reports.length > 3 && <a href={reportLink(project)}>{t("كل تقارير المشروع", "All project reports")}</a>}
  </>;
}

export function usePlatformSession() {
  const [failure, setFailure] = useState(null);
  const [retry, setRetry] = useState(0);
  const [user, setUser] = useState(undefined);
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
  return { user, setUser, failure, retry: () => setRetry((current) => current + 1) };
}

export function Platform({ location, navigate, lang, session, preferences }) {
  const t = translate(lang);
  const { user, setUser, failure, retry } = session;
  const signingIn = /^\/signin\/?$/.test(location.pathname);
  const pendingInvite = location.hash?.startsWith("#invite=");
  const [invitationRevision, setInvitationRevision] = useState(0);
  useEffect(() => {
    if (!user || !signingIn) return;
    const next = new URLSearchParams(location.search).get("next") || "";
    const safeReport = /^\/reports(?:\/[a-f0-9]{32})?(?:\?[^#]*)?$/.test(next);
    const destination = pendingInvite ? "/settings" + location.hash : safeReport ? next : "/dashboard";
    navigate(destination, { replace: true });
  }, [user, signingIn, location.hash, location.search, pendingInvite, navigate]);
  if (failure) return <p className="workspace-error" role="alert">{errorText(failure, t)} <button className="btn" onClick={retry}>{t("إعادة المحاولة", "Retry")}</button></p>;
  if (user === undefined) return <p role="status">{t("جاري التحقق من الجلسة…", "Checking your session…")}</p>;
  if (!user) return <AccountAccess lang={lang} onAuthenticated={(account) => {
    setUser(account);
    if (!signingIn && !pendingInvite) navigate("/dashboard", { replace: true });
  }} />;
  if (signingIn) return <p role="status">{t("بنفتح مساحة العمل…", "Opening your workspace…")}</p>;
  const match = /^\/projects\/([a-f0-9]{32})\/scans\/([a-f0-9]{32})\/?$/.exec(location.pathname);
  if (match) return <ScanStatus key={match[2]} projectId={match[1]} scanId={match[2]} lang={lang} />;
  if (/^\/settings\/?$/.test(location.pathname)) return <AccountSettings lang={lang} user={user} preferences={preferences}
    onProfileChange={setUser}
    key={user.id} invitation={pendingInvite ? location.hash.slice("#invite=".length) : ""}
    clearInvite={() => navigate("/settings", { replace: true })}
    onJoined={() => setInvitationRevision((current) => current + 1)}
    onLogout={() => { setUser(null); navigate("/", { replace: true }); }} />;
  return <Dashboard location={location} navigate={navigate} user={user} lang={lang} invitationRevision={invitationRevision} />;
}
