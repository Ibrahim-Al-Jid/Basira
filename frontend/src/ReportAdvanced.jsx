import React, { useEffect, useRef, useState } from "react";
import { agents, fetchJson, post } from "./data";

const REVIEW_STATUS = ["open", "triaged", "resolved", "accepted"];
const CHANGE_TYPES = ["new", "resolved", "coverage_changed", "unchanged"];

const COPY = {
  ar: {
    compare: "مقارنة الفحوصات",
    baseline: "التقرير المرجعي",
    choose: "اختار تقرير من نفس المشروع",
    unavailableBaseline: "التقرير المرجعي غير متاح",
    noBaselines: "أكمل فحص تاني في المشروع عشان يبقى متاح للمقارنة.",
    noChanges: "المقارنة ما رجّعتش أي نتائج.",
    baselineLoading: "جاري تحميل التقارير المرجعية…",
    comparisonLoading: "جاري مقارنة الفحصين…",
    comparisonError: "تعذّرت مقارنة الفحصين.",
    choicesError: "تعذّر تحميل قائمة التقارير المرجعية.",
    compatible: "الفحصين قابلين للمقارنة.",
    coverage_unavailable: "تغطية أحد الفحصين غير متاحة للمقارنة.",
    incompatible_scope: "نطاق الفحصين مختلف. اختار تقرير لنفس النطاق.",
    incompatible_policy: "سياسة الفحص اتغيّرت. اختار تقرير بنفس إصدار السياسة.",
    incompatible_ruleset: "إصدار القواعد مختلف. اختار تقرير بنفس إصدار القواعد.",
    comparisonLimited: "اختار فحص تاني عشان تقارن النتائج.",
    new: "جديدة",
    resolved: "محلولة",
    coverage_changed: "تغيّر التغطية",
    unchanged: "مستمرة",
    before: "مرجعي",
    after: "حالي",
    findingsReview: "مراجعة النتائج",
    reviewLoading: "جاري تحميل حالة المراجعة…",
    reviewError: "تعذّر تحميل سجل المراجعة.",
    noReview: "التقرير ده مفيهوش نتائج للمراجعة.",
    readOnly: "صلاحيتك تسمح بعرض سجل المراجعة.",
    open: "مفتوحة",
    triaged: "اتراجعت",
    accepted: "مخاطر مقبولة",
    comments: "التعليقات",
    statusHistory: "سجل الحالة",
    noComments: "مفيش تعليقات.",
    noHistory: "مفيش تغييرات في الحالة.",
    comment: "تعليق",
    addComment: "إضافة تعليق",
    reason: "سبب التغيير",
    changeStatus: "تحديث الحالة",
    saveError: "تعذّر حفظ التغيير.",
    emptyComment: "اكتب نص التعليق.",
    emptyReason: "اكتب سبب تغيير الحالة.",
    sameStatus: "اختار حالة مختلفة.",
    saving: "جاري الحفظ…",
    saved: "اتحفظ التغيير.",
    toolRuns: "سجل تشغيل الأدوات",
    noTools: "سجل الأدوات غير متاح للتقرير ده.",
    agent: "الدور",
    checks: "القواعد",
    matches: "المطابقات",
    duration: "المدة",
    ms: "مللي ثانية",
    runCoverage: "تغطية الأداة",
  },
  en: {
    compare: "Compare scans",
    baseline: "Baseline report",
    choose: "Choose a report from this project",
    unavailableBaseline: "Baseline report unavailable",
    noBaselines: "Complete another scan in this project to compare results.",
    noChanges: "This comparison returned no findings.",
    baselineLoading: "Loading baseline reports…",
    comparisonLoading: "Comparing the scans…",
    comparisonError: "Could not compare the scans.",
    choicesError: "Could not load the baseline reports.",
    compatible: "These scans are comparable.",
    coverage_unavailable: "Coverage is unavailable for one of the scans.",
    incompatible_scope: "The scopes differ. Choose a report for the same scope.",
    incompatible_policy: "The scan policy changed. Choose a report with the same policy version.",
    incompatible_ruleset: "The ruleset versions differ. Choose a report with the same ruleset version.",
    comparisonLimited: "Choose another report to compare findings.",
    new: "New",
    resolved: "Resolved",
    coverage_changed: "Coverage changed",
    unchanged: "Still present",
    before: "Baseline",
    after: "Current",
    findingsReview: "Finding review",
    reviewLoading: "Loading finding review…",
    reviewError: "Could not load the review.",
    noReview: "This report has no findings to review.",
    readOnly: "You have read access to this review.",
    open: "Open",
    triaged: "Triaged",
    accepted: "Risk accepted",
    comments: "Comments",
    statusHistory: "Status history",
    noComments: "No comments yet.",
    noHistory: "No status changes yet.",
    comment: "Comment",
    addComment: "Add comment",
    reason: "Reason for change",
    changeStatus: "Update status",
    saveError: "Could not save the change.",
    emptyComment: "Enter a comment.",
    emptyReason: "Enter a reason for the status change.",
    sameStatus: "Choose a different status.",
    saving: "Saving…",
    saved: "Change saved.",
    toolRuns: "Tool execution",
    noTools: "Tool records are unavailable for this report.",
    agent: "Role",
    checks: "Checks",
    matches: "Matches",
    duration: "Duration",
    ms: "ms",
    runCoverage: "Tool coverage",
  },
};

