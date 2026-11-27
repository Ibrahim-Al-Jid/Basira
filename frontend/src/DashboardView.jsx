import React, { useEffect, useRef, useState } from "react";
import { Maximize2, Minimize2 } from "lucide-react";
import { action, errorText } from "./platformClient";
import { SEVERITY_ORDER, barHeights, changeView, coverageText } from "./dashboard";
import "./dashboard.css";

const SEVERITY = { high: ["عالية", "High"], medium: ["متوسطة", "Medium"], low: ["منخفضة", "Low"] };

// Overview numbers for one project. Every number names the scan it comes from, with that scan's time.
export default function DashboardView({ path, projectId, t, lang, reportLink }) {
  const [state, setState] = useState({ loading: true });
  const [presenting, setPresenting] = useState(false);
  const [retry, setRetry] = useState(0);
  const root = useRef(null);
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
  }, [path, retry]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!presenting) return undefined;
    const close = (event) => { if (event.key === "Escape") setPresenting(false); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [presenting]);

  if (state.loading) return <p role="status">{t("بنحمّل الأرقام…", "Loading the numbers…")}</p>;
  if (state.error) return <p className="workspace-error" role="alert">{state.error}{" "}
    <button className="btn" onClick={() => setRetry((value) => value + 1)}>{t("إعادة المحاولة", "Retry")}</button></p>;
  const { data } = state;
  if (!data.scans.length) return <section className="dash" aria-label={t("لوحة الأرقام", "Numbers")}>
    <p>{t("مفيش فحوصات مكتملة لسه. الأرقام هتظهر بعد أول فحص.", "No finished scans yet. Numbers appear after the first scan.")}</p></section>;

  const { latest, scans } = data;
  const heights = barHeights(scans);
  const cover = coverageText(latest.coverage);
  const change = changeView(latest.change);
  const from = (scan) => <a className="dash-source" href={reportLink(projectId, scan.scan_id)}>
    {t("من الفحص", "From scan")} <time dateTime={scan.created_at}>{when(scan.created_at)}</time></a>;
  return (
    <section className="dash" ref={root} data-presenting={presenting || undefined} aria-label={t("لوحة الأرقام", "Numbers")}>
      <div className="dash-bar">
        <p className="dash-fresh" role="status">{t("آخر تحديث للّوحة:", "Dashboard updated:")} <time dateTime={data.as_of}>{when(data.as_of)}</time></p>
        <button type="button" className="btn" aria-pressed={presenting} onClick={() => setPresenting((value) => !value)}>
          {presenting ? <Minimize2 size={16} aria-hidden="true" /> : <Maximize2 size={16} aria-hidden="true" />}
          {presenting ? t("خروج من وضع العرض", "Exit presentation") : t("وضع العرض", "Presentation mode")}</button>
      </div>
      <ul className="dash-cards">
        <li className="dash-card" data-tone="findings">
          <h3>{t("النتائج في آخر فحص", "Findings in the latest scan")}</h3>
          <p className="dash-number" data-testid="dash-findings">{num(latest.findings)}</p>
          <p className="dash-sub">{t(`${num(latest.unique_findings)} قاعدة مختلفة`, `${num(latest.unique_findings)} distinct rules`)}</p>
          {from(latest)}
        </li>
        <li className="dash-card" data-tone="severity">
          <h3>{t("حسب الخطورة", "By severity")}</h3>
          <ul className="dash-severity">
            {SEVERITY_ORDER.map((name) => <li key={name} data-severity={name}>
              <span>{t(...SEVERITY[name])}</span><b data-testid={"dash-" + name}>{num(latest.severity[name] || 0)}</b></li>)}
          </ul>
          {from(latest)}
        </li>
        <li className="dash-card" data-tone="coverage">
          <h3>{t("التغطية", "Coverage")}</h3>
          {cover ? <p className="dash-number" data-testid="dash-coverage">{t(`${num(cover.ran)} من ${num(cover.total)}`, `${num(cover.ran)} of ${num(cover.total)}`)}</p>
            : <p className="dash-number dash-na">{t("غير متاحة", "Not available")}</p>}
          <p className="dash-sub">{t("قواعد اتفحصت من إجمالي القواعد. مش معناها إن المشروع سليم.", "Rules that ran out of all rules. It does not mean the project is clean.")}</p>
          {from(latest)}
        </li>
        <li className="dash-card" data-tone="change">
          <h3>{t("التغيير عن الفحص السابق", "Change since the previous scan")}</h3>
          {change.kind === "first" && <p className="dash-sub">{t("ده أول فحص، مفيش مقارنة لسه.", "This is the first scan, nothing to compare yet.")}</p>}
          {change.kind === "incomparable" && <p className="dash-sub" data-testid="dash-incomparable">{t(...change.reason)}</p>}
          {change.kind === "counts" && <ul className="dash-severity" data-testid="dash-change">
            <li><span>{t("جديدة", "New")}</span><b>{num(change.new)}</b></li>
            <li><span>{t("اتحلّت", "Resolved")}</span><b>{num(change.resolved)}</b></li>
            <li><span>{t("زي ما هي", "Unchanged")}</span><b>{num(change.unchanged)}</b></li>
            <li><span>{t("التغطية اتغيرت", "Coverage changed")}</span><b>{num(change.coverageChanged)}</b></li>
          </ul>}
          {latest.change && from(latest)}
        </li>
      </ul>
      <figure className="dash-trend">
        <figcaption>{t(`النتائج عبر آخر ${num(scans.length)} فحوصات`, `Findings across the last ${num(scans.length)} scans`)}</figcaption>
        <ol className="dash-bars">
          {scans.map((scan, index) => <li key={scan.scan_id} title={`${when(scan.created_at)}: ${num(scan.findings)}`}>
            <a href={reportLink(projectId, scan.scan_id)} aria-label={t(`فحص ${when(scan.created_at)}: ${num(scan.findings)} نتيجة`, `Scan ${when(scan.created_at)}: ${num(scan.findings)} findings`)}>
              <span className="dash-bar-value">{num(scan.findings)}</span>
              <span className="dash-bar-fill" style={{ blockSize: heights[index] + "%" }} />
              <time dateTime={scan.created_at}>{new Date(scan.created_at).toLocaleDateString(locale, { month: "short", day: "numeric" })}</time>
            </a></li>)}
        </ol>
      </figure>
    </section>
  );
}
