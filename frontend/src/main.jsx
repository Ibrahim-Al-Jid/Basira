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
import { Landing, OverviewSidebar } from "./Landing";
import { Entry } from "./Entry";
import { SiteHeader, readPreference, savePreference } from "./SiteHeader";
import { PersonalSidebar } from "./PersonalWorkspace";
import { action } from "./platformClient";
import "./style.css";
import "./workspace.css";
import "./design-variants.css";
import "./security-overview.css";
import "./command-center.css";
import "./command-light.css";
import "./entry.css";

const rippleControls = ".btn, .launch, .square, .site-icon, .command-search, .overview-primary, .reports-button, .signin-control, .signin-submit, .signin-secondary, .overview-chart-filters button, .report-language a";

function listenForButtonRipples() {
  const motion = window.matchMedia("(prefers-reduced-motion: reduce)");

  function ripple(event) {
    if (motion.matches || (event.type === "pointerdown" ? !event.isPrimary || event.button !== 0 : event.detail !== 0)) return;
    const control = event.target instanceof Element ? event.target.closest(rippleControls) : null;
    if (!control || control.matches(':disabled, [aria-disabled="true"]')) return;

    const bounds = control.getBoundingClientRect();
    const x = event.type === "pointerdown" ? event.clientX - bounds.left : bounds.width / 2;
    const y = event.type === "pointerdown" ? event.clientY - bounds.top : bounds.height / 2;
    const wave = document.createElement("i");
    wave.className = "button-ripple";
    wave.setAttribute("aria-hidden", "true");
    wave.style.setProperty("--ripple-x", x + "px");
    wave.style.setProperty("--ripple-y", y + "px");
    wave.style.setProperty("--ripple-radius", Math.hypot(Math.max(x, bounds.width - x), Math.max(y, bounds.height - y)) + "px");
    wave.addEventListener("animationend", () => wave.remove(), { once: true });
    wave.addEventListener("animationcancel", () => wave.remove(), { once: true });
    control.querySelector(":scope > .button-ripple")?.remove();
    control.append(wave);
  }

  document.addEventListener("pointerdown", ripple, true);
  document.addEventListener("click", ripple, true);
  return () => {
    document.removeEventListener("pointerdown", ripple, true);
    document.removeEventListener("click", ripple, true);
  };
}

function currentLocation() {
  return { pathname: window.location.pathname, search: window.location.search, hash: window.location.hash };
}

function App() {
  useEffect(listenForButtonRipples, []);
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
  const projectsPage = /^\/(?:projects(?:\/|$)|dashboard\/?$|scans\/?$|new-scan\/?$|settings\/?$|signin\/?$)/.test(location.pathname);
  const personalWorkspace = Boolean(personal && session.user && !landingPage);
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
    if (landingPage && session.user && !location.hash) navigate("/dashboard", { replace: true });
  }, [landingPage, location.hash, session.user]);
  if (entryPage && session.user === null) return <Entry follow={follow} lang={lang} preferences={preferences} />;
  if (entryPage && session.user === undefined && !session.failure) return <p role="status" className="entry-loading">{t("جاري تحميل بصيرة…", "Loading Basira…")}</p>;
  return (
    <>
      <div className={signingInPage ? undefined : "workspace-layout"} dir={signingInPage ? undefined : "ltr"}>
      {!signingInPage && <SiteHeader pathname={location.pathname} follow={follow} lang={lang} authenticated={Boolean(session.user)}
        preferences={preferences} />}
      {personalWorkspace && <PersonalSidebar key={session.user.id} location={location} navigate={navigate} lang={lang}
        follow={follow} revision={projectRevision} onLogout={() => { session.setUser(null); navigate("/", { replace: true }); }} />}
      {!signingInPage && !personalWorkspace && <OverviewSidebar lang={lang} follow={follow} location={location} />}
      <main ref={mainContent} id="main-content" tabIndex={-1} dir={lang === "ar" ? "rtl" : "ltr"}
        className={landingPage ? "site-landing-main" : "site-workspace-main"}>
        {productError ? <div role="alert"><p>{t("تعذّر تحميل إعدادات بصيرة.", "Basira settings could not be loaded.")}</p>
          <button className="btn" type="button" onClick={() => setProductAttempt((attempt) => attempt + 1)}>{t("إعادة المحاولة", "Retry")}</button></div>
          : !product ? <p role="status">{t("جاري تحميل بصيرة…", "Loading Basira…")}</p>
          : landingPage ? <Landing follow={follow} lang={lang} authenticated={Boolean(session.user)} />
          : reportsPage ? <Reports location={location} navigate={navigate} lang={lang} session={session} personal={personal} />
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