function useResource(url) {
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState(null);
  const current = result?.url === url ? result : null;
  const loading = Boolean(url && (!current || current.attempt !== attempt));

  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    fetchJson(url, { signal: controller.signal }).then(
      (data) => { if (!controller.signal.aborted) setResult({ url, attempt, data }); },
      (error) => { if (!controller.signal.aborted) setResult({ url, attempt, error: error.message }); },
    );
    return () => controller.abort();
  }, [url, attempt]);

  return { data: current?.data, error: loading ? null : current?.error, loading,
    reload: () => setAttempt((value) => value + 1) };
}

function Retry({ message, retry, label }) {
  return (
    <div className="reports-inline-state">
      <p role="alert" dir="auto">{message}</p>
      <button type="button" className="reports-button" onClick={retry}>{label}</button>
    </div>
  );
}

function RuleReference({ rule, path }) {
  return (
    <span className="reports-rule-reference">
      <code dir="ltr">{rule}</code>
      {path && <bdi>{path}</bdi>}
    </span>
  );
}

export function ReportComparison({
  report, reportApi, archiveApi, baseline, onBaselineChange, lang, t, count, dateText, sourceLabel,
}) {
  const advanced = COPY[lang];
  const archive = useResource(archiveApi);
  const comparison = useResource(baseline ? `${reportApi}/compare?baseline=${encodeURIComponent(baseline)}` : null);
  const candidates = (archive.data?.reports || []).filter((candidate) => candidate.id !== report.id);
  const currentSelection = candidates.some((candidate) => candidate.id === baseline);
  const changes = comparison.data?.changes || [];
  const changeCounts = new Map();
  for (const change of changes) changeCounts.set(change.change, (changeCounts.get(change.change) || 0) + 1);
  return (
    <section className="reports-panel reports-section reports-advanced" aria-label={advanced.compare}>
      <label className="reports-review-field">
        {advanced.baseline}
        <select value={baseline || ""} onChange={(event) => onBaselineChange(event.target.value)}
          disabled={!candidates.length && !baseline}>
          <option value="">{advanced.choose}</option>
          {baseline && !currentSelection && <option value={baseline}>{advanced.unavailableBaseline}</option>}
          {candidates.map((candidate) => (
            <option key={candidate.id} value={candidate.id}>
              {sourceLabel(t, candidate.source || candidate.input_artifact)} · {dateText(lang, candidate.created_at)}
            </option>
          ))}
        </select>
      </label>
      {archive.loading && <p role="status" className="reports-annotation">{advanced.baselineLoading}</p>}
      {archive.error && <Retry message={lang === "ar" ? archive.error : advanced.choicesError} retry={archive.reload} label={t.retry} />}
      {archive.data && !candidates.length && !baseline && <p className="reports-empty">{advanced.noBaselines}</p>}
      {comparison.loading && <p role="status" className="reports-annotation">{advanced.comparisonLoading}</p>}
      {comparison.error && <Retry message={lang === "ar" ? comparison.error : advanced.comparisonError} retry={comparison.reload} label={t.retry} />}
      {!comparison.loading && comparison.data && (
        <div className="reports-comparison">
          <p role="status" className={comparison.data.comparable ? "reports-annotation" : "reports-comparison-limited"}>
            {comparison.data.comparable
              ? advanced.compatible
              : advanced[comparison.data.reason] || advanced.comparisonLimited}
          </p>
          {!!changes.length && (
            <dl className="reports-metadata">
              {CHANGE_TYPES.map((type) => (
                <div key={type}>
                  <dt>{advanced[type]}</dt>
                  <dd>{count(changeCounts.get(type) || 0)}</dd>
                </div>
              ))}
            </dl>
          )}
          {changes.length ? (
            <ul className="reports-review-list">
              {changes.map((change) => (
                <li className="reports-comparison-row" key={change.fingerprint}>
                  <RuleReference rule={change.rule} path={change.path} />
                  <span className="reports-tag" data-review-state={change.change}>{advanced[change.change] || change.change}</span>
                  <span className="reports-annotation">{advanced.before} {count(change.before)} · {advanced.after} {count(change.after)}</span>
                </li>
              ))}
            </ul>
          ) : comparison.data.comparable && <p className="reports-empty">{advanced.noChanges}</p>}
        </div>
      )}
    </section>
  );
}

