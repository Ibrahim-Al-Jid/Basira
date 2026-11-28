import React, { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, FileText, Folder, Plus, UploadCloud } from "lucide-react";
import { post } from "./data";
import { api, action, errorText, json, translate } from "./platformClient";
import { AccountSettings } from "./AccountSettings";
import { ProjectAccess } from "./ProjectAccess";
import { DirectoryLink, ProjectDirectory } from "./ProjectDirectory";
import { ProjectTabs } from "./ProjectTabs";
import { PersonalDirectory, PersonalProjectManagement } from "./PersonalWorkspace";
import { SignIn } from "./SignIn";
import AgentLanes from "./AgentLanes";
import ReplayPanel from "./ReplayPanel";
import { ProjectSummary } from "./Overview";
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
  website: ["رابط موقع", "Website URL"],
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
  website: ["اجمع أدلة من صفحة HTTPS مصرّح بيها للمشروع.", "Collect evidence from an HTTPS page approved for this project."],
};
const states = {
  queued: ["في الانتظار", "Queued"], running: ["قيد التنفيذ", "Running"],
  completed: ["مكتمل", "Completed"], partial: ["جزئي", "Partial"],
  failed: ["فشل", "Failed"], cancelled: ["أُلغي", "Cancelled"],
  model_skipped: ["الموديل لم يُستخدم", "Model not used"],
};
const eventText = {
  "scan.queued": ["تم تسجيل الطلب للفحص.", "Scan request queued."],
  "scan.completed": ["اكتمل الفحص.", "Scan completed."],
  "scan.partial_ready": ["التقرير التجريبي جاهز.", "The partial report is ready."],
  "scan.cancelled": ["اتلغى الفحص.", "Scan cancelled."],
  "scan.cancelled_requester_changed": ["اتلغى الفحص لأن صلاحية مقدم الطلب اتغيّرت.", "Scan cancelled because the requester's access changed."],
  "scan.cancelled_project_deleted": ["اتلغى الفحص بعد حذف المشروع.", "Scan cancelled after the project was deleted."],
  "scan.failed_input_expired": ["انتهت مدة الاحتفاظ بالمدخل قبل اكتمال الفحص.", "The input expired before the scan finished."],
  "scan.failed_provenance": ["تعذّر التحقق من مصدر الفحص أو النطاق المسجّل.", "The scan source or recorded scope could not be verified."],
  "scan.failed_retry_limit": ["وصلت المهمة للحد الأقصى لمحاولات التشغيل.", "The scan reached its retry limit."],
  "scan.agent_failed": ["تعذّر تشغيل وضع الوكلاء، فمتّحسبش النتيجة كفحص وكلاء.", "Agent mode could not run, so this result is not counted as an agent scan."],
  "scan.agent_fallback": ["مسار الوكلاء ما اكتملش، وكمّلنا بالقواعد.", "The agent path did not finish, so the scan continued with rules."],
  "scan.failed": ["تعذّر تنفيذ الفحص.", "The scan could not be completed."],
};
const attemptText = {
  "scan.attempt_started": (n) => [`بدأت محاولة التنفيذ رقم ${n}.`, `Execution attempt ${n} started.`],
  "scan.attempt_resumed": (n) => [`استؤنفت محاولة التنفيذ رقم ${n} من نتيجة التحليل المحفوظة.`, `Execution attempt ${n} resumed from the saved analysis.`],
};
// Events carry a stable key from the backend. The stored Arabic detail is only the fallback for unknown keys.
function eventDetail(event, t) {
  const attempt = event.params?.attempt;
  const pair = attemptText[event.key]?.(attempt ?? "") ?? eventText[event.key];
  return pair ? t(pair[0], pair[1]) : t(event.detail, event.detail);
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
  return <section className="card project-panel">{title && <h2>{title}</h2>}{children}</section>;
}

