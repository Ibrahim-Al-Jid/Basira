import React, { useEffect, useId, useRef, useState } from "react";
import { ArrowUpRight, CheckCircle2, ChevronLeft, ChevronRight, FileCheck2, Folder, FolderPlus, GitBranch, Grid2X2, History, LogOut, Menu, Pencil, Plus, RefreshCw, RotateCcw, ScanLine, Search, Settings, Trash2, Workflow } from "lucide-react";
import { post } from "./data";
import { action, api, errorText, json, translate } from "./platformClient";
import { DirectoryLink } from "./ProjectDirectory";
import { WorkspaceBrand } from "./SiteHeader";
import "./personal-workspace.css";

// Only link to GitHub over https, whatever the API returns.
function safeGithubUrl(value) {
  try { const url = new URL(value); return url.protocol === "https:" && url.hostname === "github.com" ? url.href : ""; }
  catch { return ""; }
}

export function PersonalSidebar({ location, navigate, follow, lang, revision, onLogout }) {
  const t = translate(lang);
  const [projects, setProjects] = useState([]);
  const [failure, setFailure] = useState(null);
  const [retry, setRetry] = useState(0);
  const [open, setOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const linksId = useId();
  const menu = useRef(null);
  const params = new URLSearchParams(location.search);
  const projectId = params.get("project") || /^\/projects\/([a-f0-9]{32})\/scans\//.exec(location.pathname)?.[1];
  const projectDirectory = location.pathname.replace(/\/$/, "") === "/projects" && !projectId;

  useEffect(() => {
    const controller = new AbortController();
    setFailure(null);
    action(api + "/projects", { signal: controller.signal }).then(
      ({ projects }) => { if (!controller.signal.aborted) setProjects(projects); },
      (error) => { if (!controller.signal.aborted) setFailure(error); },
    );
    return () => controller.abort();
  }, [revision, retry]);
  useEffect(() => setOpen(false), [location.pathname, location.search]);

  async function logout() {
    setLeaving(true);
    setFailure(null);
    try {
      await action(api + "/auth/logout", { method: "POST" });
      onLogout();
    } catch (error) {
      setFailure(error);
      setLeaving(false);
    }
  }

  const projectQuery = projectId ? "?project=" + encodeURIComponent(projectId) : "";
  return <nav className="personal-sidebar" data-project-directory={projectDirectory || undefined}
    aria-label={t("مساحة العمل", "Workspace navigation")} onKeyDown={(event) => {
    if (event.key === "Escape" && open) {
      setOpen(false);
      menu.current?.focus();
    }
  }}>
    <WorkspaceBrand href="/" follow={follow} lang={lang} />
    <button ref={menu} className="btn personal-menu" type="button" aria-expanded={open} aria-controls={linksId}
      onClick={() => setOpen((value) => !value)}><Menu size={18} aria-hidden="true" />{t("القائمة", "Menu")}</button>
    <div id={linksId} className={"personal-links" + (open ? " is-open" : "")}>
      <DirectoryLink to={"/dashboard" + projectQuery} navigate={navigate} aria-current={location.pathname === "/dashboard" ? "page" : undefined}>
        <Grid2X2 size={18} aria-hidden="true" />{t("نظرة عامة", "Overview")}
      </DirectoryLink>
      <DirectoryLink to={"/new-scan" + projectQuery} navigate={navigate} aria-current={location.pathname === "/new-scan" ? "page" : undefined}>
        <ScanLine size={18} aria-hidden="true" />{t("فحص جديد", "New scan")}
      </DirectoryLink>
      <DirectoryLink to={"/dashboard" + projectQuery + "#agents"} navigate={navigate}
        aria-current={location.pathname === "/dashboard" && location.hash === "#agents" ? "location" : undefined}>
        <Workflow size={18} aria-hidden="true" />{t("فريق المراجعة", "Review agents")}
      </DirectoryLink>
      <DirectoryLink to={"/reports" + projectQuery} navigate={navigate}
        aria-current={location.pathname.startsWith("/reports") ? "page" : undefined}>
        <FileCheck2 size={18} aria-hidden="true" />{t("التقارير", "Reports")}
      </DirectoryLink>
      <DirectoryLink to={"/scans" + projectQuery} navigate={navigate} aria-current={location.pathname === "/scans" ? "page" : undefined}>
        <History size={18} aria-hidden="true" />{t("سجل الفحوصات", "Scan history")}
      </DirectoryLink>
      <DirectoryLink to="/projects" navigate={navigate} aria-current={projectDirectory && !params.has("new") ? "page" : undefined}>
        <Folder size={18} aria-hidden="true" />{t("المشاريع", "Projects")}
      </DirectoryLink>
      {!projectDirectory && projects.length > 0 && <div className="personal-nav-group">
        <p className="personal-nav-label">{t("مشاريعي", "My projects")}</p>
        <ul aria-label={t("مشاريعي", "My projects")}>
          {projects.map((project) => <li key={project.id}>
            <DirectoryLink to={"/projects?project=" + project.id} navigate={navigate}
              aria-current={project.id === projectId ? "location" : undefined}>
              <Folder size={16} aria-hidden="true" /><bdi>{project.name}</bdi>
            </DirectoryLink>
            <DirectoryLink className="personal-nav-add" to={"/new-scan?project=" + encodeURIComponent(project.id)} navigate={navigate}
              aria-label={t("فحص جديد في " + project.name, "New scan in " + project.name)}>
              <Plus size={14} aria-hidden="true" />
            </DirectoryLink>
          </li>)}
        </ul>
      </div>}
      <div className="personal-nav-account">
        <DirectoryLink to="/settings?tab=github" navigate={navigate} aria-current={params.get("tab") === "github" ? "page" : undefined}>
          <GitBranch size={18} aria-hidden="true" />{t("اتصال GitHub", "GitHub Connection")}
        </DirectoryLink>
        <DirectoryLink to="/settings" navigate={navigate} aria-current={location.pathname === "/settings" && !params.has("tab") ? "page" : undefined}>
          <Settings size={18} aria-hidden="true" />{t("الإعدادات", "Settings")}
        </DirectoryLink>
        <button type="button" onClick={logout} disabled={leaving}>
          <LogOut size={18} aria-hidden="true" />{t("تسجيل الخروج", "Logout")}
        </button>
      </div>
      {failure && <p className="workspace-error" role="alert">{errorText(failure, t)}{" "}
        <button type="button" onClick={() => setRetry((count) => count + 1)}>{t("إعادة تحميل القائمة", "Reload menu")}</button>
      </p>}
    </div>
  </nav>;
}

export function PersonalDirectory({ projects, creating, navigate, refresh, submit, busy, lang }) {
  const t = translate(lang);
  const Chevron = lang === "ar" ? ChevronLeft : ChevronRight;
  if (creating) return <section className="card project-panel personal-project-editor">
    <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
      const project = await action(api + "/projects", post({ name: data.get("name") }));
      await refresh();
      navigate("/projects?project=" + project.id);
    })}>
      <label>{t("اسم المشروع", "Project name")}<input name="name" maxLength={120} required dir="auto" /></label>
      <div className="workspace-actions">
        <button className="btn primary" disabled={busy}>{t("إنشاء مشروع", "Create project")}</button>
      </div>
    </form>
  </section>;
  return <ProjectList projects={projects} navigate={navigate} refresh={refresh} submit={submit} busy={busy} lang={lang} />;
}