function ReviewForm({ action, item, reportApi, lang, t, onSaved, disabled }) {
  const advanced = COPY[lang];
  const active = useRef(null);
  const [submission, setSubmission] = useState({ status: "idle" });
  const working = submission.status === "saving";

  useEffect(() => () => active.current?.abort(), []);

  async function submit(event) {
    event.preventDefault();
    if (disabled || active.current) return;
    const form = event.currentTarget;
    const fields = new FormData(form);
    const body = action === "comment"
      ? { body: String(fields.get("body")).trim() }
      : { status: fields.get("status"), reason: String(fields.get("reason")).trim() };
    const invalid = action === "comment"
      ? (!body.body && "emptyComment")
      : ((!body.reason && "emptyReason") || (body.status === item.status && "sameStatus"));
    if (invalid) {
      setSubmission({ status: "invalid", message: invalid });
      return;
    }
    const controller = new AbortController();
    active.current = controller;
    setSubmission({ status: "saving" });
    try {
      await fetchJson(reportApi + "/review", { ...post({ fingerprint: item.fingerprint, action, ...body }), signal: controller.signal });
      if (controller.signal.aborted) return;
      form.reset();
      setSubmission({ status: "saved" });
      onSaved();
    } catch (error) {
      if (!controller.signal.aborted) setSubmission({ status: "error", message: error.message });
    } finally {
      active.current = null;
    }
  }

  return (
    <form className="reports-review-form" onSubmit={submit}>
      {action === "comment" ? (
        <label className="reports-review-field">
          {advanced.comment}
          <textarea name="body" rows={3} required maxLength={2000} dir="auto" disabled={disabled || working} />
        </label>
      ) : (
        <>
          <label className="reports-review-field">
            {t.status}
            <select name="status" defaultValue={item.status} key={item.status} required disabled={disabled || working}>
              {REVIEW_STATUS.map((status) => <option value={status} key={status}>{advanced[status]}</option>)}
            </select>
          </label>
          <label className="reports-review-field">
            {advanced.reason}
            <textarea name="reason" rows={2} required maxLength={500} dir="auto" disabled={disabled || working} />
          </label>
        </>
      )}
      <button className="reports-button" disabled={disabled || working}>
        {action === "comment" ? advanced.addComment : advanced.changeStatus}
      </button>
      {working && <small role="status">{advanced.saving}</small>}
      {submission.status === "saved" && <small role="status">{advanced.saved}</small>}
      {submission.status === "invalid" && <p role="alert">{advanced[submission.message]}</p>}
      {submission.status === "error" && <p role="alert" dir="auto">{lang === "ar" ? submission.message : advanced.saveError}</p>}
    </form>
  );
}

export function ReportDialog({ lang, title, onClose, children }) {
  const dialog = useRef(null);
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return <dialog className="reports-dialog" ref={dialog} aria-label={title} onClose={onClose}>
    <header className="reports-dialog-heading">
      <h2>{title}</h2>
      <button className="reports-button" type="button" autoFocus onClick={() => dialog.current.close()}>
        {lang === "ar" ? "إغلاق" : "Close"}
      </button>
    </header>
    {children}
  </dialog>;
}

