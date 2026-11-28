import React, { useEffect, useRef } from "react";
import { Activity, ChartNoAxesCombined, Check, CircleAlert, ScanLine, ShieldCheck, Workflow } from "lucide-react";
import { agents } from "./data";
import { AgentIcon } from "./Network";

const severity = [
  ["high", "عالية", "High"],
  ["medium", "متوسطة", "Medium"],
  ["low", "منخفضة", "Low"],
];

const roles = [
  ["orchestrator", "Review routing"],
  ["planning", "Selects the applicable checks"],
  ["analysis", "Examines evidence by branch"],
  ["validation", "Verifies findings"],
  ["reporting", "Summarizes repair priorities"],
];
const previewProgress = { analysis: 100, validation: 80, reporting: 60 };

function Sparkline({ points }) {
  if (!points || points.length < 2) return null;
  const top = Math.max(0, ...points);
  const bottom = Math.min(0, ...points);
  const line = points.map((point, index) => {
    const x = index * 120 / (points.length - 1);
    const y = 30 - (point - bottom) * 27 / (top - bottom || 1);
    return x + "," + y;
  }).join(" ");
  return <svg className="command-sparkline" viewBox="0 0 120 34" preserveAspectRatio="none" aria-hidden="true">
    <polygon points={"0,34 " + line + " 120,34"} fill="currentColor" opacity=".14" />
    <polyline points={line} fill="none" stroke="currentColor" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
  </svg>;
}

export function CommandMetrics({ metrics }) {
  return <ul className="command-metrics">
    {metrics.map(({ icon: Icon, label, value, detail, tone, points, testId }) => (
      <li className="overview-card command-metric" key={label} data-tone={tone}>
        <span className="command-icon"><Icon size={22} aria-hidden="true" /></span>
        <div><p>{label}</p><strong data-testid={testId}>{value}</strong>{detail && <small>{detail}</small>}</div>
        <Sparkline points={points} />
      </li>
    ))}
  </ul>;
}

export function CoverageGauge({ t, number, cover, example, children }) {
  const percentage = cover?.total > 0 ? Math.round(cover.ran * 100 / cover.total) : null;
  return <section className="overview-card command-panel">
    <header className="command-panel-head"><h2><ShieldCheck size={19} aria-hidden="true" />{t("تغطية الفحص", "Review coverage")}</h2>
      {example && <span className="overview-pill">{t("مثال", "Example")}</span>}
    </header>
    <div className="command-gauge">
      <div className="command-gauge-ring" aria-hidden="true" style={{ "--gauge-fill": (percentage ?? 0) * 2.7 + "deg" }} />
      <div className="command-ring-value"><strong>{percentage === null ? "—" : number(percentage) + "%"}</strong>
        <span data-testid={example ? undefined : "dash-coverage"}>
          {cover ? t(number(cover.ran) + " من " + number(cover.total), number(cover.ran) + " of " + number(cover.total)) : t("مفيش بيانات", "No data yet")}
        </span>
      </div>
    </div>
    <p className="command-panel-note">{t("نسبة القواعد اللي اتفحصت من إجمالي القواعد.", "Share of rules evaluated in the scan.")}</p>
    {children}
  </section>;
}