function ProjectList({ projects, navigate, refresh, submit, busy, lang }) {
  const t = translate(lang);
  const Chevron = lang === "ar" ? ChevronLeft : ChevronRight;
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [archived, setArchived] = useState(null);
  const [showArchived, setShowArchived] = useState(false);
  const [listFailure, setListFailure] = useState(null);

  useEffect(() => {
    if (!showArchived) return;
    const controller = new AbortController();
    setListFailure(null);
    action(api + "/projects?archived=true", { signal: controller.signal }).then(
      ({ projects: items }) => { if (!controller.signal.aborted) setArchived(items); },
      (error) => { if (!controller.signal.aborted) setListFailure(error); },
    );
    return () => controller.abort();
  }, [showArchived, projects]);

  const needle = query.trim().toLowerCase();
  const visible = projects.filter((project) => project.name.toLowerCase().includes(needle));
  const toolbar = <div className="personal-project-toolbar">
    <DirectoryLink className="btn primary" to="/projects?new=1" navigate={navigate}>
      <FolderPlus size={16} aria-hidden="true" />{t("مشروع جديد", "New project")}
    </DirectoryLink>
    {projects.length > 0 && <label className="personal-project-search">
      <Search size={16} aria-hidden="true" />
      <input type="search" value={query} onChange={(event) => setQuery(event.target.value)} dir="auto"
        placeholder={t("ابحث في المشاريع", "Search projects")} aria-label={t("ابحث في المشاريع", "Search projects")} />
    </label>}
    <button className="btn" type="button" aria-pressed={showArchived} onClick={() => setShowArchived((value) => !value)}>
      <Trash2 size={16} aria-hidden="true" />{showArchived ? t("إخفاء المحذوف", "Hide deleted") : t("المشاريع المحذوفة", "Deleted projects")}
    </button>
  </div>;

  return <>
    {toolbar}
    {!projects.length && <section className="card project-panel personal-project-empty">
      <h2>{t("لسه مفيش مشاريع", "No projects yet")}</h2>
      <p>{t("اضغط «مشروع جديد» لبدء أول فحص.", "Choose New project to start your first scan.")}</p>
    </section>}
    {projects.length > 0 && !visible.length && <p role="status">{t("مفيش مشروع بالاسم ده.", "No project matches that name.")}</p>}
    {visible.length > 0 && <ul className="personal-project-list" aria-label={t("مشاريع الحساب", "Your projects")}>
      {visible.map((project) => {
        const updated = project.updated_at || project.created_at;
        const path = api + "/projects/" + project.id;
        return <li key={project.id}>
          <DirectoryLink className="personal-project-card" to={"/projects?project=" + project.id}
            navigate={navigate}>
            <span className="personal-project-marker"><Folder size={20} aria-hidden="true" /></span>
            <span><bdi>{project.name}</bdi>
              {updated && <time dateTime={updated}>
                {new Date(updated).toLocaleDateString(lang === "ar" ? "ar-EG" : "en", { dateStyle: "medium" })}
              </time>}
            </span>
            <Chevron size={18} aria-hidden="true" />
          </DirectoryLink>
          {editing === project.id ? <form className="project-form personal-project-inline" onSubmit={(event) => submit(event, async (data) => {
            await action(path, json("PATCH", { name: data.get("name") }));
            await refresh();
            setEditing(null);
          })}>
            <label>{t("اسم المشروع", "Project name")}<input name="name" defaultValue={project.name} maxLength={120} required dir="auto" autoFocus /></label>
            <div className="workspace-actions">
              <button className="btn primary" disabled={busy}>{t("حفظ الاسم", "Save name")}</button>
              <button className="btn" type="button" disabled={busy} onClick={() => setEditing(null)}>{t("إلغاء", "Cancel")}</button>
            </div>
          </form> : deleting === project.id ? <form className="project-form personal-project-inline" onSubmit={(event) => submit(event, async () => {
            await action(path, { method: "DELETE" });
            await refresh();
            setDeleting(null);
          })}>
            <p>{t("هيتخفي المشروع وتقاريره وهتتلغي الفحوصات الجارية. تقدر ترجّعه من «المشاريع المحذوفة».", "The project and its reports are hidden and running scans are cancelled. You can restore it from Deleted projects.")}</p>
            <div className="workspace-actions">
              <button className="btn danger-action" disabled={busy}>{t("تأكيد الحذف", "Confirm deletion")}</button>
              <button className="btn" type="button" disabled={busy} onClick={() => setDeleting(null)}>{t("رجوع", "Cancel")}</button>
            </div>
          </form> : <div className="workspace-actions personal-project-actions">
            <DirectoryLink className="btn primary" to={"/new-scan?project=" + encodeURIComponent(project.id)} navigate={navigate}
              aria-label={t("فحص جديد، " + project.name, "Add scan, " + project.name)}>
              <Plus size={14} aria-hidden="true" />{t("فحص جديد", "Add scan")}
            </DirectoryLink>
            <button className="btn" type="button" disabled={busy} onClick={() => { setDeleting(null); setEditing(project.id); }}>
              <Pencil size={14} aria-hidden="true" />{t("تعديل الاسم", "Rename")}
            </button>
            <button className="btn danger-action" type="button" disabled={busy} onClick={() => { setEditing(null); setDeleting(project.id); }}>
              <Trash2 size={14} aria-hidden="true" />{t("حذف", "Delete")}
            </button>
          </div>}
        </li>;
      })}
    </ul>}
    {showArchived && <section className="card project-panel personal-project-archived" aria-labelledby="archived-heading">
      <h2 id="archived-heading">{t("المشاريع المحذوفة", "Deleted projects")}</h2>
      {listFailure && <p role="alert" className="workspace-error">{errorText(listFailure, t)}</p>}
      {!archived && !listFailure && <p role="status">{t("بنحمّل…", "Loading…")}</p>}
      {archived && !archived.length && <p>{t("مفيش مشاريع محذوفة.", "No deleted projects.")}</p>}
      {archived?.length > 0 && <ul className="personal-archived-list">
        {archived.map((project) => <li key={project.id}>
          <bdi>{project.name}</bdi>
          <time dateTime={project.deleted_at}>{new Date(project.deleted_at).toLocaleDateString(lang === "ar" ? "ar-EG" : "en", { dateStyle: "medium" })}</time>
          <form onSubmit={(event) => submit(event, async () => {
            await action(api + "/projects/" + project.id + "/restore", { method: "POST" });
            await refresh();
          })}><button className="btn" disabled={busy}><RotateCcw size={14} aria-hidden="true" />{t("استرجاع", "Restore")}</button></form>
        </li>)}
      </ul>}
    </section>}
  </>;
}

