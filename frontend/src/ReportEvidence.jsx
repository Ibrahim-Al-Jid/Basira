import React, { useEffect, useState } from "react";
import { action, errorText, json, translate } from "./platformClient";

export function FileManifest({ entries, lang }) {
  if (!entries?.length) return null;
  const t = translate(lang);
  return <section className="reports-section">
    <h2>{t("ملفات اللقطة", "Snapshot files")}</h2>
    <div className="reports-table-wrap" role="region" tabIndex={0} aria-label={t("نطاق ملفات اللقطة", "Snapshot file scope")}>
      <table className="reports-coverage reports-file-table">
        <thead><tr>
          <th scope="col">{t("الملف", "File")}</th>
          <th scope="col">{t("حالة الإدراج", "Inclusion")}</th>
        </tr></thead>
        <tbody>{entries.map(({ path, status, reason }, index) => <tr key={`${path}:${index}`}>
          <td><code dir="auto">{path}</code></td>
          <td>{status === "included" ? t("اتضمّن في الفحص", "Included in scan")
            : reason === "unsupported_extension" ? t("اتخطّى · امتداد غير مدعوم", "Skipped · unsupported extension")
            : reason === "build_artifact" ? t("اتخطّى · ملف ناتج عن البناء أو تبعية مضمّنة", "Skipped · build output or vendored dependency")
            : t("اتخطّى", "Skipped")}</td>
        </tr>)}</tbody>
      </table>
    </div>
  </section>;
}

export function ImportedEvidence({ evidence, lang, count }) {
  if (!evidence) return null;
  const t = translate(lang);
  return <section className="reports-section">
    <h2>{t("ملاحظات ZAP المستوردة", "Imported ZAP observations")}</h2>
    <p>{t("الملاحظات جاية من تقرير محفوظ وبتحتاج مراجعة مع الدليل الأصلي.",
      "These observations come from a saved report and need review alongside the original evidence.")}</p>
    <dl className="reports-metadata">
      <div><dt>{t("التنبيهات المقبولة", "Accepted alerts")}</dt><dd>{count(evidence.accepted_alerts)}</dd></div>
      <div><dt>{t("التنبيهات المتخطّاة", "Skipped alerts")}</dt><dd>{count(evidence.skipped_alerts)}</dd></div>
    </dl>
  </section>;
}

export function LinkedEvidence({ reportApi, hrefFor, follow, lang, count, formatDate }) {
  const t = translate(lang);
  const endpoint = reportApi + "/links";
  const [view, setView] = useState(null);
  const [candidates, setCandidates] = useState(null);
  const [failure, setFailure] = useState(null);
  const [pending, setPending] = useState(false);
  const [revision, setRevision] = useState(0);
  const [choice, setChoice] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    async function load() {
      const next = await action(endpoint, options);
      if (controller.signal.aborted) return;
      setView(next);
      if (next.can_link) {
        const available = await action(reportApi + "/link-candidates", options);
        if (!controller.signal.aborted) setCandidates(available.reports);
      }
    }
    load().catch((error) => {
      if (!controller.signal.aborted) setFailure(error);
    });
    return () => controller.abort();
  }, [endpoint, reportApi, revision]);

  async function change(id) {
    if (pending || (!choice && !id)) return;
    setFailure(null);
    setPending(true);
    try {
      if (id) {
        await action(endpoint + "/" + encodeURIComponent(id), { method: "DELETE" });
      } else {
        await action(endpoint, json("POST", { report_id: choice }));
      }
      setChoice("");
      setRevision((value) => value + 1);
    } catch (error) {
      setFailure(error);
    } finally {
      setPending(false);
    }
  }

  return <section className="reports-panel reports-section">
    <h2>{t("الأدلة المرتبطة", "Linked evidence")}</h2>
    <p>{t("الربط بيجمع تقارير من نفس المشروع ومرجع الموقع، وكل تقرير بيحتفظ بمصدر أدلته ونتائجه.",
      "Link a source snapshot and website evidence from the same project and site reference. Each report keeps its own findings and provenance.")}</p>
    {!view && !failure && <p role="status">{t("بنحمّل الروابط…", "Loading linked evidence…")}</p>}
    {failure && <div className="reports-caution" role="alert">{errorText(failure, t)}{" "}
      <button className="reports-button" type="button" onClick={() => {
        setFailure(null);
        setRevision((value) => value + 1);
      }}>{t("إعادة المحاولة", "Retry")}</button>
    </div>}
    {view?.links?.length > 0 && <ul className="reports-evidence-links">
      {view.links.map((item) => {
        const href = hrefFor(item.report_id);
        return <li key={item.id}>
          <div>
            <a href={href} onClick={(event) => follow(event, href)}><bdi>{item.name}</bdi></a>
            <p>{count(item.finding_count)} {t("نتائج في التقرير المرتبط", "findings in the linked report")}</p>
          </div>
          {view.can_link && <button className="reports-button" type="button" disabled={pending}
            aria-label={t(`أزل رابط ${item.name}`, `Remove link to ${item.name}`)}
            onClick={() => void change(item.id)}>{t("أزل الرابط", "Remove link")}</button>}
        </li>;
      })}
    </ul>}
    {view?.links?.length === 0 && <p>{t("لسه مفيش تقارير مرتبطة.", "There are no linked reports yet.")}</p>}
    {view?.can_link && candidates?.length > 0 && <form className="project-form" aria-busy={pending} onSubmit={(event) => {
      event.preventDefault();
      void change(null);
    }}>
      <label>{t("التقرير المطابق", "Matching report")}
        <select value={choice} disabled={pending} required onChange={(event) => setChoice(event.target.value)}>
          <option value="">{t("اختار تقرير", "Choose a report")}</option>
          {candidates.map((item) => <option key={item.id} value={item.id}>
            {item.name}{item.created_at ? " · " + formatDate(item.created_at) : ""}
          </option>)}
        </select>
      </label>
      <button className="reports-button" type="submit" disabled={pending || !choice}>{t("اربط التقرير", "Link report")}</button>
    </form>}
    {view?.can_link && candidates?.length === 0 && <p>{t("مفيش تقارير تانية مطابقة لمرجع الموقع في المشروع.",
      "There are no other matching reports for this site reference in the project.")}</p>}
  </section>;
}

export function AgentReview({ findings, lang, count }) {
  if (!findings?.length) return null;
  const t = translate(lang);
  return <section className="reports-section reports-agent-review" aria-labelledby="agent-review-title">
    <h2 id="agent-review-title">{t("مراجعة الوكلاء", "Agent review")} <span className="reports-agent-badge">{t("تحتاج مراجعة", "Review required")}</span></h2>
    <p>{t("دي ملاحظات من الوكلاء راجعها المدقق في نسخة المصدر. هي ادّعاءات من موديل، مش نتائج مؤكدة، ومش محسوبة في النتائج أو التغطية.",
      "These are places the agents pointed at and the Auditor re-read in the source snapshot. They are model claims, not confirmed findings, and are not counted in the findings or coverage.")}</p>
    <ul className="reports-agent-list">
      {findings.map((item) => <li key={item.fingerprint}>
        <strong dir="ltr">{item.rule}</strong>
        <span dir="ltr">{item.path}:{count(item.line)}</span>
        <code dir="ltr">{item.quote}</code>
      </li>)}
    </ul>
  </section>;
}