export function RiskDistribution({ t, number, counts, example, children }) {
  const total = severity.reduce((sum, [id]) => sum + (counts?.[id] ?? 0), 0);
  let cumulative = 0;
  const segments = severity.flatMap(([id]) => {
    const value = counts?.[id] ?? 0;
    if (!value || !total) return [];
    const start = cumulative;
    cumulative += value;
    return ["var(--risk-" + id + ") " + start * 100 / total + "% " + cumulative * 100 / total + "%"];
  });
  return <section className="overview-card command-panel">
    <header className="command-panel-head"><h2><ChartNoAxesCombined size={19} aria-hidden="true" />{t("توزيع النتائج", "Findings distribution")}</h2>
      {example && <span className="overview-pill">{t("مثال", "Example")}</span>}
    </header>
    <div className="command-risk-content">
      <div className="command-donut" style={segments.length ? { "--donut-fill": "conic-gradient(" + segments.join(", ") + ")" } : undefined}>
        <div className="command-ring-value"><strong>{counts ? number(total) : "—"}</strong><span>{t("إجمالي", "Total")}</span></div>
      </div>
      <ul className="command-risk-legend">
        {severity.map(([id, ar, en]) => {
          const count = counts?.[id] ?? 0;
          const percent = total ? number(Math.round(count * 1000 / total) / 10) + "%" : "—";
          return <li key={id} data-level={id} title={counts ? number(count) : undefined}>
            <span>{t(ar, en)}</span><strong data-testid={example ? undefined : "dash-" + id}>{example ? percent : counts ? number(count) : "—"}</strong>
          </li>;
        })}
      </ul>
    </div>
    {children}
  </section>;
}

export function ReviewAgents({ lang, t, scanHref, scanState, overview = false }) {
  const panel = useRef(null);
  const status = {
    running: t("قيد التنفيذ", "Running"), queued: t("في الانتظار", "Queued"),
    completed: t("مكتمل", "Completed"), partial: t("جزئي", "Partial"),
    failed: t("فشل", "Failed"), cancelled: t("أُلغي", "Cancelled"),
  }[scanState];
  useEffect(() => {
    if (location.hash === "#agents") panel.current?.scrollIntoView({ block: "start" });
  }, []);
  return <section ref={panel} className="overview-card command-panel" id="agents">
    <header className="command-panel-head">
      <h2><Workflow size={19} aria-hidden="true" />{t("فريق المراجعة", "Review agents")}</h2>
      {status && <span className="workspace-badge" data-state={scanState}>{status}</span>}
    </header>
    <ul className="command-agents">
      {roles.filter(([id]) => !overview || ["analysis", "validation", "reporting"].includes(id)).map(([id, detail]) => (
        <li key={id}><span className="command-icon"><AgentIcon role={id} size={19} /></span>
          <div><strong>{agents[id][lang === "ar" ? 0 : 1]}</strong><small>{lang === "ar" ? agents[id][3] : detail}</small>
            {overview && <div className="command-agent-progress">
              <progress max="100" value={previewProgress[id]} aria-label={t("تقدّم في المثال", "Example progress")} />
              <span>{new Intl.NumberFormat(lang, { style: "percent" }).format(previewProgress[id] / 100)}</span>
            </div>}
          </div>
        </li>
      ))}
    </ul>
    {scanHref && <a className="overview-text-link" href={scanHref}>{t("افتحي حالة الفحص", "Open scan status")}</a>}
    {overview && <a className="overview-text-link" href="#workflow">{t("شوفي مسار المراجعة", "See the review workflow")}</a>}
  </section>;
}

export function CommandActivity({ t, events, historyHref }) {
  return <section className="overview-card command-panel command-activity">
    <header className="command-panel-head">
      <h2>{t("آخر النشاط", "Recent activity")}</h2>
      <a href={historyHref}>{t("عرض الكل", "View all")}</a>
    </header>
    {events.length ? <ul>
      {events.map(({ id, title, detail, href, state }) => {
        const Icon = state === "completed" ? Check : state === "failed" ? CircleAlert : state === "running" ? ScanLine : Activity;
        const content = <><span className="command-activity-icon"><Icon size={18} aria-hidden="true" /></span>
          <span><strong>{title}</strong><small>{detail}</small></span></>;
        return <li key={id} data-state={state}>{href ? <a href={href}>{content}</a> : <div>{content}</div>}</li>;
      })}
    </ul> : <p className="command-panel-note">{t("النشاط هيظهر بعد أول فحص.", "Activity appears after the first scan.")}</p>}
  </section>;
}

