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
  History,
  LayoutDashboard,
  LoaderCircle,
  Play,
  Settings2,
  SlidersHorizontal,
  Waypoints,
  Workflow,
} from "lucide-react";
import "@fontsource/ibm-plex-sans-arabic/arabic-400.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-500.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-600.css";
import "@fontsource/ibm-plex-sans-arabic/arabic-700.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import {
  agents,
  labelOf,
  num,
  readRun,
  roleOf,
} from "./data";
import { Network, AgentIcon } from "./Network";
import { Agent, Modal, Settings } from "./Dialogs";
import { initialSource, SourcePicker, sourceError } from "./Source";
import { Reports } from "./Reports";
import { Platform } from "./Platform";
import { CheckCatalog } from "./CheckCatalog";
import "./style.css";

function currentLocation() {
  return { pathname: window.location.pathname, search: window.location.search };
}

function App() {
  const [location, setLocation] = useState(currentLocation);
  const reportsPage = /^\/reports(?:\/|$)/.test(location.pathname);
  const projectsPage = /^\/projects(?:\/|$)/.test(location.pathname);
  const catalogPage = location.pathname === "/checks";
  const [dialog, show] = useState(""),
    [source, setSource] = useState(initialSource),
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
  async function start() {
    if (lock.current || sourceBusy) return;
    const invalidSource = sourceError(source.text);
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
      <header className="header">
        <div className="navwrap">
          <button
            className="brand"
            onClick={() => navigate("/")}
            aria-label="مرصد، صفحة المختبر"
          >
            <img src="/mark.svg" alt="" />
            <span>
              مرصد<small>MARSAD</small>
            </span>
          </button>
          <div className="nav-divider" />
          <nav>
            <button
              className={!reportsPage && !projectsPage && !catalogPage ? "selected" : ""}
              aria-current={!reportsPage && !projectsPage && !catalogPage ? "page" : undefined}
              onClick={() => navigate("/")}
            >
              <LayoutDashboard />
              المختبر
            </button>
            <button
              className={reportsPage ? "selected" : ""}
              aria-current={reportsPage ? "page" : undefined}
              onClick={() => navigate("/reports")}
            >
              <History />
              سجل التقارير
            </button>
            <button className={projectsPage ? "selected" : ""} aria-current={projectsPage ? "page" : undefined}
              onClick={() => navigate("/projects")}>المشاريع</button>
          </nav>
          <button
            className="nav-settings"
            onClick={() => show("settings")}
            disabled={busy}
          >
            <Settings2 size={17} />
            <span>الإعدادات</span>
          </button>
        </div>
      </header>
      <main>
        {reportsPage ? (
          <Reports location={location} navigate={navigate} revision={latest?.id} />
        ) : projectsPage ? <Platform location={location} navigate={navigate} /> : catalogPage ? <CheckCatalog /> : (
          <>
            <div className="heading">
              <div>
                <div className="section-tag"><i /> AGENT WORKSPACE</div>
                <h1>مختبر الوكلاء</h1>
                <p>شغّل مراجعة أمنية لكود HTML وتابع تنفيذ الوكلاء لحظة بلحظة.</p>
              </div>
              <button
                className={"connection " + (config ? "connected" : "")}
                disabled={busy}
                onClick={() => show("settings")}
              >
                <i />
                {config ? "الموديل متصل" : "فحص محلي"}
                <ChevronLeft size={14} />
              </button>
            </div>
            <div className="desk">
              <section className="setup card">
                <div className="card-head">
                  <div className="title-icon">
                    <SlidersHorizontal size={18} />
                  </div>
                  <h2>إعداد الفحص</h2>
                </div>
                <p className="card-intro">اختار مصدر HTML للفحص. نموذج اللغة اختياري.</p>
                <SourcePicker source={source} setSource={setSource} disabled={busy} onBusyChange={setSourceBusy} />
                <div className="profile-setting">
                  <label htmlFor="scan-profile">نطاق الفحص</label>
                  <select id="scan-profile" value={profile} disabled={busy} onChange={(event) => setProfile(event.target.value)}>
                    <option value="extended">موسّع · ١٠٠ قاعدة في الكتالوج</option>
                    <option value="baseline">أساسي · ٣ قواعد HTML</option>
                  </select>
                  <a href="/checks" onClick={(event) => follow(event, "/checks")}>شوف القواعد والأدوات</a>
                  <small className="hint">التغطية الفعلية بتتحدد حسب نوع الملف ومحتواه.</small>
                </div>
                <div className="field-title">إثراء التقرير بالموديل</div>
                <button
                  className="option"
                  disabled={busy}
                  onClick={() => show("settings")}
                >
                  <span className="tile lilac">
                    <Cpu size={21} />
                  </span>
                  <span>
                    <strong dir="auto">{config?.model || "إضافة موديل اختياري"}</strong>
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
                  {busy ? "الفحص قيد التشغيل" : "تشغيل الفحص"}
                </button>
                {busy && (
                  <button className="subtle" onClick={() => controller.current?.abort()}>إلغاء الفحص</button>
                )}
              </section>
              <Network
                {...{ events, busy, error, expanded, setExpanded }}
                onAgent={setAgent}
              />
            </div>
            {error && (
              <div className="error" role="alert">
                <CircleAlert size={17} />
                {error}
              </div>
            )}
            {runState === "cancelled" && <p className="card-intro" role="status">تم إلغاء متابعة الفحص.</p>}
            <div className="results-heading">
              <h2>نتائج التشغيل</h2>
              {latest && (
                <a className="subtle" href={`/reports/${latest.id}`} onClick={(event) => follow(event, `/reports/${latest.id}`)}>
                  فتح التقرير <ArrowLeft size={15} />
                </a>
              )}
            </div>
            <div className="stats">
              {[
                [
                  Waypoints,
                  "الأدوار المكتملة",
                  num(roleCount) + " / " + num(5),
                ],
                [
                  ClipboardList,
                  "الملاحظات المؤكدة",
                  metrics ? num(latest.findings?.length || 0) : "—",
                ],
                [
                  Activity,
                  "استدعاءات الموديل",
                  metrics ? num(metrics.modelCalls ?? 0) : "—",
                ],
                [
                  Workflow,
                  "القواعد المنطبقة",
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
                العينة المرجعية · {num(metrics.benchmark.matched)} من{" "}
                {num(metrics.benchmark.expected)} مطابق ·{" "}
                {num(metrics.benchmark.unexpected)} إضافية
              </p>
            )}
            <div className="utility">
              <button onClick={() => show("agents")}>
                <Boxes size={15} />
                دليل الوكلاء
              </button>
              <button onClick={() => show("memory")}>
                <Database size={15} />
                الذاكرة
              </button>
              {events.length > 0 && (
                <button onClick={() => show("trace")}>
                  <Workflow size={15} />
                  تفاصيل التنفيذ
                </button>
              )}
            </div>
          </>
        )}
      </main>
      {dialog === "settings" && (
        <Settings config={config} save={setConfig} close={() => show("")} />
      )}
      {dialog === "agents" && (
        <Modal title="دليل الوكلاء" close={() => show("")}>
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
                  <strong>{a[0]}</strong>
                  <small>{a[1]}</small>
                </span>
                <ChevronLeft size={15} />
              </button>
            ))}
          </div>
        </Modal>
      )}
      {dialog === "memory" && (
        <Modal title="ذاكرة الوكلاء" close={() => show("")}>
          <dl className="spec">
            <dt>ذاكرة العمل</dt>
            <dd>
              حالة مشتركة داخل LangGraph بتنقل الخطة والملاحظات والقياسات بين
              الوكلاء أثناء الفحص.
            </dd>
            <dt>ذاكرة التشغيلات السابقة</dt>
            <dd>
              تُحفظ التقارير في قاعدة SQLite. المنسّق يستقبل إحصاءات محدودة من فحص
              سابق لنفس الجلسة عند توفرها.
            </dd>
            <dt>ذاكرة القواعد</dt>
            <dd>
              كتالوج الفحص بيحدّد قواعد السكربتات والنماذج المؤهلة للتحليل.
            </dd>
          </dl>
          <button
            className="btn"
            onClick={() => {
              show("");
              navigate("/reports");
            }}
          >
            عرض التقارير المحفوظة <ArrowLeft size={16} />
          </button>
        </Modal>
      )}
      {dialog === "trace" && (
        <Modal title="تفاصيل التنفيذ" close={() => show("")}>
          <ol className="trace">
            {events.map((e, i) => (
              <li key={i}>
                <b>{labelOf(e.node)}</b>
                <small>
                  {e.status === "done" ? "اكتمل" : "بدأ"}
                  {e.source && (e.source === "model" ? " · موديل" : " · محلي")}
                </small>
                <p dir="auto">{e.detail}</p>
              </li>
            ))}
          </ol>
        </Modal>
      )}
      {agent && (
        <Agent
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
