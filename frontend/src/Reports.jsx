import React, { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowLeft, ArrowRight, FileCheck2, FileText, Search } from "lucide-react";
import { agents, fetchJson } from "./data";
import { FindingReview, ReportComparison, ReportDialog, ToolRuns } from "./ReportAdvanced";
import { FileManifest, ImportedEvidence, LinkedEvidence } from "./ReportEvidence";
import "./reports.css";

const PAGE_SIZE = 10;

const copy = {
  ar: {
    reports: "سجل التقارير",
    report: "تقرير فحص HTML",
    projectReport: "تقرير فحص المشروع",
    newScan: "فحص جديد",
    back: "كل التقارير",
    search: "بحث في التقارير",
    searchHint: "اسم الملف، الموديل، أو معرّف التقرير",
    searchFindings: "بحث في النتائج",
    filterHint: "اسم القاعدة، الدليل، أو رقم السطر",
    all: "الكل",
    severity: "الشدة",
    domain: "المجال",
    enrichment: "إثراء الموديل",
    results: "النتائج",
    sections: "أقسام التقرير",
    viewEvidence: "عرض الدليل",
    api: "عقد واجهة API",
    document: "المستند",
    apiVersion: "إصدار OpenAPI",
    apiOperations: "العمليات المعلنة",
    apiAuth: "عمليات تتطلب المصادقة في الوثيقة",
    apiAnonymous: "عمليات بلا هوية معلنة",
    apiReferences: "المراجع المحلية",
    apiUnresolved: "المراجع غير المحلولة",
    apiSchemes: "أنواع المصادقة",
    apiUnresolvedSecurity: "متطلبات مصادقة غير مرتبطة بتعريف",
    importedZap: "ملاحظة مستوردة من ZAP",
    noImportedZap: "التقرير المحفوظ مفيهوش ملاحظات اتقبلت للاستيراد.",
    linkedEvidence: "الأدلة المرتبطة",
    linkedRepository: "مستودع GitHub",
    linkedCommit: "معرّف النسخة",
    occurrences: "المواضع",
    source: "المصدر",
    sourceDetails: "تفاصيل المصدر",
    scope: "نطاق الفحص",
    scopeText: "مراجعة ثابتة لإعدادات السكربتات والنماذج في مصدر HTML المقدّم.",
    projectScope: "مراجعة دفاعية للملفات المقدّمة حسب سياسة المشروع.",
    date: "التاريخ",
    status: "الحالة",
    model: "الموديل",
    modelCalls: "استدعاءات الموديل",
    modelOrder: "ترتيب الأولويات المقترح من الموديل",
    seconds: "ثانية",
    duration: "مدة الفحص",
    loading: "جاري تحميل التقارير…",
    retry: "إعادة المحاولة",
    loadError: "تعذّر تحميل التقرير أو السجل.",
    noReports: "لسه مفيش تقارير محفوظة.",
    noMatches: "مفيش تقارير مطابقة للفلاتر دي.",
    noFindingsMatches: "مفيش نتائج مطابقة للفلاتر دي.",
    zeroFindings: "القواعد اللي اتنفذت ما رصدتش أدلة مطابقة في المصدر ده.",
    noApplicable: "ولا قاعدة من قواعد الفحص انطبقت على المصدر ده.",
    unavailable: "غير متاح",
    none: "بدون موديل",
    legacyCoverage: "تفاصيل التغطية لكل قاعدة غير متاحة للتقرير ده.",
    claimTitle: "تقارير المختبر في جلستك",
    claimIntro: "اتعملت في المختبر قبل تسجيل الدخول. احفظها في المشروع ده قبل ما الجلسة تنتهي.",
    claimSave: "احفظ في المشروع",
    claimSaving: "جاري الحفظ…",
    claimError: "التقرير ما تحفظش في المشروع. جرّبي تاني.",
    noSteps: "أحداث التشغيل غير متاحة للتقرير ده.",
    line: "سطر",
    lines: "سطر",
    bytes: "بايت",
    confidence: "الثقة",
    evidence: "الدليل",
    remediation: "الإصلاح",
    executive: "ملخص الفحص",
    decisionTitle: "القرار",
    decisionClear: "مفيش نتايج في اللي اتفحص",
    decisionFix: "إصلاحات قبل التسليم",
    decisionFixOne: "إصلاح واحد قبل التسليم",
    decisionFirst: "ابدأ بالأهم",
    decisionCovered: "قواعد اتنفذت من",
    decisionNotChecked: "قواعد ماتفحصتش أو مش مطبّقة على النوع ده",
    decisionCaution: "ده مش معناه إن المشروع سليم: اللي ماتفحصش مكتوب في التغطية.",
    decisionOpen: "افتح النتيجة",
    pdf: "تحميل PDF",
    alternatePdf: "تحميل PDF بالإنجليزي",
    findingTypes: "أنواع النتائج",
    rulesApplied: "قواعد اتنفذت",
    incompleteCoverage: "بعض القواعد ما اكتملتش. راجع تغطية الفحص للتفاصيل.",
    technical: "التفاصيل الفنية",
    snapshotVerification: "مطابقة لقطة الفحص",
    verifiedLocations: "مواضع الأدلة المتحققة",
    verifiedFiles: "الملفات اللي قرأها التحليل",
    snapshotSha256: "بصمة المصدر",
    agentAdvisory: "إرشادات الوكلاء",
    advisoryNote: "إشارات مراجعة بشرية فقط؛ لا تُضيف دليلًا ولا تغيّر شدة النتيجة.",
    advisoryPlanning: "اقتراحات التخطيط",
    advisoryValidation: "اقتراحات التحقق",
    advisoryExplanation: "اقتراحات الشرح",
    review_tool_coverage: "راجع تغطية الأداة",
    review_tool_findings: "راجع نتائج الأداة",
    present: "عرض خطوة بخطوة", presentNext: "النتيجة التالية", presentAll: "عرض الكل", presentRestart: "من البداية", presentProgress: "المعروض",
    review_evidence: "راجع الدليل",
    review_context: "راجع السياق",
    read_remediation: "اقرأ الإصلاح",
    confirm_scope: "أكّد النطاق",
    priorReviews: "سياق المراجعة السابق",
    priorReviewsNote: "حالات تصنيف سابقة من نفس المشروع واللقطة؛ سياق فقط لا دليل جديد.",
    priorScan: "فحص سابق",
    triaged: "تم فرزها",
    resolved: "تم حلها",
    accepted: "مقبولة",
    moreFormats: "صيغ تنزيل أخرى",
    compareTitle: "مقارنة الفحوصات",
    reviewTitle: "مراجعة النتائج",
    policyVersion: "إصدار السياسة",
    provenance: "مصدر الفحص",
    snapshotHash: "بصمة الملف",
    policyHash: "بصمة السياسة",
    rawExpiry: "انتهاء الاحتفاظ بالملف",
    profile: "ملف الفحص",
    asset: "مرجع الأصل المعلن",
    records: "سجل الأدلة",
    provenanceLoading: "جاري تحميل مصدر الفحص…",
    provenanceUnavailable: "بيانات مصدر الفحص غير متاحة للتقرير ده.",
    provenanceError: "تعذّر تحميل مصدر الفحص.",
    coverage: "تغطية الفحص",
    rule: "القاعدة",
    steps: "أحداث الوكلاء",
    summarySource: "مصدر الملخص",
    modelSummary: "قالب بصيرة بترتيب الموديل",
    systemSummary: "قالب بصيرة",
    filter: "الفلاتر",
    reset: "مسح الفلاتر",
    prev: "السابق",
    next: "التالي",
    page: "صفحة",
    of: "من",
    listed: "تقرير",
    high: "عالية",
    medium: "متوسطة",
    low: "منخفضة",
    html: "إعدادات HTML",
    web: "المتصفح والاستجابات",
    dependencies: "التبعيات",
    infrastructure: "البنية التحتية",
    ci: "خطوط CI/CD",
    application: "إعدادات التطبيق",
    file: "ملف HTML",
    paste: "كود ملصوق",
    sample: "العينة المرجعية",
    local: "محلي",
    modelEnrichment: "تم بالموديل",
    fallback: "بديل محلي",
    disabled: "غير مفعّل",
    completed: "مكتمل",
    partial: "جزئي",
    failed: "فشل",
    cancelled: "أُلغي",
    matched: "دليل مطابق",
    clear: "بلا مطابقات",
    not_applicable: "غير منطبق",
    skipped: "متخطّى",
    error: "خطأ",
    observed: "دليل مرصود",
    review_required: "يحتاج مراجعة",
    start: "بدأ",
    done: "اكتمل",
    system: "محلي",
    json: "تحميل JSON",
    downloadAr: "تحميل HTML عربي",
    downloadEn: "تحميل HTML إنجليزي",
    benchmark: "نتيجة العينة المرجعية",
    unexpected: "إضافية",
  },
  en: {
    reports: "Reports",
    report: "HTML review report",
    projectReport: "Project review report",
    newScan: "New scan",
    back: "All reports",
    search: "Search reports",
    searchHint: "File name, model, or report ID",
    searchFindings: "Search findings",
    filterHint: "Rule name, evidence, or line number",
    all: "All",
    severity: "Severity",
    domain: "Domain",
    enrichment: "Model enrichment",
    results: "Findings",
    sections: "Report sections",
    viewEvidence: "View evidence",
    api: "API contract",
    document: "Document",
    apiVersion: "OpenAPI version",
    apiOperations: "Declared operations",
    apiAuth: "Operations declaring required authentication",
    apiAnonymous: "Operations without declared authentication",
    apiReferences: "Local references",
    apiUnresolved: "Unresolved references",
    apiSchemes: "Authentication scheme types",
    apiUnresolvedSecurity: "Unresolved security requirements",
    importedZap: "Imported ZAP observation",
    noImportedZap: "The saved report contained no observations accepted for import.",
    linkedEvidence: "Linked evidence",
    linkedRepository: "GitHub repository",
    linkedCommit: "Commit SHA",
    occurrences: "Occurrences",
    source: "Source",
    sourceDetails: "Source details",
    scope: "Review scope",
    scopeText: "Static review of script and form settings in the supplied HTML.",
    projectScope: "Offline defensive review of the supplied artifacts under the project policy.",
    date: "Date",
    status: "Status",
    model: "Model",
    modelCalls: "Model calls",
    modelOrder: "Order suggested by the model",
    seconds: "s",
    duration: "Duration",
    loading: "Loading reports…",
    retry: "Try again",
    loadError: "Could not load the report or archive.",
    noReports: "No saved reports yet.",
    noMatches: "No reports match these filters.",
    noFindingsMatches: "No findings match these filters.",
    zeroFindings: "The rules that ran found no matching evidence in this source.",
    noApplicable: "No registered rule applied to this source.",
    unavailable: "Unavailable",
    none: "No model",
    legacyCoverage: "Rule-by-rule coverage is unavailable for this report.",
    claimTitle: "Lab reports in your session",
    claimIntro: "Created in the lab before signing in. Save them into this project before the session ends.",
    claimSave: "Save to project",
    claimSaving: "Saving…",
    claimError: "The report could not be saved to the project. Try again.",
    noSteps: "Execution events are unavailable for this report.",
    line: "Line",
    lines: "lines",
    bytes: "bytes",
    confidence: "Confidence",
    evidence: "Evidence",
    remediation: "Remediation",
    executive: "Scan summary",
    decisionTitle: "Decision",
    decisionClear: "No findings in what was checked",
    decisionFix: "fixes before handover",
    decisionFixOne: "One fix before handover",
    decisionFirst: "Start with the most important",
    decisionCovered: "rules ran out of",
    decisionNotChecked: "rules were not checked or do not apply to this input",
    decisionCaution: "This does not mean the project is clean: what was not checked is listed under Coverage.",
    decisionOpen: "Open finding",
    pdf: "Download PDF",
    alternatePdf: "Download Arabic PDF",
    findingTypes: "Finding types",
    rulesApplied: "Rules run",
    incompleteCoverage: "Some checks did not finish. Open scan coverage for details.",
    technical: "Technical details",
    snapshotVerification: "Scan snapshot verification",
    verifiedLocations: "Validated evidence locations",
    verifiedFiles: "Files read by analysis",
    snapshotSha256: "Source fingerprint",
    agentAdvisory: "Agent advisory",
    advisoryNote: "Human review hints only; they add no evidence and do not change finding severity.",
    advisoryPlanning: "Planning hints",
    advisoryValidation: "Validation hints",
    advisoryExplanation: "Explanation hints",
    review_tool_coverage: "Review tool coverage",
    review_tool_findings: "Review tool findings",
    present: "Step-by-step view", presentNext: "Next finding", presentAll: "Show all", presentRestart: "Restart", presentProgress: "Shown",
    review_evidence: "Review evidence",
    review_context: "Review context",
    read_remediation: "Read remediation",
    confirm_scope: "Confirm scope",
    priorReviews: "Prior review context",
    priorReviewsNote: "Prior triage states from the same project and snapshot; context only, not new evidence.",
    priorScan: "Prior scan",
    triaged: "Triaged",
    resolved: "Resolved",
    accepted: "Accepted",
    moreFormats: "Other download formats",
    compareTitle: "Compare scans",
    reviewTitle: "Finding review",
    policyVersion: "Policy version",
    provenance: "Scan provenance",
    snapshotHash: "File digest",
    policyHash: "Policy digest",
    rawExpiry: "Raw file expiry",
    profile: "Scan profile",
    asset: "Declared asset reference",
    records: "Evidence records",
    provenanceLoading: "Loading scan provenance…",
    provenanceUnavailable: "This report does not have scan provenance.",
    provenanceError: "Could not load scan provenance.",
    coverage: "Scan coverage",
    rule: "Rule",
    steps: "Agent events",
    summarySource: "Summary source",
    modelSummary: "Basira template with model prioritization",
    systemSummary: "Basira template",
    filter: "Filters",
    reset: "Clear filters",
    prev: "Previous",
    next: "Next",
    page: "Page",
    of: "of",
    listed: "reports",
    high: "High",
    medium: "Medium",
    low: "Low",
    html: "HTML configuration",
    web: "Browser and responses",
    dependencies: "Dependencies",
    infrastructure: "Infrastructure",
    ci: "CI/CD",
    application: "Application configuration",
    file: "HTML file",
    paste: "Pasted source",
    sample: "Reference fixture",
    local: "Local",
    modelEnrichment: "Model enriched",
    fallback: "Local fallback",
    disabled: "Disabled",
    completed: "Completed",
    partial: "Partial",
    failed: "Failed",
    cancelled: "Cancelled",
    matched: "Matched",
    clear: "No match",
    not_applicable: "Not applicable",
    skipped: "Skipped",
    error: "Error",
    observed: "Observed",
    review_required: "Review required",
    start: "Started",
    done: "Finished",
    system: "Local",
    json: "Download JSON",
    downloadAr: "Download Arabic HTML",
    downloadEn: "Download English HTML",
    benchmark: "Reference fixture",
    unexpected: "unexpected",
  },
};

