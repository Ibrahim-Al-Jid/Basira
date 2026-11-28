import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowLeft,
  Boxes,
  ChevronLeft,
  CircleAlert,
  ClipboardList,
  Database,
  LoaderCircle,
  Play,
  SlidersHorizontal,
  Waypoints,
  Workflow,
} from "lucide-react";
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
import {
  agents,
  num,
  readRun,
  roleOf,
} from "./data";
import { Network, AgentIcon, networkLabel } from "./Network";
import { Agent, Modal } from "./Dialogs";
import { emptySource, SourcePicker, sourceError } from "./Source";
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
  const demoPage = product && !personal && /^\/demo\/?$/.test(location.pathname);
  const session = usePlatformSession();
  const t = (ar, en) => lang === "en" ? en : ar;
  const mainContent = useRef(null);
  const initialPath = useRef(location.pathname);
  const findingsPage = /^\/findings\/?$/.test(location.pathname);
  const reportsPage = /^\/reports(?:\/|$)/.test(location.pathname);
  const projectsPage = /^\/(?:projects(?:\/|$)|dashboard\/?$|scans\/?$|new-scan\/?$|settings\/?$|signin\/?$)/.test(location.pathname);
  const personalWorkspace = Boolean(personal && session.user && !landingPage);
  const [dialog, show] = useState(""),
    [source, setSource] = useState(emptySource),
    [sourceBusy, setSourceBusy] = useState(false),
    [profile, setProfile] = useState("extended");
  const [events, setEvents] = useState([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [runState, setRunState] = useState("idle");
  const [latest, setLatest] = useState(null),
    [agent, setAgent] = useState(null),
    [expanded, setExpanded] = useState(false);
  const lock = useRef(false),
    controller = useRef(null);

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
      controller.current?.abort();
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
    function esc(e) {
      if (e.key === "Escape") setExpanded(false);
    }
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, []);
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
      : demoPage ? "BASIRA | Demo" : "BASIRA | Workspace";
  }, [entryPage, landingPage, demoPage, lang]);
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
    if (landingPage && session.user && !location.hash) navigate("/dashboard", { replace: true });
  }, [landingPage, location.hash, session.user]);
  async function start() {
    if (lock.current || sourceBusy) return;
    const invalidSource = sourceError(source.text, lang);
    if (invalidSource) {
      setError(invalidSource);
      return;
    }
    lock.current = true;
    controller.current = new AbortController();
    setBusy(true);
    setRunState("running");
    setError("");
    setEvents([]);
    setLatest(null);
    try {
      await readRun(
        {
          source: source.text,
          profile,
          source_info: { kind: source.kind, name: source.name },
        },
        (e) => {
          if (e.type === "step") setEvents((prev) => [...prev, e]);
          if (e.type === "complete") {
            setLatest(e.report);
            setRunState("completed");
          }
        },
        controller.current.signal,
      );
    } catch (err) {
      if (err.name === "AbortError") {
        setRunState("cancelled");
      } else {
        setError(err.message);
        setRunState("failed");
      }
    } finally {
      lock.current = false;
      controller.current = null;
      setBusy(false);
    }
  }
  const roleCount = new Set(
      events.filter((e) => e.status === "done").map((e) => roleOf(e.node)),
    ).size,
    metrics = latest?.metrics;
  if (entryPage && session.user === null) return <Entry follow={follow} lang={lang} preferences={preferences} />;
  if (entryPage && session.user === undefined && !session.failure) return <p role="status" className="entry-loading">{t("جاري تحميل بصيرة…", "Loading Basira…")}</p>;
  return (
    <>
      <div className={signingInPage ? undefined : "workspace-layout"} dir={signingInPage ? undefined : "ltr"}>
      {!signingInPage && <SiteHeader pathname={location.pathname} follow={follow} lang={lang} authenticated={Boolean(session.user)}
        preferences={preferences} />}
      {personalWorkspace && <PersonalSidebar key={session.user.id} location={location} navigate={navigate} lang={lang}
        follow={follow} revision={projectRevision} onLogout={() => { session.setUser(null); navigate("/", { replace: true }); }} />}
      {!signingInPage && !personalWorkspace && <OverviewSidebar lang={lang} follow={follow} location={location} personal={personal} />}
      <main ref={mainContent} id="main-content" tabIndex={-1} dir={lang === "ar" ? "rtl" : "ltr"}
        className={landingPage ? "site-landing-main" : "site-workspace-main"}>
        {productError ? <div role="alert"><p>{t("تعذّر تحميل إعدادات بصيرة.", "Basira settings could not be loaded.")}</p>
          <button className="btn" type="button" onClick={() => setProductAttempt((attempt) => attempt + 1)}>{t("إعادة المحاولة", "Retry")}</button></div>
          : !product ? <p role="status">{t("جاري تحميل بصيرة…", "Loading Basira…")}</p>
          : landingPage ? <Landing follow={follow} lang={lang} authenticated={Boolean(session.user)} personal={personal} />
          : reportsPage ? <Reports location={location} navigate={navigate} revision={latest?.id} lang={lang} session={session} personal={personal} />
          : findingsPage ? <p role="status">{t("جاري فتح التقارير…", "Opening reports…")}</p>
          : projectsPage ? <Platform location={location} navigate={navigate} lang={lang} session={session}
            personal={personal} onProjectsChanged={() => setProjectRevision((revision) => revision + 1)}
            preferences={preferences} />
          : demoPage ? (
          <>
            <div className="heading">
              <div>

                <h1>{t("مختبر الوكلاء", "Agent demo")}</h1>
                <p>{t("شغّل مراجعة أمنية لكود HTML وتابع تنفيذ الوكلاء لحظة بلحظة.", "Review a supplied HTML file and follow each step.")}</p>
              </div>
            </div>
            <div className="desk">
              <section className="setup card">
                <div className="card-head">
                  <div className="title-icon">
                    <SlidersHorizontal size={18} />
                  </div>
                  <h2>{t("إعداد الفحص", "Scan setup")}</h2>
                </div>
                <p className="card-intro">{t("اختار مصدر HTML للفحص المحلي.", "Choose an HTML source for a local scan.")}</p>
                <SourcePicker source={source} setSource={setSource} disabled={busy} onBusyChange={setSourceBusy} lang={lang} />
                <div className="profile-setting">
                  <label htmlFor="scan-profile">{t("نطاق الفحص", "Scan profile")}</label>
                  <select id="scan-profile" value={profile} disabled={busy} onChange={(event) => setProfile(event.target.value)}>
                    <option value="extended">{t("موسّع · ١١٤ قاعدة", "Extended · 114 rules")}</option>
                    <option value="baseline">{t("أساسي · ٣ قواعد HTML", "Baseline · 3 HTML rules")}</option>
                  </select>
                  <small className="hint">{t("التغطية الفعلية بتتحدد حسب نوع الملف ومحتواه.", "Coverage depends on the evidence in your file.")}</small>
                </div>
                <button className="launch" disabled={busy || sourceBusy || !source.text.trim()} onClick={start}>
                  {busy ? (
                    <LoaderCircle size={17} className="spin" />
                  ) : (
                    <Play size={16} fill="currentColor" />
                  )}
                  {busy ? t("الفحص قيد التشغيل", "Scan running") : t("تشغيل الفحص", "Run scan")}
                </button>
                {busy && (
                  <button className="subtle" onClick={() => controller.current?.abort()}>{t("إلغاء الفحص", "Cancel scan")}</button>
                )}
              </section>
              <Network
                {...{ events, busy, error, expanded, setExpanded }}
                onAgent={setAgent} lang={lang}
              />
            </div>
            {error && (
              <div className="error" role="alert">
                <CircleAlert size={17} />
                {error}
              </div>
            )}
            {runState === "cancelled" && <p className="card-intro" role="status">{t("تم إلغاء متابعة الفحص.", "Scan cancelled.")}</p>}
            <div className="results-heading">
              <h2>{t("نتائج التشغيل", "Scan results")}</h2>
              {latest && (
                <a className="subtle" href={`/reports/${latest.id}?scope=demo`} onClick={(event) => follow(event, `/reports/${latest.id}?scope=demo`)}>
                  {t("فتح التقرير", "Open report")} <ArrowLeft size={15} />
                </a>
              )}
            </div>
            <div className="stats">
              {[
                [
                  Waypoints,
                  t("الأدوار المكتملة", "Roles completed"),
                  num(roleCount) + " / " + num(5),
                ],
                [
                  ClipboardList,
                  t("الأدلة المرصودة", "Evidence observed"),
                  metrics ? num(latest.findings?.length || 0) : "—",
                ],
                [
                  Activity,
                  t("استدعاءات الموديل", "Model calls"),
                  metrics ? num(metrics.modelCalls ?? 0) : "—",
                ],
                [
                  Workflow,
                  t("القواعد المنطبقة", "Applicable rules"),
                  latest?.coverage ? num(metrics.checksRun || 0) + " / " + num(latest.coverage.length) : "—",
                ],
              ].map(([Icon, title, value], i) => (
                <div key={title} className="stat card">
                  <span className={"stat-icon t" + i}>
                    <Icon size={20} />
                  </span>
                  <div>
                    <small>{title}</small>
                    <strong dir="ltr">{value}</strong>
                  </div>
                </div>
              ))}
            </div>
            {metrics?.benchmark && (
              <p className="benchmark">
                {t("العينة المرجعية", "Reference fixture")} · {num(metrics.benchmark.matched)} / {num(metrics.benchmark.expected)} {t("مطابق", "matched")} · {num(metrics.benchmark.unexpected)} {t("إضافية", "unexpected")}
              </p>
            )}
            <div className="utility">
              <button onClick={() => show("agents")}>
                <Boxes size={15} />
                {t("دليل الوكلاء", "Agent guide")}
              </button>
              <button onClick={() => show("memory")}>
                <Database size={15} />
                {t("الذاكرة", "Memory")}
              </button>
              {events.length > 0 && (
                <button onClick={() => show("trace")}>
                  <Workflow size={15} />
                  {t("تفاصيل التنفيذ", "Execution details")}
                </button>
              )}
            </div>
          </>
        ) : <section className="card project-panel">
          <h1>{t("الصفحة غير موجودة", "Page not found")}</h1>
          <a href="/" onClick={(event) => follow(event, "/")}>{t("الصفحة الرئيسية", "Back to home")}</a>
        </section>}
      </main>
      </div>
      {dialog === "agents" && (
        <Modal lang={lang} title={t("دليل الوكلاء", "Agent guide")} close={() => show("")}>
          <div className="agent-list">
            {Object.entries(agents).map(([id, a]) => (
              <button
                key={id}
                onClick={() => {
                  show("");
                  setAgent(id);
                }}
              >
                <span className="tile lilac">
                  <AgentIcon role={id} />
                </span>
                <span>
                  <strong>{t(a[0], a[1])}</strong>
                  {lang === "ar" && <small>{a[1]}</small>}
                </span>
                <ChevronLeft size={15} />
              </button>
            ))}
          </div>
        </Modal>
      )}
      {dialog === "memory" && (
        <Modal lang={lang} title={t("ذاكرة الوكلاء", "Agent memory")} close={() => show("")}>
          <dl className="spec">
            <dt>{t("ذاكرة العمل", "Working memory")}</dt>
            <dd>
              {t("حالة مشتركة داخل LangGraph بتنقل الخطة والملاحظات والقياسات بين               الوكلاء أثناء الفحص.", "A shared LangGraph state carries the plan, observations and measurements during a scan.")}
            </dd>
            <dt>{t("ذاكرة التشغيلات السابقة", "Run history")}</dt>
            <dd>
              {t("تُحفظ التقارير في قاعدة SQLite. المايسترو يستقبل إحصاءات محدودة من فحص               سابق لنفس الجلسة عند توفرها.", "SQLite stores reports. The orchestrator can use limited statistics from a prior scan in the same session.")}
            </dd>
            <dt>{t("ذاكرة القواعد", "Rule catalog")}</dt>
            <dd>
              {t("كتالوج الفحص بيحدّد قواعد السكربتات والنماذج المؤهلة للتحليل.", "The catalog identifies checks that may apply to the file.")}
            </dd>
          </dl>
          <button
            className="btn"
            onClick={() => {
              show("");
              navigate("/reports?scope=demo");
            }}
          >
            {t("عرض التقارير المحفوظة", "Open saved reports")} <ArrowLeft size={16} />
          </button>
        </Modal>
      )}
      {dialog === "trace" && (
        <Modal lang={lang} title={t("تفاصيل التنفيذ", "Execution details")} close={() => show("")}>
          <ol className="trace">
            {events.map((e, i) => (
              <li key={i}>
                <b>{networkLabel(e.node, lang)}</b>
                <small>
                  {e.status === "done" ? t("اكتمل", "Finished") : t("بدأ", "Started")}
                  {e.source && (e.source === "model" ? t(" · موديل", " · Model") : t(" · محلي", " · Local"))}
                </small>
                <p dir="auto">{lang === "en" ? e.detail_en || e.detail : e.detail}</p>
              </li>
            ))}
          </ol>
        </Modal>
      )}
      {agent && (
        <Agent
          lang={lang}
          node={agent}
          event={events.filter((e) => e.node === agent).at(-1)}
          tasks={latest?.task_runs?.filter((task) => task.agent === roleOf(agent))}
          close={() => setAgent(null)}
        />
      )}
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
