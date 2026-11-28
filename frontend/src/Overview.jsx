import React, { useEffect, useState } from "react";
import { action } from "./platformClient";
import { changeView } from "./dashboard";


// What the signed-in person wants first: what is running, what needs a fix, and where each project stands.
export function ProjectSummary({ path, projectId, t, lang, reportLink }) {
  const [state, setState] = useState(null);
  const locale = lang === "ar" ? "ar-EG" : "en";
  const num = (value) => Number(value).toLocaleString(locale);
  useEffect(() => {
    const controller = new AbortController();
    setState(null);
    action(path + "/dashboard", { signal: controller.signal }).then(
      (data) => { if (!controller.signal.aborted) setState({ data }); },
      () => { if (!controller.signal.aborted) setState({ data: null }); },
    );
    return () => controller.abort();
  }, [path]);
  if (!state) return null;
  const latest = state.data?.latest;
  if (!latest) return <p className="project-summary-empty">{t("الأرقام هتظهر بعد أول فحص مكتمل.", "Numbers appear after the first finished scan.")}</p>;
  const change = changeView(latest.change);
  const changeText = change.kind === "counts"
    ? t(num(change.new) + " جديدة · " + num(change.resolved) + " اتحلّت", num(change.new) + " new · " + num(change.resolved) + " resolved")
    : change.kind === "first" ? t("أول فحص", "First scan") : t(...change.reason);
  return <dl className="project-summary" aria-label={t("ملخص آخر فحص", "Latest scan summary")}>
    <div><dt>{t("النتائج", "Findings")}</dt><dd>{num(latest.findings)}</dd></div>
    <div data-risk={(latest.severity?.high ?? 0) > 0 ? "high" : undefined}><dt>{t("عالية الخطورة", "High severity")}</dt><dd>{num(latest.severity?.high ?? 0)}</dd></div>
    <div><dt>{t("مقارنة بالفحص السابق", "Since the previous scan")}</dt><dd className="project-summary-change">{changeText}</dd></div>
    <div><dt className="visually-hidden">{t("التقرير", "Report")}</dt><dd><a href={reportLink(projectId, latest.scan_id)}>{t("افتح آخر تقرير", "Open the latest report")}</a></dd></div>
  </dl>;
}
