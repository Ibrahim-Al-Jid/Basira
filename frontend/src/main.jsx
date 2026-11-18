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
  FileCode2,
  FileText,
  FolderClock,
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
  dateText,
  fetchJson,
  labelOf,
  num,
  readRun,
  roleOf,
  sample,
} from "./data";
import { Network, AgentIcon } from "./Network";
import { Agent, Modal, Report, Settings, Source } from "./Dialogs";
import "./style.css";

function App() {
  const [page, go] = useState("lab"),
    [dialog, show] = useState(""),
    [source, setSource] = useState(sample),
    [config, setConfig] = useState(null);
  const [events, setEvents] = useState([]),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [history, setHistory] = useState([]),
    [historyError, setHistoryError] = useState("");
  const [latest, setLatest] = useState(null),
    [report, setReport] = useState(null),
    [agent, setAgent] = useState(null),
    [expanded, setExpanded] = useState(false),
    [runModel, setRunModel] = useState("");
  const lock = useRef(false),
    controller = useRef(null);
  async function refreshHistory() {
    try {
      setHistory((await fetchJson("/api/history")).reports || []);
      setHistoryError("");
    } catch (err) {
      setHistoryError(err.message);
    }
  }
  useEffect(() => {
    refreshHistory();
    return () => controller.current?.abort();
  }, []);
  useEffect(() => {
    function esc(e) {
      if (e.key === "Escape") setExpanded(false);
    }
    document.addEventListener("keydown", esc);
    return () => document.removeEventListener("keydown", esc);
  }, []);
  async function start() {
    if (lock.current) return;
    if (!config) {
      show("settings");
      return;
    }
    lock.current = true;
    controller.current = new AbortController();
    setRunModel(config.model);
    setBusy(true);
    setError("");
    setEvents([]);
    setLatest(null);
    try {
      await readRun(
        {
          source,
          key: config.key,
          model: config.model,
          allow_paid: config.paid,
        },
        (e) => {
          if (e.type === "step") setEvents((prev) => [...prev, e]);
          if (e.type === "complete") {
            setLatest(e.report);
            refreshHistory();
          }
        },
        controller.current.signal,
      );
    } catch (err) {
      if (err.name !== "AbortError") setError(err.message);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  async function openReport(id) {
    try {
      setReport(await fetchJson("/api/reports/" + encodeURIComponent(id)));
      setHistoryError("");
    } catch (err) {
      setHistoryError(err.message);
    }
  }
  const roleCount = new Set(
      events.filter((e) => e.status === "done").map((e) => roleOf(e.node)),
    ).size,
    metrics = latest?.metrics;
  const historyList = (
    <>
      {historyError && (
        <p className="error" role="alert">
          {historyError}{" "}
          <button className="subtle" onClick={refreshHistory}>
            إعادة المحاولة
          </button>
        </p>
      )}
      {history.map((h) => (
        <button
          key={h.id}
          className="history-row"
          onClick={() => openReport(h.id)}
        >
          <span className="tile pale">
            <FileText size={19} />
          </span>
          <span>
            <strong>تقرير فحص HTML</strong>
            <small>
              {dateText(h.created_at)} · {num(h.finding_count || 0)} ملاحظات
            </small>
          </span>
          <small className="history-model" dir="ltr">
            {h.model}
          </small>
          <ChevronLeft size={16} />
        </button>
      ))}
      {!history.length && !historyError && (
        <div className="no-history">
          <FolderClock size={31} />
          <strong>لسه مفيش تقارير محفوظة</strong>
          <p>
            بعد اكتمال الفحص، هتلاقي التقرير هنا بنسختيه العربية والإنجليزية.
          </p>
        </div>
      )}
    </>
  );
  return (
    <>
      <header className="header">
        <div className="navwrap">
          <button
            className="brand"
            onClick={() => go("lab")}
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
              className={page === "lab" ? "selected" : ""}
              onClick={() => go("lab")}
            >
              <LayoutDashboard />
              المختبر
            </button>
            <button
              className={page === "history" ? "selected" : ""}
              onClick={() => {
                go("history");
                refreshHistory();
              }}
            >
              <History />
              سجل التقارير
            </button>
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
        <div className="heading">
          <div>
            <div className="section-tag">
              <i />
              {page === "lab" ? "AGENT WORKSPACE" : "REPORT ARCHIVE"}
            </div>
            <h1>{page === "lab" ? "مختبر الوكلاء" : "سجل التقارير"}</h1>
            <p>
              {page === "lab"
                ? "شغّل مراجعة أمنية لكود HTML وتابع قرارات الوكلاء لحظة بلحظة."
                : "ارجع لنتائج الفحوصات السابقة ونزّل التقرير باللغة المناسبة."}
            </p>
          </div>
          <button
            className={"connection " + (config ? "connected" : "")}
            disabled={busy}
            onClick={() => show("settings")}
          >
            <i />
            {config ? "الموديل متصل" : "الموديل غير متصل"}
            <ChevronLeft size={14} />
          </button>
        </div>
        {page === "lab" ? (
          <>
            <div className="desk">
              <section className="setup card">
                <div className="card-head">
                  <div className="title-icon">
                    <SlidersHorizontal size={18} />
                  </div>
                  <h2>إعداد الفحص</h2>
                </div>
                <p className="card-intro">حدّد المصدر والموديل لبدء التشغيل.</p>
                <div className="field-title">مصدر المراجعة</div>
                <button
                  className="option"
                  disabled={busy}
                  onClick={() => show("source")}
                >
                  <span className="tile pale">
                    <FileCode2 size={21} />
                  </span>
                  <span>
                    <strong>
                      {source === sample
                        ? "عينة المتجر التجريبية"
                        : "كود HTML مخصّص"}
                    </strong>
                    <small>{num(source.split("\n").length)} سطر · HTML</small>
                  </span>
                  <ChevronLeft size={16} />
                </button>
                <div className="field-title">نموذج اللغة</div>
                <button
                  className="option"
                  disabled={busy}
                  onClick={() => show("settings")}
                >
                  <span className="tile lilac">
                    <Cpu size={21} />
                  </span>
                  <span>
                    <strong dir="auto">{config?.model || "اختار موديل"}</strong>
                    <small dir="ltr">OpenRouter</small>
                  </span>
                  <ChevronLeft size={16} />
                </button>
                <button className="launch" disabled={busy} onClick={start}>
                  {busy ? (
                    <LoaderCircle size={17} className="spin" />
                  ) : (
                    <Play size={16} fill="currentColor" />
                  )}
                  {busy ? "الفحص قيد التشغيل" : "تشغيل الفحص"}
                </button>
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
            <div className="results-heading">
              <h2>نتائج التشغيل</h2>
              {latest && (
                <button className="subtle" onClick={() => setReport(latest)}>
                  فتح التقرير <ArrowLeft size={15} />
                </button>
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
        ) : (
          <section className="card archive">{historyList}</section>
        )}
      </main>
      {dialog === "settings" && (
        <Settings config={config} save={setConfig} close={() => show("")} />
      )}
      {dialog === "source" && (
        <Source source={source} setSource={setSource} close={() => show("")} />
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
              go("history");
              refreshHistory();
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
                <small>{e.status === "done" ? "اكتمل" : "بدأ"}</small>
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
          model={runModel || config?.model}
          close={() => setAgent(null)}
        />
      )}
      {report && <Report report={report} close={() => setReport(null)} />}
    </>
  );
}
createRoot(document.getElementById("root")).render(<App />);
