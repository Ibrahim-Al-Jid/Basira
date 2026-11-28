import React, { useEffect, useState } from "react";
import { ChevronDown, FileText, Folder, Moon, Search, ShieldCheck, Sun, UserRound, Workflow } from "lucide-react";
import { Modal } from "./Dialogs";
import { action, api } from "./platformClient";

const labels = {
  ar: {
    overview: "نظرة عامة", projects: "المشاريع", scans: "سجل الفحوصات", reports: "التقارير",
    newScan: "فحص جديد", workspace: "مساحة العمل", account: "الحساب", signin: "تسجيل الدخول",
    skip: "انتقلي إلى المحتوى", light: "الوضع الفاتح", dark: "الوضع الغامق", language: "Switch to English",
  },
  en: {
    overview: "Overview", projects: "Projects", scans: "Scan history", reports: "Reports",
    newScan: "New scan", workspace: "Workspace", account: "Account", signin: "Sign in",
    skip: "Skip to content", light: "Light mode", dark: "Dark mode", language: "التبديل إلى العربية",
  },
};

export const readPreference = (key, fallback) => {
  try { return localStorage.getItem("basira-" + key) ?? fallback; }
  catch { return fallback; }
};
export const savePreference = (key, value) => {
  try { localStorage.setItem("basira-" + key, value); }
  catch { /* Preferences are optional when storage is unavailable. */ }
};

export function WorkspaceBrand({ href, follow, lang }) {
  return <a className="site-brand" href={href} onClick={(event) => follow(event, href)}
    aria-label={lang === "ar" ? "بصيرة، الرئيسية" : "Basira home"}>
    <span className="site-brand-mark" aria-hidden="true"><ShieldCheck size={33} strokeWidth={1.7} /></span>
    <span className="site-brand-copy">
      <strong dir="ltr">BASIRA</strong>
      <small>{lang === "ar" ? "مراجعة أمان المشاريع" : "PROJECT SECURITY REVIEW"}</small>
    </span>
  </a>;
}

function WorkspaceSearch({ lang, authenticated, follow, close }) {
  const t = (ar, en) => lang === "ar" ? ar : en;
  const [query, setQuery] = useState("");
  const [projects, setProjects] = useState([]);
  const [projectError, setProjectError] = useState(false);
  const clean = query.trim();
  const visible = projects.filter((project) => project.name.toLocaleLowerCase().includes(clean.toLocaleLowerCase())).slice(0, 6);
  const params = new URLSearchParams(clean ? { q: clean } : {});
  useEffect(() => {
    if (!authenticated) return undefined;
    const controller = new AbortController();
    action(api + "/projects", { signal: controller.signal }).then(
      (data) => { if (!controller.signal.aborted) setProjects(data.projects); },
      () => { if (!controller.signal.aborted) setProjectError(true); },
    );
    return () => controller.abort();
  }, [authenticated]);
  const go = (event, url) => {
    follow(event, url);
    close();
  };
  return <Modal title={t("بحث في مساحة العمل", "Search workspace")} close={close} lang={lang}>
    <div className="command-search-dialog">
      <label className="overview-search"><Search size={19} aria-hidden="true" />
        <input autoFocus type="search" value={query} onChange={(event) => setQuery(event.target.value)}
          aria-label={t("اسم المشروع أو التقرير", "Project or report name")}
          placeholder={t("اسم المشروع أو التقرير", "Project or report name")} />
      </label>
      <div className="command-search-results">
        {visible.map((project) => {
          const url = "/projects?project=" + encodeURIComponent(project.id);
          return <a href={url} key={project.id} onClick={(event) => go(event, url)}><Folder size={18} aria-hidden="true" /><bdi>{project.name}</bdi></a>;
        })}
        <a href="/projects" onClick={(event) => go(event, "/projects")}><Folder size={18} aria-hidden="true" />{t("كل المشاريع", "All projects")}</a>
        <a href={"/reports?" + params} onClick={(event) => go(event, "/reports?" + params)}>
          <FileText size={18} aria-hidden="true" />{clean ? t("ابحثي في التقارير", "Search the report archive") : t("كل التقارير", "All reports")}
        </a>
      </div>
      {projectError && <p className="command-panel-note" role="status">{t("تعذّر تحميل المشاريع.", "Projects could not be loaded.")}</p>}
    </div>
  </Modal>;
}

export function SiteHeader({ pathname, follow, lang, authenticated, preferences }) {
  const t = labels[lang];
  const route = pathname.split("/").filter(Boolean)[0] ?? "";
  const [searchOpen, setSearchOpen] = useState(false);
  const searchLabel = lang === "ar" ? "ابحثي عن مشروع أو تقرير…" : "Search projects and reports…";
  const ThemeIcon = preferences.theme === "dark" ? Sun : Moon;
  const themeLabel = preferences.theme === "dark" ? t.light : t.dark;
  const accountPath = authenticated ? "/settings" : "/signin";
  useEffect(() => {
    function keyboard(event) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        if (document.querySelector("dialog[open]")) return;
        event.preventDefault();
        setSearchOpen(true);
      }
    }
    window.addEventListener("keydown", keyboard);
    return () => window.removeEventListener("keydown", keyboard);
  }, []);

  return <>
    <a className="site-skip" href="#main-content">{t.skip}</a>
    <header className="site-header">
      <div className="site-header-inner">
        <button type="button" className="command-search" onClick={() => setSearchOpen(true)}
          aria-label={searchLabel} aria-keyshortcuts="Control+k Meta+k">
          <Search size={20} aria-hidden="true" /><span>{searchLabel}</span><kbd aria-hidden="true" dir="ltr">Ctrl K</kbd>
        </button>
        <div className="site-controls">
          <div className="command-preferences">
            <button className="site-icon" type="button" aria-label={themeLabel} title={themeLabel}
              onClick={() => preferences.setTheme(preferences.theme === "dark" ? "light" : "dark")}>
              <ThemeIcon size={17} aria-hidden="true" />
            </button>
            <button className="site-icon" type="button" aria-label={t.language} title={t.language}
              onClick={() => preferences.setLang(lang === "ar" ? "en" : "ar")}>
              {lang === "ar" ? "EN" : "ع"}
            </button>
          </div>
          <a className="site-icon site-account" href={accountPath}
            aria-label={authenticated ? t.account : t.signin}
            aria-current={route === "settings" ? "page" : undefined} onClick={(event) => follow(event, accountPath)}>
            <UserRound size={17} aria-hidden="true" />
          </a>
        </div>
      </div>
    </header>
    {searchOpen && <WorkspaceSearch lang={lang} authenticated={authenticated} follow={follow} close={() => setSearchOpen(false)} />}
  </>;
}