export function FindingReview({ reportApi, findings, lang, t, dateText }) {
  const advanced = COPY[lang];
  const review = useResource(reportApi + "/review");
  const items = review.data?.items || [];
  const [selected, select] = useState("");
  const detailsByRule = new Map(findings.map((finding) => [finding.rule, finding]));
  const titleOf = (item) => {
    const finding = detailsByRule.get(item.rule);
    return (lang === "ar" ? finding?.title_ar || finding?.title : finding?.title) || item.rule;
  };
  const item = items.find((item) => item.fingerprint === selected) || items[0];
  return (
    <section className="reports-panel reports-section reports-advanced" aria-label={advanced.findingsReview}>
      {review.loading && <p role="status" className="reports-annotation">{advanced.reviewLoading}</p>}
      {review.error && <Retry message={lang === "ar" ? review.error : advanced.reviewError} retry={review.reload} label={t.retry} />}
      {review.data && !items.length && <p className="reports-empty">{advanced.noReview}</p>}
      {!!items.length && !review.data.can_edit && <p className="reports-annotation">{advanced.readOnly}</p>}
      {items.length > 1 && <label className="reports-review-field">
        {lang === "ar" ? "النتيجة" : "Finding"}
        <select value={item.fingerprint} onChange={(event) => select(event.target.value)}>
          {items.map((item) => <option value={item.fingerprint} key={item.fingerprint}>
            {item.rule} · {titleOf(item)}{item.path ? " · " + item.path : ""}
          </option>)}
        </select>
      </label>}
      {item && (
          <article className="reports-review-item" key={item.fingerprint}>
            <header className="reports-review-heading">
              <h2>{titleOf(item)}</h2>
              <span className="reports-tag" data-review-state={item.status}>{advanced[item.status] || item.status}</span>
              <RuleReference rule={item.rule} path={item.path} />
            </header>
            <div className="reports-review-body">
              <div className="reports-review-history">
                <section>
                  <h3>{advanced.comments}</h3>
                  {item.comments?.length ? (
                    <ol className="reports-review-list">
                      {item.comments.map((comment) => (
                        <li key={comment.id}>
                          <p className="reports-annotation"><bdi>{comment.author}</bdi> · <time dateTime={comment.created_at}>{dateText(lang, comment.created_at)}</time></p>
                          <p className="reports-review-text" dir="auto">{comment.body}</p>
                        </li>
                      ))}
                    </ol>
                  ) : <p className="reports-empty">{advanced.noComments}</p>}
                </section>
                <section>
                  <h3>{advanced.statusHistory}</h3>
                  {item.history?.length ? (
                    <ol className="reports-review-list">
                      {item.history.map((event, index) => (
                        <li key={event.created_at + "-" + index}>
                          <p className="reports-annotation"><bdi>{event.author}</bdi> · <time dateTime={event.created_at}>{dateText(lang, event.created_at)}</time></p>
                          <p className="reports-review-text">
                            {advanced[event.previous] || event.previous} · {advanced[event.status] || event.status}
                          </p>
                          <p className="reports-review-text" dir="auto">{event.reason}</p>
                        </li>
                      ))}
                    </ol>
                  ) : <p className="reports-empty">{advanced.noHistory}</p>}
                </section>
              </div>
              {review.data.can_edit && (
                <div className="reports-review-history">
                  {["comment", "status"].map((action) => (
                    <ReviewForm action={action} item={item} reportApi={reportApi} lang={lang} t={t}
                      onSaved={review.reload} disabled={review.loading} key={action} />
                  ))}
                </div>
              )}
            </div>
          </article>
      )}
    </section>
  );
}

export function ToolRuns({ runs, lang, t, label, count }) {
  const advanced = COPY[lang];
  const [selected, select] = useState(null);
  return (
    <section className="reports-panel reports-section reports-advanced">
      <h2>{advanced.toolRuns}</h2>
      {!runs?.length ? <p className="reports-empty">{advanced.noTools}</p> : (
        <ul className="reports-review-list">
          {runs.map((run) => (
            <li className="reports-tool" key={run.id}>
              <div className="reports-tool-heading">
                <code dir="ltr">{run.tool}</code>
                <span className="reports-tag">{label(t, run.status)}</span>
              </div>
              <dl className="reports-metadata">
                <div><dt>{advanced.agent}</dt><dd>{agents[run.agent]?.[lang === "ar" ? 0 : 1] || run.agent}</dd></div>
                <div><dt>{advanced.checks}</dt><dd>{count(run.checks ?? 0)}</dd></div>
                <div><dt>{advanced.matches}</dt><dd>{count(run.matched ?? 0)}</dd></div>
                {run.duration_ms != null && <div><dt>{advanced.duration}</dt><dd>{count(run.duration_ms)} {advanced.ms}</dd></div>}
              </dl>
              {!!run.coverage?.length && (
                <button type="button" className="reports-button" onClick={() => select(run)}
                  aria-label={advanced.runCoverage + " · " + run.tool}>{advanced.runCoverage} · {count(run.coverage.length)}</button>
              )}
            </li>
          ))}
        </ul>
      )}
      {selected && <ReportDialog lang={lang} title={advanced.runCoverage + " · " + selected.tool} onClose={() => select(null)}>
        <ul className="reports-tool-rules">
          {selected.coverage.map((rule) => <li key={rule}><code dir="ltr">{rule}</code></li>)}
        </ul>
      </ReportDialog>}
    </section>
  );
}
