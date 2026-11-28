import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/ibm-plex-sans-arabic/arabic-400.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-500.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-600.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-700.css";
import "@fontsource-variable/space-grotesk";
import "@fontsource/cairo/arabic-700.css";
import "@fontsource/cairo/arabic-900.css";
import "@fontsource/cairo/latin-700.css";
import "@fontsource/cairo/latin-900.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import { Reports } from "./Reports";
import { Platform, usePlatformSession } from "./Platform";
import { Landing } from "./Landing";
import { Entry } from "./Entry";
import { SiteHeader, readPreference, savePreference } from "./SiteHeader";
import { action } from "./platformClient";
import "./style.css";
import "./workspace.css";
import "./design-variants.css";
import "./security-overview.css";
import "./command-center.css";
import "./command-light.css";
import "./entry.css";
import "./redesign.css";

function currentLocation() {
  return { pathname: window.location.pathname, search: window.location.search, hash: window.location.hash };
}

function App() {
  const [location, setLocation] = useState(currentLocation);
  const [lang, setLang] = useState(() => {
    const browserLanguage = (navigator.languages?.[0] || navigator.language || "").split("-")[0].toLowerCase();
    return readPreference("language", browserLanguage === "ar" ? "ar" : "en") === "ar" ? "ar" : "en";
  });
  const [theme, setTheme] = useState(() => readPreference("reference-theme", "dark") === "light" ? "light" : "dark");
  const preferences = { lang, setLang, theme, setTheme };
  const entryPage = location.pathname === "/" && !location.hash;
  const landingPage = /^\/(?:overview\/?)?$/.test(location.pathname);
  const signingInPage = /^\/signin\/?$/.test(location.pathname);
  const [product, setProduct] = useState(null);
  const [productError, setProductError] = useState(false);
  const [productAttempt, setProductAttempt] = useState(0);
  const [projectRevision, setProjectRevision] = useState(0);
  const personal = product?.personal_projects;
  const demoPage = /^\/demo\/?$/.test(location.pathname);
  const session = usePlatformSession();
  const t = (ar, en) => lang === "en" ? en : ar;
  const mainContent = useRef(null);
  const initialPath = useRef(location.pathname);
  const findingsPage = /^\/findings\/?$/.test(location.pathname);
  const reportsPage = /^\/reports(?:\/|$)/.test(location.pathname);
  const projectsPage = /^\/(?:projects(?:\/|$)|dashboard\/?$|new-scan\/?$|settings\/?$|signin\/?$)/.test(location.pathname);
  const scansRedirect = /^\/scans\/?$/.test(location.pathname);
    function navigate(path, { replace = false } = {}) {
    const previousPath = window.location.pathname;
    const update = replace ? "replaceState" : "pushState";
    if (path !== previousPath + window.location.search + window.location.hash) window.history[update](null, "", path);
    setLocation(currentLocation());
    if (window.location.pathname !== previousPath) window.scrollTo(0, 0);
  }

  function follow(event, path) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(path);
  }

  useEffect(() => {
    const controller = new AbortController();
    setProductError(false);
    action("/api/product", { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setProduct(value); },
      () => { if (!controller.signal.aborted) setProductError(true); },
    );
    return () => controller.abort();
  }, [productAttempt]);

  useEffect(() => {
    const onPopState = () => setLocation(currentLocation());
    window.addEventListener("popstate", onPopState);
    window.addEventListener("hashchange", onPopState);
    return () => {
      window.removeEventListener("popstate", onPopState);
      window.removeEventListener("hashchange", onPopState);
    };
  }, []);
  useEffect(() => {
    // Share-style URLs open the matching screen instead of an empty page.
    const report = location.pathname.match(/^\/projects\/([\w-]+)\/reports\/([\w-]+)\/?$/);
    const project = location.pathname.match(/^\/projects\/([\w-]+)\/?$/);
    if (report) navigate(`/reports/${report[2]}?project=${report[1]}`, { replace: true });
    else if (project) navigate(`/projects?project=${project[1]}`, { replace: true });
  }, [location.pathname]);
  useEffect(() => {
    const root = document.documentElement;
    root.lang = lang;
    root.dir = lang === "ar" ? "rtl" : "ltr";
    root.dataset.theme = theme;
    savePreference("language", lang);
    savePreference("reference-theme", theme);
  }, [lang, theme]);
  useEffect(() => {
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "light" ? "#edf5fd" : "#000b19");
  }, [theme]);
  useEffect(() => {
    const arabic = lang === "ar";
    document.title = entryPage ? (arabic ? "بصيرة | رؤية كاملة لمشروعك" : "BASIRA | A full view of your project")
      : landingPage ? "BASIRA | Demo overview"
      : "BASIRA | Workspace";
  }, [entryPage, landingPage, lang]);
  useEffect(() => {
    if (initialPath.current !== location.pathname) {
      initialPath.current = location.pathname;
      if (!reportsPage && !findingsPage) mainContent.current?.focus({ preventScroll: true });
    }
  }, [reportsPage, findingsPage, location.pathname]);

  useEffect(() => {
    if (!findingsPage) return;
    const params = new URLSearchParams(location.search);
    const report = params.get("report");
    params.delete("report");
    const detail = /^[a-f0-9]{32}$/.test(report || "") && /^[a-f0-9]{32}$/.test(params.get("project") || "");
    const query = params.size ? "?" + params : "";
    navigate((detail ? "/reports/" + report : "/reports") + query + (detail ? "#report-findings" : ""), { replace: true });
  }, [findingsPage, location.search]);
  useEffect(() => {
    if (location.hash === "#agents" || (landingPage && ["#workflow", "#coverage"].includes(location.hash))) {
      document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: "start" });
    }
  }, [landingPage, location.hash, location.pathname]);
  useEffect(() => {
    if (!demoPage || session.user === undefined) return;
    navigate(session.user ? "/new-scan" : "/signin", { replace: true });
  }, [demoPage, session.user]);
  useEffect(() => {
    // Scan history is a project tab now. Old links open it for the project they name, or for the first project.
    if (!/^\/scans\/?$/.test(location.pathname) || !session.user) return;
    const named = new URLSearchParams(location.search).get("project");
    if (named) { navigate("/projects?project=" + encodeURIComponent(named) + "&view=scans", { replace: true }); return; }
    const controller = new AbortController();
    action("/api/platform/projects", { signal: controller.signal }).then(
      ({ projects }) => navigate(projects.length ? "/projects?project=" + projects[0].id + "&view=scans" : "/projects", { replace: true }),
      () => {},
    );
    return () => controller.abort();
  }, [location.pathname, location.search, session.user]);
  useEffect(() => {
    // Reports belong to a project. A bare /reports opens the first project's reports.
    if (!/^\/reports\/?$/.test(location.pathname) || !session.user || new URLSearchParams(location.search).get("project")) return;
    const controller = new AbortController();
    action("/api/platform/projects", { signal: controller.signal }).then(
      ({ projects }) => navigate(projects.length ? "/reports?project=" + projects[0].id : "/projects", { replace: true }),
      () => {},
    );
    return () => controller.abort();
  }, [location.pathname, location.search, session.user]);
  useEffect(() => {
    // There is no separate Overview page: Projects is home.
    if (/^\/dashboard\/?$/.test(location.pathname) && session.user) navigate("/projects", { replace: true });
  }, [location.pathname, session.user]);
  useEffect(() => {
    if (landingPage && session.user && !location.hash) navigate("/projects", { replace: true });
  }, [landingPage, location.hash, session.user]);
  if (entryPage && session.user === null) return <Entry follow={follow} lang={lang} preferences={preferences} />;
  if (entryPage && session.user === undefined && !session.failure) return <p role="status" className="entry-loading">{t("جاري تحميل بصيرة…", "Loading Basira…")}</p>;
  return (
    <>
      <div className={signingInPage ? undefined : "workspace-layout"} dir={signingInPage ? undefined : lang === "ar" ? "rtl" : "ltr"}>
      {!signingInPage && <SiteHeader pathname={location.pathname} follow={follow} navigate={navigate} lang={lang} user={session.user}
        preferences={preferences} onLogout={() => { session.setUser(null); navigate("/", { replace: true }); }} />}
      <main ref={mainContent} id="main-content" tabIndex={-1} dir={lang === "ar" ? "rtl" : "ltr"}
        className={landingPage ? "site-landing-main" : "site-workspace-main"}>
        {productError ? <div role="alert"><p>{t("تعذّر تحميل إعدادات بصيرة.", "Basira settings could not be loaded.")}</p>
          <button className="btn" type="button" onClick={() => setProductAttempt((attempt) => attempt + 1)}>{t("إعادة المحاولة", "Retry")}</button></div>
          : !product ? <p role="status">{t("جاري تحميل بصيرة…", "Loading Basira…")}</p>
          : landingPage ? <Landing follow={follow} lang={lang} authenticated={Boolean(session.user)} />
          : reportsPage ? <Reports location={location} navigate={navigate} lang={lang} session={session} personal={personal} />
          : scansRedirect ? <p role="status">{t("جاري فتح الفحوصات…", "Opening scans…")}</p>
          : findingsPage ? <p role="status">{t("جاري فتح التقارير…", "Opening reports…")}</p>
          : projectsPage ? <Platform location={location} navigate={navigate} lang={lang} session={session}
            personal={personal} onProjectsChanged={() => setProjectRevision((revision) => revision + 1)}
            preferences={preferences} />
          : demoPage ? <p role="status">{t("جاري فتح مساحة العمل…", "Opening your workspace…")}</p>
          : <section className="card project-panel">
          <h1>{t("الصفحة غير موجودة", "Page not found")}</h1>
          <a href="/" onClick={(event) => follow(event, "/")}>{t("الصفحة الرئيسية", "Back to home")}</a>
        </section>}
      </main>
      </div>
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