function ScanStatus({ projectId, scanId, lang }) {
  const t = translate(lang);
  const [scan, setScan] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [canScan, setCanScan] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [staying, setStaying] = useState(false);
  const [countdown, setCountdown] = useState(null);
  const watchedRun = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    let cursor = 0;
    try { watchedRun.current = sessionStorage.getItem("basira:fresh:" + scanId) === "1"; } catch { watchedRun.current = false; }
    setStaying(false);
    setCountdown(null);
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
        if (isActive(view.state)) watchedRun.current = true;
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
  const openAutomatically = Boolean(scan?.report_available) && watchedRun.current && !staying;
  useEffect(() => {
    if (!openAutomatically) { setCountdown(null); return undefined; }
    let left = 4;
    setCountdown(left);
    const timer = setInterval(() => {
      left -= 1;
      if (left <= 0) {
        clearInterval(timer);
        try { sessionStorage.removeItem("basira:fresh:" + scanId); } catch { /* ignore */ }
        window.location.assign(reportLink(projectId, scanId));
      } else setCountdown(left);
    }, 1000);
    return () => clearInterval(timer);
  }, [openAutomatically, projectId, scanId]);
  async function cancel() {
    setCancelling(true);
    try {
      await action(projectApi(projectId) + "/scans/" + scanId + "/cancel", { method: "POST" });
      setReload((count) => count + 1);
    } catch (err) { setError(err); }
    finally { setCancelling(false); }
  }
  return (
    <div className="project-workspace scan-status-page">
      <header className="project-header">
        <div>
          <a className="workspace-back" href={"/projects?project=" + projectId + "&view=scans"}>{t("فحوصات المشروع", "Project scans")}</a>
          <h1>{t("متابعة الفحص", "Scan progress")}</h1>
        </div>
        {scan?.report_available && <a className="btn primary" href={reportLink(projectId, scan.id)}>
          <FileText size={17} aria-hidden="true" />{t("فتح التقرير", "Open report")}</a>}
        {scan && canScan && isActive(scan.state) &&
          <button className="btn danger-action" onClick={cancel} disabled={cancelling}>{t("إلغاء الفحص", "Cancel scan")}</button>}
      </header>
      {error && <p className="workspace-error" role="alert">{errorText(error, t)} <button className="btn" onClick={() => setReload((n) => n + 1)}>{t("إعادة المحاولة", "Retry")}</button></p>}
      {!scan && !error && <p role="status">{t("جاري تحميل حالة الفحص…", "Loading scan status…")}</p>}
      {scan && <section className="card project-panel">
        <div className="directory-heading scan-status-summary">
          <h2><FileText size={20} aria-hidden="true" /><bdi>{scan.artifact.name}</bdi></h2>
          <p role="status" className="workspace-scan-status"><span className="workspace-badge" data-state={scan.state}>{label(states, scan.state, t)}</span></p>
        </div>
        {scan.artifact.profile && <p className="workspace-hint">
          {label(kinds, scan.artifact.profile.mode === "zip" ? "repository" : scan.artifact.profile.mode, t)}
        </p>}
        {countdown !== null && <p className="workspace-auto-open" role="status">
          {t(`الفحص خلص. هفتح التقرير بعد ${number(countdown, lang)} ثواني.`, `Scan finished. Opening the report in ${number(countdown, lang)} s.`)}{" "}
          <button type="button" className="btn" onClick={() => { setStaying(true); try { sessionStorage.removeItem("basira:fresh:" + scanId); } catch { /* ignore */ } }}>{t("خليني هنا", "Stay here")}</button>
        </p>}
        <AgentLanes events={events} active={isActive(scan.state)} t={t} lang={lang} />
        <ReplayPanel scan={scan} events={events} t={t} lang={lang} reportHref={scan.report_available ? reportLink(projectId, scan.id) : ""} />
        {!!events.length && <section className="workspace-management">
          <h3>{t("سجل الفحص", "Scan activity")}</h3>
          <ol className="workspace-timeline" aria-label={t("سجل الفحص", "Scan events")}>{events.filter((item) => !["agent_done", "agent_start", "stage_start"].includes(item.kind)).map((item) => <li key={item.sequence}>
          <b>{label(states, item.kind, t)}</b>
          <p dir="auto">{eventDetail(item, t)}</p>
          <time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString(lang === "ar" ? "ar-EG" : "en")}</time>
          </li>)}</ol>
        </section>}
      </section>}
    </div>
  );
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

