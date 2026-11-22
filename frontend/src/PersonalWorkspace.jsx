import React, { useEffect, useId, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Folder, FolderPlus, GitBranch, LogOut, Menu, Settings } from "lucide-react";
import { post } from "./data";
import { action, api, errorText, json, translate } from "./platformClient";
import { DirectoryLink } from "./ProjectDirectory";
import "./personal-workspace.css";

export function PersonalSidebar({ location, navigate, lang, revision, onLogout }) {
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

  return <nav className="personal-sidebar" data-project-directory={projectDirectory || undefined}
    aria-label={t("مساحة العمل", "Workspace navigation")} onKeyDown={(event) => {
    if (event.key === "Escape" && open) {
      setOpen(false);
      menu.current?.focus();
    }
  }}>
    <button ref={menu} className="btn personal-menu" type="button" aria-expanded={open} aria-controls={linksId}
      onClick={() => setOpen((value) => !value)}><Menu size={18} aria-hidden="true" />{t("القائمة", "Menu")}</button>
    <div id={linksId} className={"personal-links" + (open ? " is-open" : "")}>
      <DirectoryLink className="personal-new-project" to="/projects?new=1" navigate={navigate}
        aria-current={projectDirectory && params.has("new") ? "page" : undefined}>
        <FolderPlus size={18} aria-hidden="true" />{t("مشروع جديد", "New Project")}
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
  if (!projects.length) return <section className="card project-panel personal-project-empty">
    <h2>{t("لسه مفيش مشاريع", "No projects yet")}</h2>
    <p>{t("اختار «مشروع جديد» من قائمة مساحة العمل لبدء أول فحص.", "Choose New Project in the workspace menu to start your first scan.")}</p>
  </section>;
  return <ul className="personal-project-list" aria-label={t("مشاريع الحساب", "Your projects")}>
    {projects.map((project) => {
      const updated = project.updated_at || project.created_at;
      const nameId = "project-card-" + project.id;
      return <li key={project.id}><DirectoryLink className="personal-project-card" to={"/projects?project=" + project.id}
        navigate={navigate} aria-labelledby={nameId} aria-describedby={updated ? nameId + "-updated" : undefined}>
        <span className="personal-project-marker"><Folder size={20} aria-hidden="true" /></span>
        <span><bdi id={nameId}>{project.name}</bdi>
          {updated && <time id={nameId + "-updated"} dateTime={updated}>
            {new Date(updated).toLocaleDateString(lang === "ar" ? "ar-EG" : "en", { dateStyle: "medium" })}
          </time>}
        </span>
        <Chevron size={18} aria-hidden="true" />
      </DirectoryLink></li>;
    })}
  </ul>;
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
  const [repositories, setRepositories] = useState(null);
  const [checking, setChecking] = useState(false);
  const outcome = new URLSearchParams(window.location.search).get("github");
  useEffect(() => {
    const controller = new AbortController();
    action(api + "/github/connection", { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setView(value); },
      (error) => { if (!controller.signal.aborted) setFailure(error); },
    );
    action(api + "/github/setup", { signal: controller.signal }).then(setSetup, () => {});
    return () => controller.abort();
  }, []);
  async function changeConnection() {
    setFailure(null);
    setBusy(true);
    try {
      if (view.connected) {
        await action(api + "/github/connection", { method: "DELETE" });
        setView({ ...view, connected: false });
        setRepositories(null);
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
  async function checkConnection() {
    setChecking(true);
    setFailure(null);
    try {
      const result = await action(api + "/github/repositories");
      setRepositories(result.repositories);
    } catch (error) {
      setRepositories(null);
      setFailure(error);
    } finally {
      setChecking(false);
    }
  }
  const registration = setup && "https://github.com/settings/apps/new?" + new URLSearchParams({
    name: "Marsad Repository Review", url: "https://github.com/Ibrahim-Al-Jid/Marsad",
    "callback_urls[]": setup.callback_url, contents: "read", public: "false",
    webhook_active: "false", request_oauth_on_install: "false",
  });
  return <div className="project-workspace">
    <header className="project-header"><h1>{t("اتصال GitHub", "GitHub Connection")}</h1></header>
    <section className="card project-panel personal-github">
      <span className="personal-project-marker"><GitBranch size={22} aria-hidden="true" /></span>
      {failure && <p role="alert">{errorText(failure, t)}</p>}
      {outcome === "failed" && !view?.connected && <p role="alert">
        {t("ربط GitHub ما اكتملش. راجعي الإذن وحاولي تاني.", "GitHub authorization did not complete. Check permissions and try again.")}
      </p>}
      {view ? <>
        <p>{view.connected ? t("الحساب متصل بـGitHub.", "GitHub is connected.")
          : view.connect_available ? t("ثبّتي GitHub App على المستودعات المختارة، ثم اربطي حسابك.",
            "Install the GitHub App on selected repositories and authorize your account.")
            : t("إعداد GitHub App مطلوب على السيرفر.", "The server needs a GitHub App configuration.")}</p>
        <div className="workspace-actions">
          {!view.connect_available && registration && <a className="btn primary" href={registration}
            target="_blank" rel="noreferrer">{t("افتح إعداد GitHub App", "Open GitHub App setup")}</a>}
          {view.connect_available && setup?.install_url && <a className="btn" href={setup.install_url}
            target="_blank" rel="noreferrer">{t("اختاري المستودعات على GitHub", "Select repositories on GitHub")}</a>}
          {view.connect_available && <button type="button" className="btn primary" disabled={busy} onClick={changeConnection}>
            {view.connected ? t("افصلي اتصال GitHub", "Disconnect GitHub") : t("اربطي GitHub", "Connect GitHub")}
          </button>}
          {view.connected && <a className="btn" href="https://github.com/settings/apps/authorizations">
            {t("إدارة إذن GitHub", "Manage GitHub authorization")}
          </a>}
          {view.connected && <button type="button" className="btn" disabled={busy || checking} onClick={checkConnection}>
            {checking ? t("بنجرب الاتصال…", "Testing connection…") : t("جرّبي الاتصال", "Test connection")}
          </button>}
        </div>
        {!view.connect_available && setup && <div className="project-form">
          <p>{t("استخدمي عنوان الرجوع ده في GitHub App، وحددي صلاحية قراءة Contents ومستودعات مختارة.",
            "Use this callback in the GitHub App with Contents read access and selected repositories.")}</p>
          <code dir="ltr">{setup.callback_url}</code>
          <p>{t("على النسخة المحلية، احفظي إعداد التطبيق من الطرفية، وبعدها حدّثي الصفحة.",
            "For local Windows, save the app settings from the terminal, then reload this page.")}</p>
          <code dir="ltr">.venv\Scripts\python.exe ops/configure-local-github.py</code>
        </div>}
        {repositories && <div aria-live="polite">
          <h2>{t("المستودعات المتاحة", "Available repositories")}</h2>
          {repositories.length ? <>
            <ul>{repositories.map((repo) => <li key={repo.installation_id + "/" + repo.repository_id}>
              <bdi>{repo.repository}</bdi> · <bdi>{repo.default_branch}</bdi>
            </li>)}</ul>
            <a className="btn primary" href="/new-scan">{t("ابدئي فحص مستودع", "Start a repository scan")}</a>
          </> : <p>{t("اختاري المستودع من إعداد التثبيت على GitHub وجرّبي الاتصال تاني.",
            "Select a repository in the GitHub App installation and test again.")}</p>}
        </div>}
      </> : !failure && <p role="status">{t("بنحمّل حالة الاتصال…", "Loading connection status…")}</p>}
    </section>
  </div>;
}