const label = (t, value) => value ? (Object.hasOwn(t, value) ? t[value] : value) : t.unavailable;
const enrichLabel = (t, value) => value === "model" ? t.modelEnrichment : label(t, value);
const modelLabel = (t, report) => report.model || (report.enrichment === "disabled" ? t.none : t.unavailable);
const sourceLabel = (t, source) => source?.name || label(t, source?.kind);
const importedFromZap = (finding) => finding.origins?.some(({ tool }) => tool === "zap-passive-report");
const lower = (value) => String(value ?? "").toLowerCase();
const unique = (items) => [...new Set(items.filter(Boolean))];
const fields = (value) => Array.isArray(value) ? value : Object.keys(value || {});
const numberFormats = Object.fromEntries(Object.keys(copy).map((lang) => [lang, new Intl.NumberFormat(lang)]));
const dateFormats = Object.fromEntries(Object.keys(copy).map((lang) => [
  lang,
  new Intl.DateTimeFormat(lang, { dateStyle: "medium", timeStyle: "short" }),
]));

function dateText(lang, value) {
  const date = new Date(value);
  return value && Number.isFinite(date.getTime()) ? dateFormats[lang].format(date) : copy[lang].unavailable;
}

function routeLink(event, path, navigate) {
  if (event.button !== 0 || event.metaKey || event.altKey || event.ctrlKey || event.shiftKey) return;
  event.preventDefault();
  navigate(path);
}