export function PersonalProjectManagement({ project, navigate, refresh, submit, busy, lang, children }) {
  const t = translate(lang);
  const [confirm, setConfirm] = useState(false);
  const path = api + "/projects/" + project.id;
  return <div className="personal-project-management">
    <section className="card project-panel">
      <h2>{t("بيانات المشروع", "Project details")}</h2>
      <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
        await action(path, json("PATCH", { name: data.get("name") }));
        await refresh();
      })}>
        <label>{t("اسم المشروع", "Project name")}<input name="name" defaultValue={project.name} maxLength={120} required dir="auto" /></label>
        <button className="btn primary" disabled={busy}>{t("حفظ الاسم", "Save name")}</button>
      </form>
    </section>
    {children}
    <section className="card project-panel">
      <h2>{t("حذف المشروع", "Delete project")}</h2>
      {confirm ? <form className="project-form" onSubmit={(event) => submit(event, async () => {
        await action(path, { method: "DELETE" });
        await refresh();
        navigate("/projects");
      })}>
        <label className="project-check">
          <input type="checkbox" required />
          {t("أؤكد إخفاء المشروع وتقاريره وإلغاء الفحوصات الجارية.", "Hide the project and its reports and cancel running scans.")}
        </label>
        <div className="workspace-actions">
          <button className="btn danger-action" disabled={busy}>{t("تأكيد حذف المشروع", "Confirm project deletion")}</button>
          <button className="btn" type="button" onClick={() => setConfirm(false)} disabled={busy}>{t("رجوع", "Cancel")}</button>
        </div>
      </form> : <button className="btn danger-action" type="button" disabled={busy} onClick={() => setConfirm(true)}>
        {t("حذف المشروع", "Delete project")}
      </button>}
    </section>
  </div>;
}

