import React, { useEffect, useRef, useState } from "react";
import { Building2, FolderOpen, Plus } from "lucide-react";
import { post } from "./data";
import { api, action, translate } from "./platformClient";

const roleNames = {
  owner: ["مالك", "Owner"],
  admin: ["مدير", "Admin"],
  analyst: ["محلّل", "Analyst"],
  viewer: ["مشاهد", "Viewer"],
};

export function DirectoryLink({ to, navigate, children, ...props }) {
  return <a {...props} href={to} onClick={(event) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
    event.preventDefault();
    navigate(to);
  }}>{children}</a>;
}

export function ProjectDirectory({ organizations, projects, selectedOrg, navigate, refresh, submit, busy, lang }) {
  const t = translate(lang);
  const [create, setCreate] = useState(null);
  const createField = useRef(null);
  const newOrgButton = useRef(null);
  const newProjectButton = useRef(null);
  const returnFocus = useRef(null);
  const current = organizations.find((org) => org.id === selectedOrg) || organizations[0];
  const entries = projects.filter((project) => project.org_id === current?.id);
  const canCreate = current && ["owner", "admin"].includes(current.role);
  const firstOrganization = !current;
  const showNewOrg = firstOrganization || create === "organization";
  const showNewProject = canCreate && !showNewOrg && (create === "project" || !entries.length);
  useEffect(() => {
    if (create) createField.current?.focus();
    else {
      returnFocus.current?.current?.focus();
      returnFocus.current = null;
    }
  }, [create]);

  function cancelForm(trigger) {
    returnFocus.current = trigger;
    setCreate(null);
  }

  return <div className="workspace-directory">
    <section className="card project-panel directory-organization" aria-labelledby="directory-org-heading">
      <div className="directory-heading">
        <h2 id="directory-org-heading">{t("المؤسسات", "Organizations")}</h2>
        {!showNewOrg && <button ref={newOrgButton} className="btn" type="button" onClick={() => setCreate("organization")}>
          <Plus size={16} aria-hidden="true" />{t("مؤسسة جديدة", "New organization")}
        </button>}
      </div>
      {showNewOrg && <form className="project-form directory-form" onSubmit={(event) => submit(event, async (data) => {
        const created = await action(api + "/organizations", post({ name: data.get("name") }));
        await refresh();
        setCreate(null);
        navigate("/projects?org=" + created.id);
      })}>
        <label>{t("اسم المؤسسة", "Organization name")}<input ref={create === "organization" ? createField : null} name="name" maxLength={120} required /></label>
        <div className="workspace-actions">
          <button className="btn primary" disabled={busy}>{t("إنشاء مؤسسة", "Create organization")}</button>
          {!firstOrganization && <button className="btn" type="button" disabled={busy} onClick={() => cancelForm(newOrgButton)}>{t("إلغاء", "Cancel")}</button>}
        </div>
      </form>}
      {!!organizations.length && <ul className="directory-org-list">
        {organizations.map((organization) => <li key={organization.id}>
          <DirectoryLink to={"/projects?org=" + organization.id} navigate={(to) => { setCreate(null); navigate(to); }}
            aria-current={organization.id === current.id ? "true" : undefined}>
            <Building2 size={18} aria-hidden="true" />
            <bdi>{organization.name}</bdi>
            {roleNames[organization.role] && <small>{t(...roleNames[organization.role])}</small>}
          </DirectoryLink>
        </li>)}
      </ul>}
    </section>
    {current && <section className="card project-panel directory-projects" aria-labelledby="directory-project-heading">
      <div className="directory-heading">
        <div><h2 id="directory-project-heading">{t("مشاريع المؤسسة", "Organization projects")}</h2><p><bdi>{current.name}</bdi></p></div>
        {canCreate && !showNewOrg && !showNewProject && <button ref={newProjectButton} className="btn primary" type="button" onClick={() => setCreate("project")}>
          <Plus size={16} aria-hidden="true" />{t("مشروع جديد", "New project")}
        </button>}
      </div>
      {showNewProject && <form key={current.id} className="project-form directory-form" onSubmit={(event) => submit(event, async (data) => {
        const created = await action(api + "/organizations/" + current.id + "/projects", post({ name: data.get("name") }));
        await refresh();
        setCreate(null);
        navigate("/projects?project=" + created.id);
      })}>
        <label>{t("اسم المشروع", "Project name")}<input ref={create === "project" ? createField : null} name="name" maxLength={120} required /></label>
        <div className="workspace-actions">
          <button className="btn primary" disabled={busy}>{t("إنشاء مشروع", "Create project")}</button>
          {!!entries.length && <button className="btn" type="button" disabled={busy} onClick={() => cancelForm(newProjectButton)}>{t("إلغاء", "Cancel")}</button>}
        </div>
      </form>}
      {entries.length > 0 ? <ul className="directory-project-list">
        {entries.map((project) => <li key={project.id}>
          <DirectoryLink to={"/projects?project=" + project.id} navigate={navigate}>
            <span className="directory-project-mark"><FolderOpen size={20} aria-hidden="true" /></span>
            <bdi>{project.name}</bdi>
          </DirectoryLink>
        </li>)}
      </ul> : <p>{t("لسه مفيش مشاريع متاحة في المؤسسة دي.", "There are no accessible projects in this organization yet.")}</p>}
    </section>}
  </div>;
}