function Link({ href, navigate, children, ...props }) {
  return <a {...props} href={href} onClick={(event) => routeLink(event, href, navigate)}>{children}</a>;
}

function SelectFilter({ name, value, options, update, t, title }) {
  return (
    <label>
      {title}
      <select name={name} value={value} onChange={(event) => update(name, event.target.value)}>
        <option value="">{t.all}</option>
        {unique([value, ...options]).map((option) => (
          <option value={option} key={option}>
            {name === "enrichment" ? enrichLabel(t, option) : label(t, option)}
          </option>
        ))}
      </select>
    </label>
  );
}

function SearchFilter({ name, value, update, title, placeholder }) {
  return (
    <label className="reports-search">
      {title}
      <span>
        <Search size={17} aria-hidden="true" />
        <input
          name={name}
          type="search"
          value={value}
          placeholder={placeholder}
          onChange={(event) => update(name, event.target.value)}
        />
      </span>
    </label>
  );
}

function reportPath(pathname, params, changes) {
  const next = new URLSearchParams(params);
  for (const [name, value] of Object.entries(changes)) {
    if (value) next.set(name, value);
    else next.delete(name);
  }
  const search = next.toString();
  return pathname + (search ? "?" + search : "");
}


function ClaimableLabReports({ projectApi, archiveReports, t, lang, onClaimed }) {
  const [lab, setLab] = useState(null);
  const [busy, setBusy] = useState("");
  const [failed, setFailed] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetchJson("/api/history", { signal: controller.signal }).then(
      (data) => { if (!controller.signal.aborted) setLab(data.reports || []); },
      () => { if (!controller.signal.aborted) setLab([]); },
    );
    return () => controller.abort();
  }, [projectApi]);
  const known = new Set((archiveReports || []).map((report) => report.id));
  const items = (lab || []).filter((report) => !known.has(report.id));
  if (!items.length) return null;
  async function claim(reportId) {
    setBusy(reportId);
    setFailed("");
    try {
      const result = await fetch(`${projectApi}/${encodeURIComponent(reportId)}/claim`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }),
      });
      if (result.status === 201 || result.status === 409) {
        onClaimed();
      } else {
        const body = await result.json().catch(() => null);
        setFailed(typeof body?.detail === "string" ? body.detail : "claim");
      }
    } catch {
      setFailed("claim");
    }
    setBusy("");
  }
  return (
    <div className="reports-panel reports-claim">
      <h2>{t.claimTitle}</h2>
      <p>{t.claimIntro}</p>
      <ul>
        {items.map((report) => (
          <li key={report.id}>
            <bdi>{sourceLabel(t, report.source || report.input_artifact)}</bdi>
            <small>{dateText(lang, report.created_at)}</small>
            <button className="reports-button" type="button" disabled={busy === report.id}
              onClick={() => claim(report.id)}>{busy === report.id ? t.claimSaving : t.claimSave}</button>
          </li>
        ))}
      </ul>
      {failed && <p role="alert" dir="auto">{lang === "ar" ? failed : t.claimError}</p>}
    </div>
  );
}

function Archive({ reports, t, lang, params, navigate }) {
  const count = (value) => numberFormats[lang].format(value);
  const query = params.get("q") ?? "";
  const severity = params.get("severity") ?? "";
  const domain = params.get("domain") ?? "";
  const enrichment = params.get("enrichment") ?? "";
  const archiveChanged = (name, value) => navigate(reportPath("/reports", params, { [name]: value, page: "" }), { replace: name === "q" });
  const filtered = reports.filter((report) => {
    const terms = lower([report.id, report.model, sourceLabel(t, report.source || report.input_artifact)].join(" "));
    return terms.includes(lower(query.trim()))
      && (!severity || fields(report.severities).includes(severity))
      && (!domain || fields(report.domains).includes(domain))
      && (!enrichment || report.enrichment === enrichment);
  });
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const page = Math.min(pages, Math.max(1, Number.parseInt(params.get("page") ?? "1", 10) || 1));
  const pageRows = filtered.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const active = Boolean(query || severity || domain || enrichment);
  const pageTo = (number) => navigate(reportPath("/reports", params, { page: number === 1 ? "" : number }));

  if (!reports.length) {
    return (
      <div className="reports-panel reports-state">
        <FileText size={26} aria-hidden="true" />
        <p>{t.noReports}</p>
      </div>
    );
  }
  return (
    <>
      <div className="reports-panel reports-filters" role="group" aria-label={t.filter}>
        <SearchFilter name="q" value={query} update={archiveChanged} title={t.search} placeholder={t.searchHint} />
        <SelectFilter t={t} title={t.severity} name="severity" value={severity} options={reports.flatMap((item) => fields(item.severities))} update={archiveChanged} />
        <SelectFilter t={t} title={t.domain} name="domain" value={domain} options={reports.flatMap((item) => fields(item.domains))} update={archiveChanged} />
        <SelectFilter t={t} title={t.enrichment} name="enrichment" value={enrichment} options={reports.map((item) => item.enrichment)} update={archiveChanged} />
        {active && <button className="reports-button" onClick={() => navigate(reportPath("/reports", params, { q: "", severity: "", domain: "", enrichment: "", page: "" }))}>{t.reset}</button>}
      </div>
      <p className="reports-count" role="status">{count(filtered.length)} {t.listed}</p>
      {pageRows.length ? (
        <ul className="reports-panel reports-list">
          {pageRows.map((report) => {
            const href = reportPath("/reports/" + encodeURIComponent(report.id), params, {})
              + (params.get("focus") === "remediation" ? "#report-findings" : "");
            return (
              <li key={report.id}>
                <Link className="reports-row" navigate={navigate} href={href}>
                  <span className="reports-row-icon"><FileText size={19} aria-hidden="true" /></span>
                  <span className="reports-row-info">
                    <strong dir="auto">{(report.source || report.input_artifact) ? sourceLabel(t, report.source || report.input_artifact) : t.report}</strong>
                    <small>{dateText(lang, report.created_at)}</small>
                  </span>
                  <span className="reports-row-status">
                    <span className="reports-tag">{label(t, report.status || "completed")}</span>
                    <small>{count(report.unique_count ?? report.finding_count ?? 0)} {t.results}</small>
                  </span>
                  {lang === "ar" ? <ArrowLeft size={17} aria-hidden="true" /> : <ArrowRight size={17} aria-hidden="true" />}
                </Link>
              </li>
            );
          })}
        </ul>
      ) : <div className="reports-panel reports-state">{t.noMatches}</div>}
      {pages > 1 && (
        <nav className="reports-pagination" aria-label={t.reports}>
          <button className="reports-button" disabled={page <= 1} onClick={() => pageTo(page - 1)}>{t.prev}</button>
          <span>{t.page} {count(page)} {t.of} {count(pages)}</span>
          <button className="reports-button" disabled={page >= pages} onClick={() => pageTo(page + 1)}>{t.next}</button>
        </nav>
      )}
    </>
  );
}