function NewScan({ projects, project, navigate, lang, personal }) {
  const t = translate(lang);
  const [step, setStep] = useState(1);
  const [kind, setKind] = useState("");
  const [source, setSource] = useState(null);
  const [githubSource, setGithubSource] = useState(null);
  const [commit, setCommit] = useState("");
  const [repository, setRepository] = useState("");
  const [targetReference, setTargetReference] = useState("");
  const [enrich, setEnrich] = useState(false);
  const [mode, setMode] = useState("hybrid");
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
  const agentKind = kind === "github" || kind === "repository" || kind === "config";
  const modeBlockers = [
    !profileValue?.agent_path_enabled && t("السيرفر مش مشغّل مسار الوكلاء (BASIRA_AGENT_LOOP=1). شغّل ops/start-local من جديد.",
      "The server has the agent path off (BASIRA_AGENT_LOOP=1 is not set). Restart with ops/start-local."),
    !model && t("مفيش اتصال موديل: سجّل المفتاح في الحساب > اتصال الموديل.", "No model connection: save a key under Account > Model connection."),
    !agentKind && t("الوكلاء بيقرأوا المستودعات وملفات الإعدادات بس.", "Agents read repositories and config files only."),
  ].filter(Boolean);
  const agentsOk = !modeBlockers.length;
  const effectiveMode = agentsOk ? mode : "rules";
  const modelWanted = (enrich || effectiveMode !== "rules") && !!model;
  const limit = profileValue?.max_bytes;
  const allowedKinds = profileValue?.allowed_kinds ?? [];
  const sourceKinds = personal && allowedKinds.includes("repository") ? ["repository", "github", "website"]
    : allowedKinds.includes("repository") ? [...allowedKinds, "github"] : allowedKinds;
  const useGithub = kind === "github";
  const useWebsite = personal && kind === "website";
  const githubPath = useGithub && access && allowedKinds.includes("repository")
    ? personal ? api + "/github/repositories" : projectApi(project.id) + "/github-source" : null;
  const githubView = githubSource?.path === githubPath ? githubSource : null;
  const repoKey = (row) => `${row.installation_id}/${row.repository_id}`;
  const githubConnection = personal ? githubView?.value?.repositories.find((row) => repoKey(row) === repository)
    : githubView?.value?.available ? githubView.value.connection : null;
  const validCommit = personal ? /^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,199}$/.test(commit.trim()) : /^[a-f0-9]{40}$/i.test(commit.trim());
  const validWebsite = /^https:\/\/[A-Za-z0-9.-]+(?::443)?(?:\/[A-Za-z0-9._~/-]*)?$/.test(targetReference.trim());
  const websiteEvidence = ["har", "openapi", "zap"].includes(kind);
  const requiresAddress = kind === "zap" && !profileValue?.asset_linked;
  const labels = [t("الملف", "Source"), t("المراجعة", "Review")];

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => { if (step > 1) heading.current?.focus(); }, [step]);
  // The project comes from the page the scan was started on. Its default input type is chosen once the scope loads.
  useEffect(() => {
    if (!access || !allowedKinds.length || sourceKinds.includes(kind)) return;
    setKind(allowedKinds.includes("repository") ? "repository" : allowedKinds[0]);
    setSource(null);
  });
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
    const ready = useGithub ? githubConnection && validCommit : useWebsite ? validWebsite : source && allowedKinds.includes(kind);
    if (request.current || !access || !ready || !acknowledged) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true);
    setError("");
    try {
      const scope = {
        scope_version: profileValue.scope_version, acknowledge_scope: true,
        analysis_mode: effectiveMode,
        ...(modelWanted ? { model_connection: model.id } : {}),
      };
      const base = projectApi(project.id);
      let endpoint = base + "/scans";
      let options;
      if (personal && !useGithub && !useWebsite) {
        endpoint = base + "/intake/zip";
        options = { method: "POST", body: source, headers: {
          "Content-Type": "application/zip", "X-Artifact-Name": encodeURIComponent(source.name),
          "X-Scope-Version": String(scope.scope_version), "X-Acknowledge-Scope": "true",
          "X-Analysis-Mode": scope.analysis_mode,
          ...(scope.model_connection ? { "X-Model-Connection": scope.model_connection } : {}),
        } };
      } else if (personal) {
        endpoint = base + "/intake";
        const input = useGithub ? {
          source: "github", installation_id: githubConnection.installation_id,
          repository_id: githubConnection.repository_id, ref: commit.trim(),
        } : { source: "website", url: targetReference.trim() };
        options = post({ ...scope, ...input });
      } else {
        if (useGithub) endpoint = githubPath + "/scans";
        const input = useGithub ? { commit: commit.trim().toLowerCase() } : {
          kind, name: source.name, content: await encoded(source),
          ...(websiteEvidence && targetReference.trim() ? { target_reference: targetReference.trim() } : {}),
        };
        options = post({ ...scope, ...input });
      }
      if (controller.signal.aborted) return;
      options.headers["Idempotency-Key"] = idempotency.current;
      const saved = await action(endpoint, { ...options, signal: controller.signal });
      if (!controller.signal.aborted) {
        try { sessionStorage.setItem("basira:fresh:" + saved.id, "1"); } catch { /* storage may be blocked */ }
        navigate(scanLink(project.id, saved.id));
      }
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

  if (!project) return <Panel title={t("اختار المشروع اللي هتفحصه", "Choose the project to scan")}>
    {candidates.length ? <ul className="project-choice">{candidates.map((item) => <li key={item.id}>
      <DirectoryLink to={newScanLink(item.id)} navigate={navigate}><Folder size={18} aria-hidden="true" /><bdi>{item.name}</bdi></DirectoryLink>
    </li>)}</ul> : <p>{personal ? t("أنشئ مشروع قبل ما تبدأ أول فحص.", "Create a project before starting your first scan.")
      : t("محتاج مشروع عندك فيه صلاحية تشغيل الفحص.", "Create a project or ask for permission to run scans in an existing project.")}</p>}
    <DirectoryLink className="btn" to="/projects" navigate={navigate}>{t("فتح المشاريع", "Open projects")}</DirectoryLink>
  </Panel>;
  if (!access) return <Panel title={t("مفيش صلاحية فحص", "Scanning is not available")}>
    <p>{t("مفيش عندك صلاحية تشغيل فحوصات في المشروع ده.", "You do not have permission to run scans in this project.")}</p>
    <DirectoryLink className="btn" to={"/projects?project=" + project.id} navigate={navigate}>{t("رجوع للمشروع", "Back to the project")}</DirectoryLink>
  </Panel>;

  return <section className="card project-panel workspace-wizard" data-step={step} aria-labelledby={title}>
    <ol className="workspace-steps" aria-label={t("خطوات الفحص", "Scan steps")}>{labels.map((text, index) =>
      <li key={index} aria-current={step === index + 1 ? "step" : undefined}><span>{number(index + 1, lang)}</span>{text}</li>)}</ol>
    <h2 id={title} ref={heading} tabIndex={-1}>{labels[step - 1]}</h2>
    {error && <p className="workspace-error" role="alert">{error}</p>}
    {staleProfile && <button className="btn" onClick={() => {
      setStaleProfile(false);
      setProfile(null);
      setAcknowledged(false);
      setError("");
      setStep(1);
      setRetryProfile((value) => value + 1);
      idempotency.current = crypto.randomUUID();
    }}>{t("راجع نطاق الفحص من جديد", "Review the updated scope")}</button>}
    {profileError && <p className="workspace-error" role="alert">{errorText(profileError, t)} <button type="button" className="btn" onClick={() => {
      setProfileFailure(null);
      setRetryProfile((value) => value + 1);
    }}>{t("إعادة المحاولة", "Retry")}</button></p>}
    {step === 1 && <form className="project-form" onSubmit={(event) => {
      event.preventDefault();
      if (useGithub) {
        if (githubConnection && validCommit) setStep(2);
        return;
      }
      if (useWebsite) {
        if (validWebsite) setStep(2);
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
                setRepository("");
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
        {personal && <DirectoryLink className="workspace-back" to="/settings?tab=github" navigate={navigate}>
          {t("إدارة اتصال GitHub", "Manage GitHub connection")}
        </DirectoryLink>}
        {personal && githubView?.value?.repositories.length === 0 &&
          <p role="status">{t("اختار مستودعات مسموح بيها في تثبيت GitHub App.", "Select repositories in the GitHub App installation.")}</p>}
        {personal && !!githubView?.value?.repositories.length && <label>{t("المستودع", "Repository")}
          <select value={repository} required onChange={(event) => updateEvidence(() => {
            const row = githubView.value.repositories.find((item) => repoKey(item) === event.target.value);
            setRepository(event.target.value);
            setCommit(row?.default_branch || "");
          })}>
            <option value="">{t("اختار مستودع", "Select a repository")}</option>
            {githubView.value.repositories.map((row) => <option key={repoKey(row)} value={repoKey(row)}>{row.repository}</option>)}
          </select>
        </label>}
        {!personal && githubView?.value && !githubConnection && <p role="status">{t(
          "محتاج اتصال GitHub مُفعّل ومُصرّح للمشروع. صاحب المؤسسة أو المدير يقدر يراجعه من الحساب. تقدر تكمل برفع ZIP.",
          "This project needs an authorized GitHub connection. An organization owner or admin can manage it in Account. You can continue with a ZIP upload."
        )}</p>}
        {githubConnection && <>
          <label>{personal ? t("اسم الفرع أو معرّف الـ commit الكامل", "Branch name or full commit SHA")
            : t("معرّف الـ commit الكامل", "Full commit SHA")}
            <input name="commit" dir="ltr" autoComplete="off" spellCheck={false} required maxLength={personal ? 200 : 40}
              value={commit} onChange={(event) => updateEvidence(() => setCommit(event.target.value))} />
          </label>
          {personal && <p className="project-hint">{t(
            "بصيرة بتقرا ملفات الكود والإعدادات (py، js، ts، json، yaml، toml، xml، Dockerfile وأشباهها) لحد ١٠٠٠ ملف و٥٠ ميجا بعد الفك (الأرشيف نفسه لحد ١٠ ميجا). ملفات Markdown والصور مش بتتفحص، ومستودع من غيرها هيترفض.",
            "Basira reads code and config files (py, js, ts, json, yaml, toml, xml, Dockerfile and similar), up to 1000 files and 50 MB unpacked (10 MB for the archive itself). Markdown and images are not scanned, and a repository with none of the supported files is rejected.")}</p>}
        </>}
      </> : useWebsite ? <label>{t("رابط الصفحة المعتمدة", "Approved page URL")}
        <input type="url" dir="ltr" value={targetReference} maxLength={250} required placeholder="https://example.com/"
          onChange={(event) => updateEvidence(() => setTargetReference(event.target.value))} />
        <small className="workspace-hint">{t("طلب قراءة لكل صفحة عامة معتمدة مسبقًا، بحد أقصى ٣ صفحات من نفس الموقع.",
          "One read request per preapproved public page, up to three pages on the same site.")}</small>
      </label> : <>
      <label className="workspace-upload"
        onDragOver={personal ? (event) => event.preventDefault() : undefined}
        onDrop={personal ? (event) => {
          event.preventDefault();
          const dropped = event.dataTransfer.files[0] || null;
          if (dropped && (!extensions[kind].split(",").some((extension) => dropped.name.toLowerCase().endsWith(extension)) || dropped.size > limit)) {
            setError(t("الملف لازم يطابق نوع المدخل وحجمه ضمن الحد.", "The file must match the selected input type and be within the size limit."));
            return;
          }
          setError("");
          updateEvidence(() => setSource(dropped));
          if (dropped) setStep(2);
        } : undefined}><UploadCloud size={25} aria-hidden="true"/>
        <span>{t("اختيار ملف", "Choose file")}</span>
        <input key={kind} name="file" type="file" accept={extensions[kind]} required={!source}
          onInvalid={(event) => event.target.setCustomValidity(t("اختار ملف الأول.", "Choose a file first."))}
          onChange={(event) => {
            event.target.setCustomValidity("");
            const chosen = event.target.files[0] || null;
            if (chosen && !extensions[kind].split(",").some((extension) => chosen.name.toLowerCase().endsWith(extension))) {
              event.target.value = "";
              updateEvidence(() => setSource(null));
              setError(t("امتداد الملف لازم يطابق نوع المدخل: " + extensions[kind], "The file extension must match the selected input: " + extensions[kind]));
              return;
            }
            if (chosen && chosen.size > limit) {
              event.target.value = "";
              updateEvidence(() => setSource(null));
              setError(t("الملف أكبر من الحد المسموح.", "The file is over the upload limit."));
              return;
            }
            setError("");
            updateEvidence(() => setSource(chosen));
            if (personal && chosen) setStep(2);
          }} />
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
        <DirectoryLink className="btn" to={"/projects?project=" + project.id} navigate={navigate}>{t("إلغاء", "Cancel")}</DirectoryLink>
        <button className="btn primary" disabled={(useGithub && (!githubConnection || !validCommit)) || (useWebsite && !validWebsite)}>{t("مراجعة الفحص", "Review scan")}</button>
      </div>
    </form>}
    {step === 2 && <form className="project-form" onSubmit={launch} aria-busy={busy}>
      <dl className="workspace-summary">
        <div><dt>{t("المشروع", "Project")}</dt><dd><bdi>{project?.name}</bdi></dd></div>
        <div><dt>{useGithub ? t("المستودع", "Repository") : useWebsite ? t("الصفحة", "Page") : t("الملف", "File")}</dt>
          <dd><bdi>{useGithub ? githubConnection?.repository : useWebsite ? targetReference : source?.name}</bdi></dd></div>
        {useGithub && <div><dt>{t("الفرع أو الـ commit", "Branch or commit")}</dt><dd><bdi>{commit}</bdi></dd></div>}
        <div><dt>{t("نوع المدخل", "Input type")}</dt><dd>{label(kinds, kind, t)}</dd></div>
        <div><dt>{t("نطاق الفحص", "Scan scope")}</dt><dd>{useGithub ? t("لقطة واحدة للنسخة المحددة", "One snapshot at the selected commit")
          : useWebsite ? t("جمع أدلة سلبي من الصفحات المعتمدة", "Passive evidence collection from approved pages")
            : t("الملف المرفوع فقط", "Uploaded file only")}</dd></div>
        {websiteEvidence && targetReference.trim() && <div><dt>{t("مرجع الموقع", "Website reference")}</dt><dd><bdi>{targetReference.trim()}</bdi></dd></div>}
      </dl>
      {model && <label className="project-check">
        <input type="checkbox" checked={enrich} disabled={busy} onChange={(event) => {
          setEnrich(event.target.checked);
          setError("");
          idempotency.current = crypto.randomUUID();
        }} />
        {t("استخدم الموديل لترتيب النتائج", "Use a model to prioritize findings")} <bdi>{model.model}</bdi>
      </label>}
      <fieldset className="project-form scan-mode" disabled={busy}>
        <legend>{t("وضع الفحص", "Scan mode")}</legend>
        {[["rules", t("قواعد فقط", "Rules only"), t("فحص ثابت بالقواعد، سريع ومن غير موديل.", "Fixed rule checks. Fast, no model.")],
          ["agents", t("وكيل ذكاء اصطناعي فقط", "AI agent only"), t("وكلاء الموديل بيقروا الكود ويدوّروا بنفسهم، من غير القواعد.", "Model agents read the code and hunt on their own, without the rules.")],
          ["hybrid", t("هجين (قواعد + ذكاء اصطناعي)", "Hybrid (rules + AI)"), t("القواعد أولًا وبعدها الوكلاء يكمّلوا ويرتّبوا النتائج.", "Rules first, then agents add findings and prioritize.")],
        ].map(([id, name, hint]) => <label key={id} className="project-check">
          <input type="radio" name="analysis_mode" value={id} checked={effectiveMode === id}
            disabled={id !== "rules" && !agentsOk} onChange={() => { setMode(id); idempotency.current = crypto.randomUUID(); }} />
          <span><b>{name}</b> <small>{hint}</small></span>
        </label>)}
        {!agentsOk && <p className="project-hint" role="status" data-testid="mode-unavailable">
          {t("وضع الوكلاء مش متاح هنا، والفحص هيشتغل بالقواعد فقط. السبب:", "AI modes are not available here, so this scan will run rules only. Why:")}
          <ul>{modeBlockers.map((reason) => <li key={reason}>{reason}</li>)}</ul></p>}
      </fieldset>
      {personal && !model && <DirectoryLink className="workspace-back" to="/settings?tab=model" navigate={navigate}>
        {t("إعداد اتصال الموديل", "Set up model connection")}
      </DirectoryLink>}
      <label className="project-check workspace-ack">
        <input name="acknowledge_scope" type="checkbox" checked={acknowledged} disabled={busy} required
          onChange={(event) => setAcknowledged(event.target.checked)} />
        {useGithub ? t("عندي صلاحية لمراجعة لقطة المستودع دي", "I have permission to review this repository snapshot")
          : useWebsite ? t("عندي تفويض لجمع أدلة من الصفحة دي", "I am authorized to collect evidence from this page")
            : t("عندي صلاحية لمراجعة الملف ده", "I have permission to review this file")}
      </label>
      <div className="workspace-actions">
        <button className="btn" type="button" disabled={busy} onClick={() => setStep(1)}>{t("رجوع", "Back")}</button>
        <button className="btn primary" disabled={busy || !profileValue || !acknowledged || staleProfile}>{busy ? t("جاري إرسال الفحص…", "Submitting scan…") : t("إرسال الفحص", "Submit scan")}</button>
      </div>
    </form>}
  </section>;
}

function Dashboard({ location, navigate, user, lang, invitationRevision, personal, onProjectsChanged }) {
  const t = translate(lang);
  const route = location.pathname.replace(/\/$/, "") || "/";
  const inProjects = route === "/projects";
  const inScan = route === "/new-scan";
  const [organizations, setOrganizations] = useState([]);
  const [projects, setProjects] = useState([]);
  const [error, setError] = useState("");
  const [snapshotState, setSnapshot] = useState(null);
  const [memoryState, setMemory] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const params = new URLSearchParams(location.search);
  const selected = params.get("project") || "";
  const project = projects.find((item) => item.id === selected);
  const path = project ? projectApi(project.id) : null;
  const activePath = useRef(path);
  const memory = memoryState?.path === path ? memoryState.value : null;
  const manage = project && ["owner", "admin"].includes(project.role);
  const requestedView = params.get("view");
  const view = ["references", "scans"].includes(requestedView) || (manage && (requestedView === "management" || (!personal && requestedView === "access")))
    ? requestedView : "activity";
  const policyView = inProjects && view === "management";
  const recentView = inProjects && view === "activity";
  const scansView = inProjects && (view === "scans" || view === "activity");
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
      personal ? null : action(api + "/organizations", { signal }), action(api + "/projects", { signal }),
    ]);
    if (!signal?.aborted) {
      if (orgs) setOrganizations(orgs.organizations);
      setProjects(work.projects);
    }
  }
  async function refreshPersonalProjects() {
    onProjectsChanged();
    await refreshDashboard();
  }
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setLoadFailed(false);
    setError("");
    refreshDashboard(controller.signal).catch((err) => {
      if (!controller.signal.aborted) { setLoadFailed(true); setError(errorText(err, t)); }
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [retry, invitationRevision, personal]);
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
  const creatingProject = personal && inProjects && !project && params.has("new");
  const title = {
    "/dashboard": t("نظرة عامة", "Overview"), "/projects": creatingProject ? t("مشروع جديد", "New Project") : t("المشاريع", "Projects"),
    "/new-scan": t("فحص جديد", "New scan"),
  }[route];
  const displayName = (user.display_name || "").trim();
  const showName = displayName && !displayName.includes("@");
  const canScan = project && project.role !== "viewer";
  const showNewScan = inProjects && canScan && view === "activity";
  const projectPage = inProjects && project;
  const lostProject = (inProjects || inScan) && selected && !project && !loading && !loadFailed;
  const policyEditor = policyView && project && snapshot?.policy && <Panel title={t("سياسة المدخلات والهدف", "Input policy and target")}>
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
            {Object.entries(kinds).filter(([id]) => personal ? id === "repository" : id !== "github").map(([id, titles]) => <label className="project-check" key={id}>
              <input type="checkbox" name="kinds" value={id} required={personal} defaultChecked={snapshot.policy.allowed_kinds.includes(id)} /> {t(...titles)}
            </label>)}
          </fieldset>
          <button className="btn" disabled={busy}>{t("حفظ السياسة", "Save policy")}</button>
        </form>
    </Panel>;
  const Back = lang === "ar" ? ChevronRight : ChevronLeft;
  return <div className="project-workspace" data-workspace-page={route.slice(1)}>
    <header className="project-header">
      <div>{((inProjects && project) || creatingProject || (inScan && project)) && <DirectoryLink className="workspace-back"
          to={inScan ? "/projects?project=" + project.id : personal ? "/projects" : "/projects?org=" + project.org_id} navigate={navigate}>
          <Back size={15} aria-hidden="true" />{inScan ? <bdi>{project.name}</bdi> : t("المشاريع", "Projects")}</DirectoryLink>}
        <h1>{inProjects && project ? <bdi>{project.name}</bdi> : title}</h1></div>
      <div className="header-actions">
        {!loading && !loadFailed && personal && inProjects && !project && !creatingProject && <DirectoryLink className="btn icon-plus"
          to="/projects?new=1" navigate={navigate} aria-label={t("مشروع جديد", "New project")} title={t("مشروع جديد", "New project")}>
          <Plus size={18} aria-hidden="true" /></DirectoryLink>}
        {!loading && showNewScan && <DirectoryLink className="btn primary" to={newScanLink(project.id)} navigate={navigate}>
          <Plus size={17} aria-hidden="true" />{t("فحص جديد", "New scan")}
        </DirectoryLink>}
      </div>
    </header>
    {error && <p className="workspace-error" role="alert">{error} <button className="btn" onClick={() => setRetry((value) => value + 1)}>{t("إعادة المحاولة", "Retry")}</button></p>}
    {loading && <p role="status">{t("بنحمّل المشاريع…", "Loading projects…")}</p>}
    {lostProject && <Panel title={t("المشروع مش متاح", "Project not found")}>
      <p>{t("المشروع المطلوب مش موجود أو مفيش عندك صلاحية عليه.", "This project does not exist or you cannot open it.")}</p>
      <DirectoryLink className="btn" to="/projects" navigate={navigate}>{t("كل المشاريع", "All projects")}</DirectoryLink>
    </Panel>}
    {!loading && !loadFailed && inScan && !lostProject && <NewScan key={selected || "new"} projects={projects} project={project} navigate={navigate} lang={lang} personal={personal} />}
    {inProjects && !project && !selected && !loading && !loadFailed && (personal ?
      <PersonalDirectory projects={projects} creating={params.has("new")} navigate={navigate}
        refresh={refreshPersonalProjects} submit={submit} busy={busy} lang={lang} />
      : <ProjectDirectory organizations={organizations} projects={projects}
        selectedOrg={params.get("org")} navigate={navigate} refresh={refreshDashboard} submit={submit} busy={busy} lang={lang} />)}
    {projectPage && <ProjectTabs project={project} active={view} manage={manage} personal={personal} t={t} navigate={navigate}
      onNavigate={() => setError("")} />}
    {inProjects && project && needsSnapshot && !snapshot && !error && <p role="status">{t("بنحمّل تفاصيل المشروع…", "Loading project details…")}</p>}
    {projectPage && view === "scans" && snapshot && <Panel title={null}>
      <ScanList project={project.id} scans={snapshot.scans} lang={lang} t={t} />
    </Panel>}
    {recentView && project && snapshot && <div className="project-overview" key={project.id}>
      <ProjectSummary path={path} projectId={project.id} t={t} lang={lang} reportLink={reportLink} />
      <div className="project-grid">
        <Panel title={t("الفحوصات الجارية", "Current scans")}>
          <ScanList project={project.id} scans={snapshot.scans.filter((item) => isActive(item.state)).slice(0, 5)}
            lang={lang} t={t} emptyMessage={t("مفيش فحوصات جارية.", "No scans are running.")} />
        </Panel>
        <Panel title={t("آخر التقارير", "Recent reports")}>
          <RecentReports reports={snapshot.reports || []} project={project.id} lang={lang} />
        </Panel>
      </div>
    </div>}
    {personal && policyView && project
      ? <PersonalProjectManagement key={project.id} project={project}
        refresh={refreshPersonalProjects} submit={submit} busy={busy} lang={lang} navigate={navigate}>
        {policyEditor}
      </PersonalProjectManagement>
      : policyEditor}
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

export function Platform({ location, navigate, lang, session, preferences, personal, onProjectsChanged }) {
  const t = translate(lang);
  const { user, setUser, failure, retry } = session;
  const signingIn = /^\/signin\/?$/.test(location.pathname);
  const startInRegister = signingIn && new URLSearchParams(location.search).get("mode") === "register";
  const pendingInvite = !personal && location.hash?.startsWith("#invite=");
  const [invitationRevision, setInvitationRevision] = useState(0);
  useEffect(() => {
    if (!user || !signingIn) return;
    const next = new URLSearchParams(location.search).get("next") || "";
    const safeReport = /^\/reports(?:\/[a-f0-9]{32})?(?:\?[^#]*)?$/.test(next);
    const destination = pendingInvite ? "/settings" + location.hash : safeReport ? next : "/projects";
    navigate(destination, { replace: true });
  }, [user, signingIn, location.hash, location.search, pendingInvite, personal, navigate]);
  if (failure) return <p className="workspace-error" role="alert">{errorText(failure, t)} <button className="btn" onClick={retry}>{t("إعادة المحاولة", "Retry")}</button></p>;
  if (user === undefined) return <p role="status">{t("جاري التحقق من الجلسة…", "Checking your session…")}</p>;
  if (!user) return <SignIn key={String(startInRegister)} lang={lang} personal={personal} startInRegister={startInRegister}
    navigate={navigate} preferences={preferences}
    onAuthenticated={(account) => {
    setUser(account);
    if (!signingIn && !pendingInvite) navigate("/projects", { replace: true });
  }} />;
  if (signingIn) return <p role="status">{t("بنفتح مساحة العمل…", "Opening your workspace…")}</p>;
  const match = /^\/projects\/([a-f0-9]{32})\/scans\/([a-f0-9]{32})\/?$/.exec(location.pathname);
  if (match) return <ScanStatus key={match[2]} projectId={match[1]} scanId={match[2]} lang={lang} />;
  if (/^\/settings\/?$/.test(location.pathname)) return <AccountSettings lang={lang} user={user} personal={personal} location={location} navigate={navigate}
    onProfileChange={setUser}
    key={user.id} invitation={pendingInvite ? location.hash.slice("#invite=".length) : ""}
    clearInvite={() => navigate("/settings?tab=organization", { replace: true })}
    onJoined={() => setInvitationRevision((current) => current + 1)}
    onLogout={() => { setUser(null); navigate("/", { replace: true }); }} />;
  return <Dashboard location={location} navigate={navigate} user={user} lang={lang} invitationRevision={invitationRevision}
    personal={personal} onProjectsChanged={onProjectsChanged} />;
}
