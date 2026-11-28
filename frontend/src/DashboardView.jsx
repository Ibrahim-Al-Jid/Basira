import React, { useEffect, useState } from "react";
import { Activity, Bug, Folder, Maximize2, Minimize2, ScanLine, TriangleAlert } from "lucide-react";
import { action, errorText } from "./platformClient";
import { barHeights, changeView, coverageText } from "./dashboard";
import { CommandActivity, CommandMetrics, CoverageGauge, ReviewAgents, RiskDistribution } from "./CommandOverview";
import "./dashboard.css";

export default function DashboardView({ path, projectId, t, lang, reportLink, activity, projectCount, projectScans, activityEvents }) {
  const [state, setState] = useState({ loading: true });
  const [presenting, setPresenting] = useState(false);
  const [showRecent, setShowRecent] = useState(false);
  const [retry, setRetry] = useState(0);
  const locale = lang === "ar" ? "ar-EG" : "en";
  const num = (value) => Number(value).toLocaleString(locale);
  const when = (value) => new Date(value).toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });

  useEffect(() => {
    if (!path) return undefined;
    const controller = new AbortController();
    setState({ loading: true });
    action(path + "/dashboard", { signal: controller.signal }).then(
      (data) => { if (!controller.signal.aborted) setState({ data }); },
      (error) => { if (!controller.signal.aborted) setState({ error: errorText(error, t) }); },
    );
    return () => controller.abort();
  }, [path, retry]);
  useEffect(() => {
    if (!presenting) return undefined;
    const close = (event) => { if (event.key === "Escape") setPresenting(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [presenting]);

  if (path && state.loading) return <><p role="status">{t("بنحمّل الأرقام…", "Loading the numbers…")}</p>{activity}</>;
  if (path && state.error) return <><p className="workspace-error" role="alert">{state.error}{" "}
    <button className="btn" onClick={() => setRetry((value) => value + 1)}>{t("إعادة المحاولة", "Retry")}</button></p>{activity}</>;

  const { latest, scans = [], as_of } = state.data ?? {};
  const displayedScans = showRecent ? scans.slice(-5) : scans;
  const heights = barHeights(displayedScans);
  const cover = coverageText(latest?.coverage);
  const change = changeView(latest?.change);
  const currentScan = projectScans?.find(({ state }) => state === "running" || state === "queued") ?? projectScans?.[0];
  const activeCount = projectScans?.filter(({ state }) => state === "running" || state === "queued").length;
  const source = latest && <a className="dash-source" href={reportLink(projectId, latest.scan_id)}>
    {t("تقرير آخر فحص", "Latest scan report")} · <time dateTime={latest.created_at}>{when(latest.created_at)}</time>
  </a>;
  const metrics = [
    { icon: Folder, tone: "blue", label: t("المشاريع", "Total projects"), value: num(projectCount) },
    { icon: Bug, tone: "red", label: t("النتائج في آخر فحص", "Latest scan findings"), value: latest ? num(latest.findings) : "—",
      detail: latest && t(num(latest.unique_findings) + " قاعدة مختلفة", num(latest.unique_findings) + " distinct rules"), points: scans.map((scan) => scan.findings), testId: "dash-findings" },
    { icon: TriangleAlert, tone: "amber", label: t("نتائج عالية الخطورة", "High severity findings"), value: latest ? num(latest.severity.high ?? 0) : "—",
      points: scans.map((scan) => scan.severity?.high ?? 0) },
    { icon: ScanLine, tone: "blue", label: t("فحوصات نشطة", "Active scans"), value: activeCount === undefined ? "—" : num(activeCount),
      detail: t("قيد التنفيذ أو في الانتظار", "Running or queued") },
    { icon: Activity, label: t("تقارير الفحوصات الأخيرة", "Recent scan reports"), value: num(scans.length) },
  ];

  return (
    <section className="dash" data-presenting={presenting || undefined} aria-label={t("لوحة الأرقام", "Numbers")}>
      <CommandMetrics metrics={metrics} />
      <div className="command-panels">
        <CoverageGauge t={t} number={num} cover={cover}>{source}</CoverageGauge>
        <RiskDistribution t={t} number={num} counts={latest?.severity}>
          {change.kind === "counts" && <p className="command-panel-note" data-testid="dash-change">
            {t(num(change.new) + " جديدة · " + num(change.resolved) + " اتحلّت · " + num(change.unchanged) + " زي ما هي · " + num(change.coverageChanged) + " تغيّر في التغطية",
              num(change.new) + " new · " + num(change.resolved) + " resolved · " + num(change.unchanged) + " unchanged · " + num(change.coverageChanged) + " coverage changes")}
          </p>}
          {change.kind === "incomparable" && <p className="command-panel-note" data-testid="dash-incomparable">{t(...change.reason)}</p>}
        </RiskDistribution>
        <ReviewAgents lang={lang} t={t} scanState={currentScan?.state}
          scanHref={currentScan ? "/projects/" + projectId + "/scans/" + currentScan.id : undefined} />
      </div>
      <div className="command-lower">
        {!presenting && <>
          {activity}
          <CommandActivity t={t} events={activityEvents} historyHref={projectId ? "/scans?project=" + encodeURIComponent(projectId) : "/scans"} />
        </>}
        <figure className="dash-trend">
          <figcaption>{t("اتجاه نتائج الفحوصات", "Findings trend")}</figcaption>
          {scans.length > 5 && <div className="overview-chart-filters" role="group" aria-label={t("عدد الفحوصات المعروضة", "Scans shown")}>
            <button type="button" aria-pressed={!showRecent} onClick={() => setShowRecent(false)}>{t("الكل", "All")}</button>
            <button type="button" aria-pressed={showRecent} onClick={() => setShowRecent(true)}>{t("آخر ٥", "Last 5")}</button>
          </div>}
          {scans.length ? <ol className="dash-bars">
            {displayedScans.map((scan, index) => <li key={scan.scan_id} title={when(scan.created_at) + ": " + num(scan.findings)}>
              <a href={reportLink(projectId, scan.scan_id)} aria-label={t("فحص " + when(scan.created_at) + ": " + num(scan.findings) + " نتيجة", "Scan " + when(scan.created_at) + ": " + num(scan.findings) + " findings")}>
                <span className="dash-bar-value">{num(scan.findings)}</span>
                <span className="dash-bar-fill" style={{ blockSize: heights[index] + "%" }} />
                <time dateTime={scan.created_at}>{new Date(scan.created_at).toLocaleDateString(locale, { month: "short", day: "numeric" })}</time>
              </a></li>)}
          </ol> : <p className="command-panel-note">{t("الاتجاه هيظهر بعد أول فحص مكتمل.", "The trend appears after your first finished scan.")}</p>}
        </figure>
      </div>
      <div className="dash-bar">
        {as_of && <p className="dash-fresh" role="status">{t("آخر تحديث:", "Updated:")} <time dateTime={as_of}>{when(as_of)}</time></p>}
        {scans.length > 0 && <button type="button" className="btn" aria-pressed={presenting} onClick={() => setPresenting((value) => !value)}>
          {presenting ? <Minimize2 size={16} aria-hidden="true" /> : <Maximize2 size={16} aria-hidden="true" />}
          {presenting ? t("خروج من وضع العرض", "Exit presentation") : t("وضع العرض", "Presentation mode")}</button>}
      </div>
    </section>
  );
}