function FindingList({ findings, coverage, imported, priority, t, lang, params, pathname, hash, navigate }) {
  const [selected, select] = useState(null);
  const [revealed, setRevealed] = useState(null);
  const count = (value) => numberFormats[lang].format(value);
  const query = params.get("finding") ?? "";
  const severity = params.get("findingSeverity") ?? "";
  const domain = params.get("findingDomain") ?? "";
  const active = Boolean(query || severity || domain);
  const findingsPath = (changes) => reportPath(pathname, params, changes) + hash;
  const update = (name, value) => navigate(findingsPath({ [name]: value }), { replace: name === "finding" });
  const titleOf = (finding) => (lang === "ar" ? finding.title_ar : finding.title) || finding.title || finding.rule;
  const remediationOf = (finding) => (lang === "ar" ? finding.remediation_ar : finding.remediation) || finding.remediation;
  const grouped = new Map();
  for (const finding of findings) {
    const matched = lower([finding.rule, finding.title, finding.title_ar, finding.evidence, finding.path, finding.line].join(" ")).includes(lower(query.trim()))
      && (!severity || finding.severity === severity)
      && (!domain || finding.domain === domain);
    if (!matched) continue;
    if (!grouped.has(finding.rule)) grouped.set(finding.rule, []);
    grouped.get(finding.rule).push(finding);
  }
  const rank = { high: 0, medium: 1, low: 2 };
  const suggested = new Map((priority || []).map((rule, index) => [rule, index]));
  const groups = [...grouped.values()].sort(([first], [second]) =>
    (suggested.get(first.rule) ?? suggested.size) - (suggested.get(second.rule) ?? suggested.size)
    || (rank[first.severity] ?? 3) - (rank[second.severity] ?? 3) || first.rule.localeCompare(second.rule));
  const stepping = revealed !== null;
  const shown = stepping ? groups.slice(0, revealed) : groups;
  const advance = () => setRevealed((value) => Math.min((value ?? 0) + 1, groups.length));
  useEffect(() => {
    if (!stepping || selected) return undefined;
    const onKey = (event) => {
      if (event.target.closest?.("input, select, textarea, button")) return;
      if (event.key === "ArrowRight" || event.key === "ArrowLeft" || event.key === " ") {
        event.preventDefault();
        const forward = event.key === " " || event.key === (lang === "ar" ? "ArrowLeft" : "ArrowRight");
        setRevealed((value) => Math.max(0, Math.min((value ?? 0) + (forward ? 1 : -1), groups.length)));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [stepping, selected, groups.length, lang]);
  return (
    <section className="reports-panel reports-section">
      {findings.length ? (
        <>
          <div className="reports-present" role="group" aria-label={t.present}>
            {!stepping
              ? <button type="button" className="reports-button" onClick={() => setRevealed(0)}>{t.present}</button>
              : <>
                <button type="button" className="reports-button reports-primary" onClick={advance} disabled={revealed >= groups.length}>{t.presentNext}</button>
                <button type="button" className="reports-button" onClick={() => setRevealed(0)}>{t.presentRestart}</button>
                <button type="button" className="reports-button" onClick={() => setRevealed(null)}>{t.presentAll}</button>
                <span className="reports-count" role="status">{t.presentProgress}: {count(shown.length)} / {count(groups.length)}</span>
              </>}
          </div>
          {suggested.size > 0 && <p className="reports-annotation">{t.modelOrder}</p>}
            <div className="reports-filters" id="report-filters" role="group" aria-label={t.filter}>
              <SearchFilter name="finding" value={query} update={update} title={t.searchFindings} placeholder={t.filterHint} />
              <SelectFilter t={t} title={t.severity} name="findingSeverity" value={severity} options={findings.map((entry) => entry.severity)} update={update} />
              <SelectFilter t={t} title={t.domain} name="findingDomain" value={domain} options={findings.map((entry) => entry.domain)} update={update} />
              {active && <button className="reports-button" onClick={() => navigate(findingsPath({ finding: "", findingSeverity: "", findingDomain: "" }))}>{t.reset}</button>}
            </div>
          {active && <p className="reports-count" role="status">{count(groups.length)} {t.results}</p>}
          {!groups.length && <p className="reports-empty">{t.noFindingsMatches}</p>}
          {shown.map((group) => {
            const first = group[0];
            return (
              <article className="reports-finding reports-finding-row" data-rule={first.rule} key={first.rule}>
                <div className="reports-finding-context">
                  <span className="reports-finding-title"><strong>{titleOf(first)}</strong></span>
                  <span className="reports-tags">
                    <span className="reports-tag" data-severity={first.severity}>{label(t, first.severity)}</span>
                    {importedFromZap(first) && <span className="reports-tag">{t.importedZap}</span>}
                    {group.length > 1 && <span className="reports-tag">{count(group.length)} {t.occurrences}</span>}
                  </span>
                </div>
                <button type="button" className="reports-button" onClick={() => select(group)}
                  aria-label={t.viewEvidence + " · " + titleOf(first)}>{t.viewEvidence}</button>
              </article>
            );
          })}
          {selected && <ReportDialog lang={lang} title={titleOf(selected[0])} onClose={() => select(null)}>
                <div className="reports-finding-body">
                  <div className="reports-fix">
                    <h3>{t.remediation}</h3>
                    <p dir="auto">{remediationOf(selected[0]) || t.unavailable}</p>
                  </div>
                  <h3>{t.evidence}</h3>
                  <ul>
                    {selected.map((occurrence, i) => (
                      <li key={occurrence.line + "-" + i}>
                        <span>{occurrence.path && <><bdi>{occurrence.path}</bdi> · </>}
                          {importedFromZap(occurrence) || occurrence.domain === "api" ? t.document
                            : t.line + " " + (occurrence.line == null ? t.unavailable : count(occurrence.line))}</span>
                        <code dir="ltr">{occurrence.evidence || t.unavailable}</code>
                        <small className="reports-annotation">
                          {t.confidence} · {label(t, occurrence.confidence)}
                          {occurrence.assessment ? " · " + label(t, occurrence.assessment) : ""}
                        </small>
                      </li>
                    ))}
                  </ul>
                  <p className="reports-annotation">
                    <code dir="ltr">{selected[0].rule}</code> · {label(t, selected[0].domain)}
                  </p>
                </div>
          </ReportDialog>}
        </>
      ) : (
        <p className="reports-empty">
          {imported ? t.noImportedZap : coverage?.length && coverage.every((rule) => rule.status === "not_applicable")
            ? t.noApplicable
            : coverage == null ? t.unavailable : t.zeroFindings}
        </p>
      )}
    </section>
  );
}

function CoverageDetails({ coverage, t, count }) {
  if (!coverage?.length) return <p className="reports-empty">{t.legacyCoverage}</p>;
  return (
    <div className="reports-table-wrap">
      <table className="reports-coverage" aria-label={t.coverage}>
        <thead><tr>{[t.rule, t.domain, t.status, t.occurrences].map((title) => <th key={title} scope="col">{title}</th>)}</tr></thead>
        <tbody>
          {coverage.map((entry) => (
            <tr key={entry.rule}>
              <th scope="row"><code dir="ltr">{entry.rule}</code></th>
              <td>{label(t, entry.domain)}</td>
              <td><span className="reports-tag">{label(t, entry.status)}</span></td>
              <td>{count(entry.match_count)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Provenance({ projectApi, reportId, t, lang, count }) {
  const url = projectApi.slice(0, -"/reports".length) + "/scans/" + encodeURIComponent(reportId) + "/provenance";
  const [state, setState] = useState(null);
  const [attempt, retry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    fetch(url, { signal: controller.signal })
      .then((response) => {
        if (response.status === 404) return null;
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then((data) => { if (!controller.signal.aborted) setState({ attempt, data }); },
        () => { if (!controller.signal.aborted) setState({ attempt, error: true }); });
    return () => controller.abort();
  }, [url, attempt]);

  const current = state?.attempt === attempt ? state : null;
  const data = current?.data;
  const intake = data?.snapshot?.profile;
  const website = intake?.mode === "website";
  const intakeLabels = lang === "ar" ? {
    field: "المدخل", zip: "رفع ZIP", github: "لقطة GitHub", website: "صفحة HTTPS",
    scope: "التغطية", websiteScope: "استجابات الصفحات المعتمدة والمتاحة للعامة",
    sourceScope: "الملفات النصية المدعومة في اللقطة", expanded: "بصمة المحتوى النصي",
    textFiles: "ملفات اتفحصت", skipped: "ملفات اتخطّت", page: "الصفحة المرصودة",
  } : {
    field: "Input", zip: "ZIP upload", github: "GitHub snapshot", website: "HTTPS page",
    scope: "Coverage", websiteScope: "Responses from approved public pages",
    sourceScope: "Supported text files in the snapshot", expanded: "Extracted text fingerprint",
    textFiles: "Included files", skipped: "Skipped files", page: "Observed page",
  };
  const fields = data && [
    [intakeLabels.field, intakeLabels[intake?.mode]],
    [intakeLabels.scope, intake && (website ? intakeLabels.websiteScope : intakeLabels.sourceScope)],
    [intakeLabels.page, intake?.public_url],
    ["TLS", intake?.tls_version],
    [intakeLabels.textFiles, Number.isInteger(intake?.text_files) && count(intake.text_files)],
    [intakeLabels.skipped, Number.isInteger(intake?.skipped_files) && count(intake.skipped_files)],
    [intakeLabels.expanded, intake?.expanded_text_sha256],
    [t.snapshotHash, data.snapshot?.sha256],
    [t.policyHash, data.scope?.sha256],
    [t.profile, data.scope?.profile],
    [t.asset, data.asset?.reference],
    [t.linkedRepository, data.snapshot?.github?.repository],
    [t.linkedCommit, data.snapshot?.github?.commit],
    [t.rawExpiry, data.snapshot?.raw_expires_at && dateText(lang, data.snapshot.raw_expires_at)],
    [t.records, Number.isInteger(data.evidence_count) && count(data.evidence_count)],
  ].filter(([, value]) => value !== undefined && value !== null && value !== false && value !== "");
  return (
    <section className="reports-section reports-advanced">
      <h2>{t.provenance}</h2>
      {!current && <p className="reports-annotation" role="status">{t.provenanceLoading}</p>}
      {current?.error && <div className="reports-inline-state">
        <p role="alert">{t.provenanceError}</p>
        <button type="button" className="reports-button" onClick={() => retry((value) => value + 1)}>{t.retry}</button>
      </div>}
      {current && !current.error && !fields?.length && <p className="reports-empty">{t.provenanceUnavailable}</p>}
      {!!fields?.length && <dl className="reports-metadata">
        {fields.map(([title, value]) => <div key={title}><dt>{title}</dt><dd dir="auto">{value}</dd></div>)}
      </dl>}
    </section>
  );
}

function TechnicalDetails({ report, lang, t, count, projectApi }) {
  const metrics = report.metrics || {};
  const source = report.source || report.input_artifact;
  const cards = [
    [t.enrichment, enrichLabel(t, report.enrichment)],
    [t.model, modelLabel(t, report)],
    [t.modelCalls, metrics.modelCalls == null ? t.unavailable : count(metrics.modelCalls)],
    [t.duration, metrics.durationMs == null ? t.unavailable : count(metrics.durationMs / 1000) + " " + t.seconds],
  ];
  const sourceDetails = [
    source?.bytes != null ? count(source.bytes) + " " + t.bytes : "",
    source?.lines != null ? count(source.lines) + " " + t.lines : "",
    source?.encoding,
  ].filter(Boolean).join(" · ");
  if (sourceDetails) cards.push([t.sourceDetails, sourceDetails]);
  const inventory = report.api_inventory;
  const apiCounts = inventory && [
    [t.apiVersion, inventory.version],
    [t.apiOperations, inventory.operations],
    [t.apiAuth, inventory.declared_auth],
    [t.apiAnonymous, inventory.anonymous_operations],
    [t.apiReferences, inventory.local_references],
    [t.apiUnresolved, inventory.unresolved_references],
    [t.apiUnresolvedSecurity, inventory.unresolved_security_requirements],
    [t.apiSchemes, Object.entries(inventory.security_schemes || {}).map(([scheme, value]) => scheme + " · " + count(value)).join(" / ") || null],
  ];
  return (
    <>
      <dl className="reports-metadata">
        {cards.map(([title, value]) => <div key={title}><dt>{title}</dt><dd dir="auto">{value}</dd></div>)}
      </dl>
      {apiCounts && <section className="reports-section reports-advanced">
        <h2>{t.api}</h2>
        <dl className="reports-metadata">
          {apiCounts.filter(([, value]) => value != null).map(([title, value]) => (
            <div key={title}><dt>{title}</dt><dd dir="auto">{typeof value === "number" ? count(value) : value}</dd></div>
          ))}
        </dl>
      </section>}
      {report.ruleset_version && <p className="reports-annotation">
        <bdi>{report.ruleset_version}</bdi> · {t.policyVersion} {report.policy_version}
      </p>}
      <p className="reports-annotation">{t.summarySource} · {label(t, report.summary_source ? report.summary_source + "Summary" : null)}</p>
      {metrics.benchmark && (
        <p className="reports-annotation">
          {t.benchmark} · {count(metrics.benchmark.matched)} / {count(metrics.benchmark.expected)} · {count(metrics.benchmark.unexpected)} {t.unexpected}
        </p>
      )}
      {projectApi && <Provenance projectApi={projectApi} reportId={report.id} t={t} lang={lang} count={count} />}
      {report.execution && <section className="reports-section reports-advanced">
        <h2>{t.snapshotVerification}</h2>
        <dl className="reports-metadata">
          <div><dt>{t.verifiedFiles}</dt><dd>{count(report.execution.files_read)}</dd></div>
          <div><dt>{t.verifiedLocations}</dt><dd>{count(report.execution.validated_locations)}</dd></div>
          <div><dt>{t.snapshotSha256}</dt><dd><code dir="ltr">{report.execution.source_sha256}</code></dd></div>
        </dl>
      </section>}
      {report.agent_advisory && <section className="reports-section reports-advanced">
        <h2>{t.agentAdvisory}</h2>
        <p className="reports-annotation">{t.advisoryNote}</p>
        <dl className="reports-metadata">
          {[
            [t.advisoryPlanning, report.agent_advisory.planning, (item) => `${label(t, item.label)} · ${item.tool}`],
            [t.advisoryValidation, report.agent_advisory.validation, (item) => `${label(t, item.label)} · ${String(item.fingerprint).slice(0, 12)}`],
            [t.advisoryExplanation, report.agent_advisory.explanation, (item) => `${label(t, item.label)} · ${String(item.fingerprint).slice(0, 12)}`],
          ].filter(([, items]) => items?.length).map(([title, items, format]) => (
            <div key={title}><dt>{title}</dt><dd dir="auto">{items.map(format).join(" · ")}</dd></div>
          ))}
        </dl>
      </section>}
      {report.review_context?.length > 0 && <section className="reports-section reports-advanced">
        <h2>{t.priorReviews}</h2>
        <p className="reports-annotation">{t.priorReviewsNote}</p>
        <dl className="reports-metadata">
          {report.review_context.map((item, i) => (
            <div key={`${item.prior_scan_id}-${item.fingerprint}-${i}`}>
              <dt><code dir="ltr">{String(item.fingerprint).slice(0, 12)}</code></dt>
              <dd dir="auto">{label(t, item.status)} · <code dir="ltr">{item.prior_scan_id}</code></dd>
            </div>
          ))}
        </dl>
      </section>}
      {(projectApi || report.task_runs?.length > 0) && (
        <ToolRuns runs={report.task_runs} selections={report.tool_selection} lang={lang} t={t} label={label} count={count} />
      )}
      <section className="reports-section reports-advanced">
        <h2>{t.steps}</h2>
        {report.steps?.length ? (
          <ol className="reports-events">
            {report.steps.map((step, i) => {
              const [role, branch] = (step.node || "").split(":");
              const title = agents[role]?.[lang === "ar" ? 0 : 1] || role;
              const detail = lang === "en" ? step.detail_en || step.detail : step.detail;
              return (
                <li key={step.occurred_at + "-" + i}>
                  <strong>{title}{branch && <code dir="ltr"> · {branch}</code>}</strong>
                  <span className="reports-tag">{label(t, step.status)}</span>
                  <span>{step.source === "model" ? t.model : label(t, step.source)}</span>
                  {step.occurred_at && <time dateTime={step.occurred_at}>{dateText(lang, step.occurred_at)}</time>}
                  {detail && <p dir="auto">{detail}</p>}
                </li>
              );
            })}
          </ol>
        ) : <p className="reports-empty">{t.noSteps}</p>}
      </section>
    </>
  );
}

function Decision({ findings, coverage, applied, t, lang, count, coverageHref, navigate }) {
  const rank = { high: 0, medium: 1, low: 2 };
  const byRule = new Map();
  for (const finding of findings) if (!byRule.has(finding.rule)) byRule.set(finding.rule, finding);
  const top = [...byRule.values()].sort((a, b) => (rank[a.severity] ?? 3) - (rank[b.severity] ?? 3) || a.rule.localeCompare(b.rule)).slice(0, 3);
  const total = coverage.length;
  const notChecked = coverage.filter(({ status }) => status !== "matched" && status !== "clear").length;
  const headline = !byRule.size ? t.decisionClear : byRule.size === 1 ? t.decisionFixOne : `${count(byRule.size)} ${t.decisionFix}`;
  const titleOf = (finding) => (lang === "ar" ? finding.title_ar : finding.title) || finding.title || finding.rule;
  return (
    <section className="reports-decision" aria-labelledby="report-decision-title" data-clear={!byRule.size || undefined}>
      <div className="reports-decision-head">
        <p className="reports-decision-kicker" id="report-decision-title">{t.decisionTitle}</p>
        <p className="reports-decision-headline">{headline}</p>
      </div>
      {!!top.length && <ol className="reports-decision-fixes" aria-label={t.decisionFirst}>
        {top.map((finding) => (
          <li key={finding.rule}>
            <span className="reports-decision-sev" data-severity={finding.severity}>{label(t, finding.severity)}</span>
            <span className="reports-decision-fix"><b>{titleOf(finding)}</b>
              {finding.path && <bdi dir="ltr" className="reports-decision-where">{finding.path}{finding.line ? `:${finding.line}` : ""}</bdi>}</span>
          </li>
        ))}
      </ol>}
      {!!total && <p className="reports-decision-cover">
        <b>{count(applied)}</b> {t.decisionCovered} <b>{count(total)}</b>
        {!!notChecked && <> · <a href={coverageHref} onClick={(event) => routeLink(event, coverageHref, navigate)}>{count(notChecked)} {t.decisionNotChecked}</a></>}
      </p>}
      <p className="reports-decision-caution">{t.decisionCaution}</p>
    </section>
  );
}

function ReportDetails({ report, t, lang, params, pathname, hash, navigate, reportApi, projectApi }) {
  const count = (value) => numberFormats[lang].format(value);
  const findings = report.findings || [];
  const coverage = report.coverage || [];
  const applied = report.imported_evidence ? report.metrics?.checksRun ?? 0
    : coverage.filter(({ status }) => status === "matched" || status === "clear").length;
  const coverageGaps = coverage.some(({ status }) => status === "skipped" || status === "error");
  const source = report.source || report.input_artifact;
  const summary = lang === "ar" ? report.summary_ar : report.summary_en;
  const downloads = [
    [`format=pdf&lang=${lang === "ar" ? "en" : "ar"}`, t.alternatePdf],
    ["lang=ar", t.downloadAr],
    ["lang=en", t.downloadEn],
    ["format=json", t.json],
  ];
  const baseline = params.get("baseline");
  const linkable = projectApi && ["repository", "har", "zap", "openapi"].includes(source?.kind);
  const sections = [
    ["findings", t.results],
    ["coverage", t.coverage],
    ...(projectApi ? [["compare", t.compareTitle], ["review", t.reviewTitle]] : []),
    ...(linkable ? [["links", t.linkedEvidence]] : []),
    ["technical", t.technical],
    ["export", t.moreFormats],
  ];
  const requestedSection = hash.startsWith("#report-") ? hash.slice("#report-".length) : "";
  const section = sections.some(([id]) => id === requestedSection)
    ? requestedSection : projectApi && baseline && baseline !== report.id ? "compare" : "findings";
  const sectionPath = (id, changes = {}) => reportPath(pathname, params, changes) + "#report-" + id;
  const stats = [
    [t.findingTypes, count(new Set(findings.map(({ rule }) => rule)).size)],
    [t.occurrences, count(findings.length)],
    [t.rulesApplied, coverage.length ? count(applied) : t.unavailable],
  ];

  return (
    <>
      <Decision findings={findings} coverage={coverage} applied={applied} t={t} lang={lang} count={count}
        coverageHref={sectionPath("coverage")} navigate={navigate} />
      <section className="reports-overview reports-panel" id="report-summary" aria-labelledby="report-overview-title">
        <div className="reports-overview-main">
          <div className="reports-overview-mark"><FileCheck2 aria-hidden="true" size={22} /></div>
          <div className="reports-overview-copy">
            <h2 id="report-overview-title">{t.executive}</h2>
            <p className="reports-overview-source"><bdi>{sourceLabel(t, source)}</bdi></p>
            <div className="reports-overview-context">
              <time dateTime={report.created_at}>{dateText(lang, report.created_at)}</time>
              <span className="reports-tag" data-report-status={report.status || "completed"}>{label(t, report.status || "completed")}</span>
            </div>
          </div>
        </div>
        <dl className="reports-overview-stats">
          {stats.map(([title, value]) => <div key={title}><dt>{title}</dt><dd>{value}</dd></div>)}
        </dl>
        <p className="reports-overview-scope">{report.input_artifact ? t.projectScope : t.scopeText}</p>
        {!!coverageGaps && <p className="reports-caution">{t.incompleteCoverage}</p>}
        {!coverage.length && summary && <p className="reports-copy" dir="auto">{summary}</p>}
      </section>
      <nav className="reports-section-nav" aria-label={t.sections}>
        {sections.map(([id, title]) => (
          <Link key={id} href={sectionPath(id)} navigate={navigate} aria-current={id === section ? "location" : undefined}
            data-report-section={id}>{title}</Link>
        ))}
      </nav>
      <section className="reports-section-page" id={"report-" + section} tabIndex={-1} aria-label={sections.find(([id]) => id === section)[1]}>
        {section === "findings" && <>
          <ImportedEvidence evidence={report.imported_evidence} lang={lang} count={count} />
          <FindingList findings={findings} coverage={report.coverage} imported={report.imported_evidence}
            priority={report.enrichment === "model" ? report.priority : null} t={t} lang={lang}
            params={params} pathname={pathname} hash={hash} navigate={navigate} />
        </>}
        {section === "coverage" && <div className="reports-panel reports-section">
          <FileManifest entries={report.input_manifest} lang={lang} />
          <CoverageDetails coverage={coverage} t={t} count={count} />
        </div>}
        {section === "compare" && <ReportComparison report={report} reportApi={reportApi} archiveApi={projectApi}
          baseline={baseline !== report.id ? baseline : null}
          onBaselineChange={(value) => navigate(sectionPath("compare", { baseline: value }))}
          lang={lang} t={t} count={count} dateText={dateText} sourceLabel={sourceLabel} />}
        {section === "review" && <FindingReview reportApi={reportApi} findings={findings} lang={lang} t={t} dateText={dateText} />}
        {section === "links" && <LinkedEvidence reportApi={reportApi} lang={lang} count={count}
          formatDate={(value) => dateText(lang, value)}
          hrefFor={(id) => reportPath("/reports/" + encodeURIComponent(id), new URLSearchParams(), { project: params.get("project"), lang })}
          follow={(event, href) => routeLink(event, href, navigate)} />}
        {section === "export" && <div className="reports-panel reports-section">
          <div className="reports-downloads">
            {downloads.map(([query, title]) => (
              <a className="reports-button" key={query} href={`${reportApi}/download?${query}`} download>
                <ArrowDownToLine size={16} aria-hidden="true" />{title}
              </a>
            ))}
          </div>
        </div>}
        {section === "technical" && <div className="reports-panel reports-section">
          <TechnicalDetails report={report} lang={lang} t={t} count={count} projectApi={projectApi} />
        </div>}
      </section>
    </>
  );
}

function useReportProjects(enabled) {
  const [state, setState] = useState(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!enabled) return;
    const controller = new AbortController();
    async function load() {
      const result = await fetch("/api/platform/projects", { signal: controller.signal });
      if (result.status === 401 || result.status === 503) return { projects: [], guest: true };
      if (!result.ok) throw new Error("Failed to load projects");
      return result.json();
    }
    load().then((data) => {
      if (!controller.signal.aborted) setState(data);
    }, () => {
      if (!controller.signal.aborted) setState({ error: true });
    });
    return () => controller.abort();
  }, [enabled, retry]);
  return [state, () => { setState(null); setRetry((value) => value + 1); }];
}

function ReportContext({ location, navigate, lang, active, state, retry }) {
  const params = new URLSearchParams(location.search);
  const project = params.get("project") || "";
  const ar = lang === "ar";
  const t = copy[lang];
  const select = (value) => navigate(reportPath(location.pathname, new URLSearchParams(), {
    lang: params.get("lang") || "", project: value, q: params.get("q") || "", focus: params.get("focus") || "",
  }));
  if (!state) return <p role="status" className="reports-panel reports-state">{ar ? "جاري تحميل المشاريع…" : "Loading projects…"}</p>;
  if (state.error) return <div className="reports-panel reports-state">
    <p role="alert">{ar ? "تعذّر تحميل المشاريع." : "Could not load projects."}</p>
    <button className="reports-button" onClick={retry}>{t.retry}</button>
  </div>;
  if (state.guest) return active ? <div className="reports-panel reports-state">
    <p>{ar ? "سجّل الدخول لعرض تقارير المشاريع." : "Sign in to see project reports."}</p>
    <Link className="reports-button reports-primary" href={"/signin?next=" + encodeURIComponent(location.pathname + location.search)} navigate={navigate}>{ar ? "تسجيل الدخول" : "Sign in"}</Link>
  </div> : null;
  return <section className="reports-panel reports-section report-context" aria-label={ar ? "مصدر التقارير" : "Report source"}>
    <label>{ar ? "المشروع" : "Project"}
      <select value={project} onChange={(event) => select(event.target.value)}>
        <option value="">{ar ? "اختار مشروعًا" : "Choose a project"}</option>
        {!state.projects.some((item) => item.id === project) && project && <option value={project} disabled>{ar ? "مشروع غير متاح" : "Unavailable project"}</option>}
        {state.projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>
    {state.projects.length === 0 && <Link className="reports-button" href="/projects" navigate={navigate}>{ar ? "إنشاء مشروع" : "Create a project"}</Link>}
  </section>;
}

export function Reports({ location, navigate, lang: preferredLanguage = "ar", session, personal }) {
  const { pathname, search, hash } = location;
  const params = new URLSearchParams(search);
  const locale = params.get("lang");
  const lang = locale === "ar" || locale === "en" ? locale : preferredLanguage;
  const t = copy[lang];
  const id = /^\/reports\/([^/]+)\/?$/.exec(pathname)?.[1];
  const project = params.get("project");
  const projectApi = /^[a-f0-9]{32}$/.test(project ?? "") ? `/api/platform/projects/${project}/reports` : null;
  const lookup = Boolean(personal && id && !project);
  const [projects, retryProjects] = useReportProjects(!id || lookup);
  const [lookedUp, setLookedUp] = useState(false);
  const badProject = Boolean((project || (personal && id && lookedUp)) && !projectApi);
  const guestProject = Boolean((projectApi || personal) && (session.user === null || projects?.guest));
  const archive = projectApi;
  const url = guestProject || badProject || lookup ? null : id ? (projectApi || "/api/reports") + "/" + encodeURIComponent(id) : archive;
  const [state, setState] = useState(null);
  const [retry, reload] = useState(0);
  const heading = useRef(null);
  const current = state?.url === url && state.retry === retry ? state : null;
  const scanProject = projects?.projects?.find((item) => item.id === project && item.role !== "viewer");
  const showNewScan = !personal && !id && !guestProject && (scanProject || (!project && projects?.projects?.some((item) => item.role !== "viewer")));

  // Reports belong to a project and the project lives in the URL. A link without it (typed or shared by hand)
  // is resolved here by asking the user's own projects which one holds the report.
  useEffect(() => {
    if (!lookup || !projects?.projects) return;
    const controller = new AbortController();
    (async () => {
      for (const item of projects.projects.slice(0, 25)) {
        try {
          const result = await fetch(`/api/platform/projects/${item.id}/reports/${encodeURIComponent(id)}`, { signal: controller.signal });
          if (result.ok) { navigate(reportPath(pathname, params, { project: item.id }) + hash, { replace: true }); return; }
        } catch { if (controller.signal.aborted) return; }
      }
      if (!controller.signal.aborted) setLookedUp(true);
    })();
    return () => controller.abort();
  }, [lookup, projects, id]);
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    fetchJson(url, { signal: controller.signal }).then(
      (data) => { if (!controller.signal.aborted) setState({ url, retry, data }); },
      (error) => { if (!controller.signal.aborted) setState({ url, retry, error: error.message }); },
    );
    return () => controller.abort();
  }, [url, retry]);
  useEffect(() => { if (!hash.startsWith("#report-")) heading.current?.focus(); }, [pathname]);
  useEffect(() => {
    if (current?.data && hash.startsWith("#report-") && document.activeElement === document.body) {
      document.getElementById(hash.slice(1))?.focus();
    }
  }, [current, hash]);

  const back = reportPath("/reports", params, { finding: "", findingSeverity: "", findingDomain: "", baseline: "" });
  const showReportActions = Boolean(id && current?.data);
  return (
    <section className="reports-workspace" lang={lang} dir={lang === "ar" ? "rtl" : "ltr"}>
      <header className="reports-heading">
        <div>
          {id && <Link className="reports-back" href={back} navigate={navigate}>{lang === "ar" ? <ArrowRight size={17} aria-hidden="true" /> : <ArrowLeft size={17} aria-hidden="true" />}{t.back}</Link>}
          <h1 tabIndex={-1} ref={heading}>{id ? (projectApi ? t.projectReport : t.report)
            : params.get("focus") === "remediation" ? t.remediation : t.reports}</h1>
          {!id && params.get("focus") === "remediation" &&
            <p>{lang === "ar" ? "افتحي تقريرًا لمراجعة توصيات الإصلاح لكل نتيجة." : "Open a report to review the recommended fix for each finding."}</p>}
        </div>
        {showReportActions && <div className="report-header-actions">
          <div className="report-language" role="group" aria-label={lang === "ar" ? "لغة التقرير" : "Report language"}>
            {["ar", "en"].map((language) => <Link key={language} lang={language}
              href={reportPath(pathname, params, { lang: language }) + hash} navigate={navigate}
              aria-current={lang === language ? "true" : undefined}>{language === "ar" ? "العربية" : "English"}</Link>)}
          </div>
          <a className="reports-button reports-primary reports-pdf" href={`${url}/download?format=pdf&lang=${lang}`} download>
            <ArrowDownToLine size={18} aria-hidden="true" />{t.pdf}
          </a>
        </div>}
        {showNewScan && <Link className="reports-button reports-primary" navigate={navigate}
          href={scanProject ? reportPath("/new-scan", new URLSearchParams(), { project }) : "/new-scan"}>{t.newScan}</Link>}
      </header>
      {!id && <ReportContext location={location} navigate={navigate} lang={lang} active={Boolean(project)}
        state={projects} retry={retryProjects} />}
      {id && guestProject && <div className="reports-panel reports-state">
        <p>{lang === "ar" ? "سجّل الدخول لعرض تقرير المشروع." : "Sign in to see this project report."}</p>
        <Link className="reports-button reports-primary" href={"/signin?next=" + encodeURIComponent(location.pathname + location.search)} navigate={navigate}>{lang === "ar" ? "تسجيل الدخول" : "Sign in"}</Link>
      </div>}
      {badProject && <div className="reports-panel reports-state" role="alert">
        <p>{project ? (lang === "ar" ? "المشروع المطلوب غير متاح." : "The requested project is unavailable.")
          : (lang === "ar" ? "مفيش تقرير بالرقم ده في مشاريعك. افتح التقرير من قائمة تقارير المشروع." : "No report with this ID in your projects. Open it from the project's report list.")}</p>
        <Link className="reports-button" href="/reports" navigate={navigate}>{lang === "ar" ? "تقارير المشاريع" : "Project reports"}</Link>
      </div>}
      {(url || (lookup && !lookedUp)) && !current && <div className="reports-panel reports-state" role="status">{t.loading}</div>}
      {current?.error && (
        <div className="reports-panel reports-state">
          <p role="alert" dir="auto">{lang === "ar" ? current.error : t.loadError}</p>
          <button className="reports-button" onClick={() => reload((value) => value + 1)}>{t.retry}</button>
        </div>
      )}
      {!id && projectApi && !personal && !guestProject && session.user &&
        <ClaimableLabReports projectApi={projectApi} archiveReports={current?.data?.reports || []} t={t} lang={lang}
          onClaimed={() => reload((value) => value + 1)} />}
      {current?.data && (id
        ? <ReportDetails key={id + ":" + (project || "")} report={current.data} t={t} lang={lang} params={params} pathname={pathname} hash={hash} navigate={navigate} reportApi={url} projectApi={projectApi} />
        : <Archive reports={current.data.reports || []} t={t} lang={lang} params={params} navigate={navigate} />)}
    </section>
  );
}