export function PersonalGitHub({ lang }) {
  const t = translate(lang);
  const [view, setView] = useState(null);
  const [failure, setFailure] = useState(null);
  const [busy, setBusy] = useState(false);
  const [setup, setSetup] = useState(null);
  const [listing, setListing] = useState(null);
  const [checking, setChecking] = useState(false);
  const [repositoryRevision, setRepositoryRevision] = useState(0);
  const [statusRevision, setStatusRevision] = useState(0);
  const [query, setQuery] = useState("");
  const connected = Boolean(view?.connected);
  const outcome = new URLSearchParams(window.location.search).get("github");
  const callbackMessage = {
    failed: t("تفويض GitHub ما اكتملش. اضغط «اربط GitHub» وكمّل التفويض من نفس المتصفح.",
      "GitHub authorization did not complete. Connect again and finish it in the same browser."),
    credentials: t("GitHub رفض بيانات التطبيق. راجع الـClient ID والـClient Secret في إعداد بصيرة.",
      "GitHub rejected the app credentials. Check the Client ID and Client Secret in Basira’s setup."),
    expiration: t("GitHub مرجّعش رمز مؤقت صالح. اتأكد إن انتهاء صلاحية الرموز مفعّل في إعداد التطبيق.",
      "GitHub did not return a valid expiring token. Check token expiration in the app settings."),
    unavailable: t("بصيرة مقدرش يكمّل الاتصال بـGitHub دلوقتي. جرّب مرة تانية.",
      "Basira could not complete the GitHub connection. Try again."),
  }[outcome];
  const repositories = listing?.repositories;
  const visible = repositories?.filter((repo) => repo.repository.toLowerCase().includes(query.trim().toLowerCase()));

  useEffect(() => {
    const controller = new AbortController();
    setFailure(null);
    action(api + "/github/connection", { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setView(value); },
      (error) => { if (!controller.signal.aborted) setFailure(error); },
    );
    action(api + "/github/setup", { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setSetup(value); },
      () => {},
    );
    return () => controller.abort();
  }, [statusRevision]);

  useEffect(() => {
    if (!connected) return;
    const controller = new AbortController();
    setChecking(true);
    setFailure(null);
    action(api + "/github/repositories", { signal: controller.signal }).then(
      (result) => {
        if (!controller.signal.aborted) setListing(result);
      },
      async (error) => {
        if (controller.signal.aborted) return;
        setListing(null);
        setFailure(error);
        if (error.status === 409) {
          const status = await action(api + "/github/connection", { signal: controller.signal }).catch(() => null);
          if (status && !controller.signal.aborted) {
            setChecking(false);
            setView(status);
          }
        }
      },
    ).finally(() => { if (!controller.signal.aborted) setChecking(false); });
    return () => controller.abort();
  }, [connected, repositoryRevision]);
  async function changeConnection() {
    setFailure(null);
    setBusy(true);
    try {
      if (view.connected) {
        await action(api + "/github/connection", { method: "DELETE" });
        setView({ ...view, connected: false });
        setListing(null);
        setQuery("");
        setChecking(false);
        window.history.replaceState(null, "", "/settings?tab=github");
      } else {
        const { url } = await action(api + "/github/authorize", { method: "POST" });
        window.location.assign(url);
      }
    } catch (error) {
      setFailure(error);
    } finally {
      setBusy(false);
    }
  }

  return <div className="project-workspace personal-github">
    <header className="project-header"><h1>{t("اتصال GitHub", "GitHub Connection")}</h1></header>
    <section className="card project-panel github-account">
      {view ? <>
        <div className="github-account-identity">
          <span className="personal-project-marker"><GitBranch size={22} aria-hidden="true" /></span>
          <div>
            <h2>{t("حساب GitHub", "GitHub account")}</h2>
            {connected && listing?.account?.login && <bdi>@{listing.account.login}</bdi>}
          </div>
          <span className="github-connection-state" data-connected={connected} role="status">
            {connected && <CheckCircle2 size={15} aria-hidden="true" />}
            {connected ? t("متصل", "Connected")
              : view.connect_available ? t("في انتظار التفويض", "Authorization needed") : t("الإعداد مطلوب", "Setup required")}
          </span>
        </div>
        {!connected && <p>{view.connect_available
          ? t("اربط حسابك عشان تظهر المستودعات اللي اخترتها عند تثبيت التطبيق على GitHub.",
            "Connect your account to see the repositories selected in the GitHub App installation.")
          : t("إعداد GitHub App مطلوب على السيرفر.", "The server needs a GitHub App configuration.")}</p>}
        {failure && (!connected || !checking) && <p className="workspace-error" role="alert">{errorText(failure, t)}</p>}
        {callbackMessage && view.connect_available && !connected && !failure && <p className="workspace-error" role="alert">
          {callbackMessage}
        </p>}
        <div className="workspace-actions">
          {view.connect_available && <button type="button" className={connected ? "btn" : "btn primary"}
            disabled={busy} onClick={changeConnection}>
            {connected ? t("افصل GitHub", "Disconnect GitHub") : t("اربط GitHub", "Connect GitHub")}
          </button>}
          {view.connect_available && safeGithubUrl(setup?.install_url) && <a className="btn" href={safeGithubUrl(setup.install_url)}
            target="_blank" rel="noreferrer">{t("اختار المستودعات على GitHub", "Select repositories on GitHub")}
            <ArrowUpRight size={16} aria-hidden="true" /></a>}
          {view.connected && <a className="btn" href="https://github.com/settings/apps/authorizations">
            {t("إدارة إذن GitHub", "Manage GitHub authorization")}
          </a>}
          {!view.connect_available && <button type="button" className="btn" onClick={() => setStatusRevision((value) => value + 1)}>
            {t("إعادة التحقق", "Check again")}
          </button>}
        </div>
      </> : failure ? <>
        <p className="workspace-error" role="alert">{errorText(failure, t)}</p>
        <button type="button" className="btn" onClick={() => setStatusRevision((value) => value + 1)}>{t("أعد المحاولة", "Retry")}</button>
      </> : <p role="status">{t("بنحمّل حالة الاتصال…", "Loading connection status…")}</p>}
    </section>
    {connected && <section className="card project-panel github-repositories">
      <div className="github-repositories-header">
        <h2>{t("المستودعات المتاحة", "Available repositories")}
          {repositories && <span className="github-repository-count">{repositories.length.toLocaleString(lang === "ar" ? "ar-EG" : "en")}</span>}
        </h2>
        <button type="button" className="btn" disabled={busy || checking}
          onClick={() => setRepositoryRevision((value) => value + 1)}>
          <RefreshCw size={16} aria-hidden="true" />{t("حدّث المستودعات", "Refresh repositories")}
        </button>
      </div>
      {checking && <p role="status">{t("بنحمّل المستودعات…", "Loading repositories…")}</p>}
      {repositories?.length > 1 && <label className="github-repository-search">
        <Search size={17} aria-hidden="true" />
        <input type="search" value={query} onChange={(event) => setQuery(event.target.value)}
          aria-label={t("ابحث عن مستودع", "Find a repository")} placeholder={t("ابحث عن مستودع", "Find a repository")} />
      </label>}
      {!!visible?.length && <ul className="github-repository-list">
        {visible.map((repo) => <li key={repo.installation_id + "/" + repo.repository_id}>
          <Folder size={19} aria-hidden="true" />
          <div className="github-repository-name">
            <a href={"https://github.com/" + String(repo.repository).split("/").map(encodeURIComponent).join("/")} target="_blank" rel="noreferrer">
              <bdi>{repo.repository}</bdi><ArrowUpRight size={14} aria-hidden="true" />
            </a>
            {repo.default_branch && <small><GitBranch size={13} aria-hidden="true" />
              {t("الفرع الافتراضي", "Default branch")} <bdi>{repo.default_branch}</bdi>
            </small>}
          </div>
          {typeof repo.private === "boolean" && <span className="github-repository-visibility">
            {repo.private ? t("خاص", "Private") : t("عام", "Public")}
          </span>}
        </li>)}
      </ul>}
      {repositories?.length === 0 && !checking && <p role="status">
        {t("ربط الحساب تم. اختار المستودعات على GitHub، وبعدها حدّث القائمة.",
          "Your account is connected. Select repositories on GitHub, then refresh this list.")}
      </p>}
      {!!repositories?.length && !visible.length && !checking && <p role="status">{t("مفيش مستودعات مطابقة للبحث.", "No repositories match your search.")}</p>}
      {!!visible?.length && <div><a className="btn primary" href="/new-scan">{t("ابدأ فحص مستودع", "Start a repository scan")}</a></div>}
    </section>}
  </div>;
}
