import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowLeft,
  Boxes,
  ChevronLeft,
  CircleAlert,
  ClipboardList,
  Cpu,
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
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import {
  agents,
  num,
  readRun,
  roleOf,
} from "./data";
import { Network, AgentIcon, networkLabel } from "./Network";
import { Agent, Modal, Settings } from "./Dialogs";
import { emptySource, SourcePicker, sourceError } from "./Source";
import { Reports } from "./Reports";
import { Platform } from "./Platform";
import { CheckCatalog } from "./CheckCatalog";
import { Landing } from "./Landing";
import { SiteHeader, readPreference, savePreference } from "./SiteHeader";
import "./style.css";
import "./workspace.css";

function currentLocation() {
  return { pathname: window.location.pathname, search: window.location.search };
}

function App() {
  const [location, setLocation] = useState(currentLocation);
  const [lang, setLang] = useState(() => readPreference("language", "ar") === "en" ? "en" : "ar");
  const [theme, setTheme] = useState(() => readPreference("theme", "dark") === "light" ? "light" : "dark");
  const landingPage = location.pathname === "/";
  const demoPage = location.pathname === "/demo";
  const t = (ar, en) => lang === "en" ? en : ar;
  const mainContent = useRef(null);
  const initialPath = useRef(location.pathname);
  const findingsPage = location.pathname === "/findings";
  const reportsPage = /^\/reports(?:\/|$)/.test(location.pathname);
  const projectsPage = /^\/(?:projects(?:\/|$)|dashboard$|scans$|new-scan$|settings$|signin$)/.test(location.pathname);
  const reportLocale = new URLSearchParams(location.search).get("lang");
  const pageLanguage = (reportsPage || findingsPage) && ["ar", "en"].includes(reportLocale) ? reportLocale : lang;
  const catalogPage = location.pathname === "/checks";
  const [dialog, show] = useState(""),
    [source, setSource] = useState(emptySource),
    [sourceBusy, setSourceBusy] = useState(false),
    [config, setConfig] = useState(null),
    [profile, setProfile] = useState("extended");
  const [events, setEvents] = useState([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [runState, setRunState] = useState("idle");
  const [latest, setLatest] = useState(null),
    [agent, setAgent] = useState(null),
    [expanded, setExpanded] = useState(false),
    [runModel, setRunModel] = useState("");
  const lock = useRef(false),
    controller = useRef(null);

  function navigate(path, { replace = false } = {}) {
    const previousPath = window.location.pathname;
    const update = replace ? "replaceState" : "pushState";
    if (path !== previousPath + window.location.search) window.history[update](null, "", path);
    setLocation(currentLocation());
    if (window.location.pathname !== previousPath) window.scrollTo(0, 0);
  }

  function changeLanguage(next) {
    setLang(next);
    if (reportsPage || findingsPage) {
      const query = new URLSearchParams(location.search);
      query.set("lang", next);
      navigate(location.pathname + "?" + query, { replace: true });
    }
  }

  function follow(event, path) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    navigate(path);
  }

  useEffect(() => {
    const onPopState = () => setLocation(currentLocation());
    window.addEventListener("popstate", onPopState);
    return () => {
      window.removeEventListener("popstate", onPopState);
      controller.current?.abort();
    };
  }, []);
  useEffect(() => {
    function esc(e) {
      if (e.key === "Escape") setExpanded(false);
    }
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, []);
  useEffect(() => {
    const root = document.documentElement;
    root.lang = pageLanguage;
    root.dir = pageLanguage === "ar" ? "rtl" : "ltr";
    root.dataset.theme = theme;
    savePreference("language", lang);
    savePreference("theme", theme);
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#0b0f12" : "#f5f7f4");
  }, [lang, pageLanguage, theme]);
  useEffect(() => {
    document.title = landingPage ? "MARSAD | Web Security Workspace"
      : demoPage ? "MARSAD | Demo" : "MARSAD | Workspace";
  }, [landingPage, demoPage]);
  useEffect(() => {
    if (initialPath.current !== location.pathname) {
      initialPath.current = location.pathname;
      if (!reportsPage && !findingsPage) mainContent.current?.focus({ preventScroll: true });
    }
    if (demoPage && new URLSearchParams(location.search).get("settings") === "models") show("settings");
  }, [demoPage, reportsPage, findingsPage, location.pathname, location.search]);
  async function start() {
    if (lock.current || sourceBusy) return;
    const invalidSource = sourceError(source.text, lang);
    if (invalidSource) {
      setError(invalidSource);
      return;
    }
    lock.current = true;
    controller.current = new AbortController();
    setRunModel(config?.model || "");
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
          ...(config && { key: config.key, model: config.model, allow_paid: config.paid }),
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
  return (
    <>
      <SiteHeader pathname={location.pathname} follow={follow} lang={pageLanguage} setLang={changeLanguage}
        theme={theme} setTheme={setTheme} publicPage={landingPage || demoPage || catalogPage} />
      <main ref={mainContent} id="main-content" tabIndex={-1} className={landingPage ? "site-landing-main" : "site-workspace-main"}>
        {landingPage ? <Landing follow={follow} lang={lang} theme={theme} />
          : reportsPage || findingsPage ? <Reports location={location} navigate={navigate} revision={latest?.id} lang={lang} />
          : projectsPage ? <Platform location={location} navigate={navigate} lang={lang} />
          : catalogPage ? <CheckCatalog lang={lang} /> : (
          <>
            <div className="heading">
              <div>

                <h1>{t("مختبر الوكلاء", "Agent demo")}</h1>
                <p>{t("شغّل مراجعة أمنية لكود HTML وتابع تنفيذ الوكلاء لحظة بلحظة.", "Review a supplied HTML file and follow each step.")}</p>
              </div>
              <button
                className={"connection " + (config ? "connected" : "")}
                disabled={busy}
                onClick={() => show("settings")}
              >
                <i />
                {config ? t("الموديل متصل", "Model connected") : t("فحص محلي", "Local scan")}
                <ChevronLeft size={14} />
              </button>
            </div>
            <div className="desk">
              <section className="setup card">
                <div className="card-head">
                  <div className="title-icon">
                    <SlidersHorizontal size={18} />
                  </div>
                  <h2>{t("إعداد الفحص", "Scan setup")}</h2>
                </div>
                <p className="card-intro">{t("اختار مصدر HTML للفحص. نموذج اللغة اختياري.", "Choose an HTML source. Model enrichment is optional.")}</p>
                <SourcePicker source={source} setSource={setSource} disabled={busy} onBusyChange={setSourceBusy} lang={lang} />
                <div className="profile-setting">
                  <label htmlFor="scan-profile">{t("نطاق الفحص", "Scan profile")}</label>
                  <select id="scan-profile" value={profile} disabled={busy} onChange={(event) => setProfile(event.target.value)}>
                    <option value="extended">{t("موسّع · ١٠٠ قاعدة في الكتالوج", "Extended · 100 rules in the catalog")}</option>
                    <option value="baseline">{t("أساسي · ٣ قواعد HTML", "Baseline · 3 HTML rules")}</option>
                  </select>
                  <a href="/checks" onClick={(event) => follow(event, "/checks")}>{t("شوف القواعد والأدوات", "Explore the rule catalog")}</a>
                  <small className="hint">{t("التغطية الفعلية بتتحدد حسب نوع الملف ومحتواه.", "Coverage depends on the evidence in your file.")}</small>
                </div>
                <div className="field-title">{t("إثراء التقرير بالموديل", "Model enrichment")}</div>
                <button
                  className="option"
                  disabled={busy}
                  onClick={() => show("settings")}
                >
                  <span className="tile lilac">
                    <Cpu size={21} />
                  </span>
                  <span>
                    <strong dir="auto">{config?.model || t("إضافة موديل اختياري", "Add an optional model")}</strong>
                    <small dir="ltr">OpenRouter</small>
                  </span>
                  <ChevronLeft size={16} />
                </button>
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
        )}
      </main>
      {dialog === "settings" && (
        <Settings lang={lang} config={config} save={setConfig} close={() => show("")} />
      )}
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
              {t("تُحفظ التقارير في قاعدة SQLite. المنسّق يستقبل إحصاءات محدودة من فحص               سابق لنفس الجلسة عند توفرها.", "SQLite stores reports. The orchestrator can use limited statistics from a prior scan in the same session.")}
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
          model={events.length ? runModel : config?.model}
          tasks={latest?.task_runs?.filter((task) => task.agent === roleOf(agent))}
          close={() => setAgent(null)}
        />
      )}
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
