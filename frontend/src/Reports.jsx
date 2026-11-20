import React, { useEffect, useRef, useState } from "react";
import { ArrowDownToLine, ArrowLeft, ArrowRight, FileText, Search } from "lucide-react";
import { agents, fetchJson } from "./data";
import { FindingReview, ReportComparison, ToolRuns } from "./ReportAdvanced";
import "./reports.css";

const PAGE_SIZE = 10;

const copy = {
  ar: {
    reports: "سجل التقارير",
    report: "تقرير فحص HTML",
    projectReport: "تقرير فحص المشروع",
    archiveIntro: "راجع فحوصات HTML المحفوظة وافتح الأدلة والإصلاحات.",
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
    noSteps: "أحداث التشغيل غير متاحة للتقرير ده.",
    line: "سطر",
    lines: "سطر",
    bytes: "بايت",
    confidence: "الثقة",
    evidence: "الدليل",
    remediation: "الإصلاح",
    executive: "الملخص",
    coverage: "تغطية الفحص",
    steps: "أحداث الوكلاء",
    summarySource: "مصدر الملخص",
    modelSummary: "قالب مرصد بترتيب الموديل",
    systemSummary: "قالب مرصد",
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
    sarif: "تحميل SARIF",
    downloadAr: "تحميل HTML عربي",
    downloadEn: "تحميل HTML إنجليزي",
    benchmark: "نتيجة العينة المرجعية",
    unexpected: "إضافية",
  },
  en: {
    reports: "Reports",
    report: "HTML review report",
    projectReport: "Project review report",
    archiveIntro: "Open saved HTML reviews to see their evidence and fixes.",
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
    noSteps: "Execution events are unavailable for this report.",
    line: "Line",
    lines: "lines",
    bytes: "bytes",
    confidence: "Confidence",
    evidence: "Evidence",
    remediation: "Remediation",
    executive: "Summary",
    coverage: "Scan coverage",
    steps: "Agent events",
    summarySource: "Summary source",
    modelSummary: "Marsad template with model prioritization",
    systemSummary: "Marsad template",
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
    sarif: "Download SARIF",
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
        <Link className="reports-button reports-primary" navigate={navigate} href="/">{t.newScan}</Link>
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
            const href = reportPath("/reports/" + encodeURIComponent(report.id), params, {});
            return (
              <li key={report.id}>
                <Link className="reports-row" navigate={navigate} href={href}>
                  <span className="reports-row-icon"><FileText size={19} aria-hidden="true" /></span>
                  <span className="reports-row-info">
                    <strong dir="auto">{(report.source || report.input_artifact) ? sourceLabel(t, report.source || report.input_artifact) : t.report}</strong>
                    <small>{dateText(lang, report.created_at)} · <bdi>{modelLabel(t, report)}</bdi></small>
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

function FindingList({ findings, coverage, t, lang, params, pathname, navigate }) {
  const count = (value) => numberFormats[lang].format(value);
  const query = params.get("finding") ?? "";
  const severity = params.get("findingSeverity") ?? "";
  const domain = params.get("findingDomain") ?? "";
  const active = Boolean(query || severity || domain);
  const update = (name, value) => navigate(reportPath(pathname, params, { [name]: value }), { replace: name === "finding" });
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
  const groups = [...grouped.values()].sort(([first], [second]) =>
    (rank[first.severity] ?? 3) - (rank[second.severity] ?? 3) || first.rule.localeCompare(second.rule));
  return (
    <section className="reports-panel reports-section">
      <h2>{t.results}</h2>
      {findings.length ? (
        <>
          <div className="reports-filters" role="group" aria-label={t.filter}>
            <SearchFilter name="finding" value={query} update={update} title={t.searchFindings} placeholder={t.filterHint} />
            <SelectFilter t={t} title={t.severity} name="findingSeverity" value={severity} options={findings.map((entry) => entry.severity)} update={update} />
            <SelectFilter t={t} title={t.domain} name="findingDomain" value={domain} options={findings.map((entry) => entry.domain)} update={update} />
            {active && <button className="reports-button" onClick={() => navigate(reportPath(pathname, params, { finding: "", findingSeverity: "", findingDomain: "" }))}>{t.reset}</button>}
          </div>
          <p className="reports-count" role="status">{count(groups.length)} {t.results}</p>
          {!groups.length && <p className="reports-empty">{t.noFindingsMatches}</p>}
          {groups.map((group) => {
            const first = group[0];
            return (
              <details className="reports-finding" key={first.rule}>
                <summary>
                  <span className="reports-finding-title">
                    <strong>{titleOf(first)}</strong>
                    <code dir="ltr">{first.rule}</code>
                  </span>
                  <span className="reports-tags">
                    <span className="reports-tag" data-severity={first.severity}>{label(t, first.severity)}</span>
                    <span className="reports-tag">{label(t, first.domain)}</span>
                    <span className="reports-tag">{count(group.length)} {t.occurrences}</span>
                  </span>
                </summary>
                <div className="reports-finding-body">
                  <p className="reports-annotation">
                    {t.confidence} · {label(t, first.confidence)}
                    {first.assessment ? " · " + label(t, first.assessment) : ""}
                  </p>
                  <h3>{t.evidence}</h3>
                  <ul>
                    {group.map((occurrence, i) => (
                      <li key={occurrence.line + "-" + i}>
                        <span>{occurrence.path && <><bdi>{occurrence.path}</bdi> · </>}
                          {t.line} {occurrence.line == null ? t.unavailable : count(occurrence.line)}</span>
                        <code dir="ltr">{occurrence.evidence || t.unavailable}</code>
                      </li>
                    ))}
                  </ul>
                  <h3>{t.remediation}</h3>
                  <p dir="auto">{remediationOf(first) || t.unavailable}</p>
                </div>
              </details>
            );
          })}
        </>
      ) : (
        <p className="reports-empty">
          {coverage?.length && coverage.every((rule) => rule.status === "not_applicable")
            ? t.noApplicable
            : coverage == null ? t.unavailable : t.zeroFindings}
        </p>
      )}
    </section>
  );
}

function ReportDetails({ report, t, lang, params, pathname, navigate, reportApi, projectApi }) {
  const count = (value) => numberFormats[lang].format(value);
  const findings = report.findings || [];
  const metrics = report.metrics || {};
  const summary = lang === "ar" ? report.summary_ar : report.summary_en;
  const source = report.source || report.input_artifact;
  const downloads = [
    ["lang=ar", t.downloadAr], ["lang=en", t.downloadEn], ["format=json", t.json],
  ];
  if (projectApi) downloads.push([`format=sarif&lang=${lang}`, t.sarif]);
  const requestedBaseline = params.get("baseline");
  const baseline = requestedBaseline !== report.id ? requestedBaseline : null;
  const metadata = [
    [t.source, sourceLabel(t, source)],
    [t.date, dateText(lang, report.created_at)],
    [t.status, label(t, report.status || "completed")],
    [t.enrichment, enrichLabel(t, report.enrichment)],
    [t.model, modelLabel(t, report)],
  ];
  const sourceDetails = [
    source?.bytes != null ? count(source.bytes) + " " + t.bytes : "",
    source?.lines != null ? count(source.lines) + " " + t.lines : "",
    source?.encoding,
  ].filter(Boolean).join(" · ");
  if (sourceDetails) metadata.push([t.sourceDetails, sourceDetails]);
  const cards = [
    [t.results, count(new Set(findings.map((item) => item.rule)).size)],
    [t.occurrences, count(findings.length)],
    [t.modelCalls, metrics.modelCalls == null ? t.unavailable : count(metrics.modelCalls)],
    [t.duration, metrics.durationMs == null ? t.unavailable : count(metrics.durationMs / 1000) + " " + t.seconds],
  ];
  return (
    <>
      <div className="reports-downloads">
        {downloads.map(([query, title]) => (
          <a className="reports-button" key={query} href={`${reportApi}/download?${query}`} download>
            <ArrowDownToLine size={16} aria-hidden="true" />{title}
          </a>
        ))}
      </div>
      <section className="reports-panel reports-section">
        <h2>{t.scope}</h2>
        <p className="reports-copy">{report.input_artifact ? t.projectScope : t.scopeText}</p>
        {report.ruleset_version && <p className="reports-annotation">
          <bdi>{report.ruleset_version}</bdi> · {lang === "ar" ? "إصدار السياسة" : "Policy version"} {report.policy_version}
        </p>}
        {!!report.priority?.length && <p className="reports-annotation">
          {lang === "ar" ? "ترتيب الأولويات بالموديل" : "Model-suggested priorities"} · <bdi>{report.priority.join(", ")}</bdi>
        </p>}
        <dl className="reports-metadata">
          {metadata.map(([key, value], index) => (
            <div key={key + index}><dt>{key}</dt><dd dir="auto">{value}</dd></div>
          ))}
        </dl>
      </section>
      <section className="reports-panel reports-section">
        <h2>{t.executive}</h2>
        <p className="reports-copy" dir="auto">{summary || t.unavailable}</p>
        <p className="reports-annotation">{t.summarySource} · {label(t, report.summary_source ? report.summary_source + "Summary" : null)}</p>
        <dl className="reports-metadata reports-metrics">
          {cards.map(([key, value]) => (
            <div key={key}><dt>{key}</dt><dd>{value}</dd></div>
          ))}
        </dl>
        {metrics.benchmark && (
          <p className="reports-annotation">
            {t.benchmark} · {count(metrics.benchmark.matched)} / {count(metrics.benchmark.expected)} · {count(metrics.benchmark.unexpected)} {t.unexpected}
          </p>
        )}
      </section>
      <FindingList findings={findings} coverage={report.coverage} t={t} lang={lang} params={params} pathname={pathname} navigate={navigate} />
      {projectApi && (
        <>
          <ReportComparison report={report} reportApi={reportApi} archiveApi={projectApi}
            baseline={baseline} onBaselineChange={(value) => navigate(reportPath(pathname, params, { baseline: value }))}
            lang={lang} t={t} count={count} dateText={dateText} sourceLabel={sourceLabel} />
          <FindingReview reportApi={reportApi} findings={findings} lang={lang} t={t} dateText={dateText} />
        </>
      )}
      <section className="reports-panel reports-section">
        <h2>{t.coverage}</h2>
        {report.coverage?.length ? (
          <ul className="reports-coverage">
            {report.coverage.map((entry) => (
              <li key={entry.rule}>
                <code dir="ltr">{entry.rule}</code>
                <span>{label(t, entry.domain)}</span>
                <span className="reports-tag">{label(t, entry.status)}</span>
                <span>{count(entry.match_count ?? 0)} {t.occurrences}</span>
              </li>
            ))}
          </ul>
        ) : <p className="reports-empty">{t.legacyCoverage}</p>}
      </section>
      {(projectApi || report.task_runs?.length > 0) && (
        <ToolRuns runs={report.task_runs} lang={lang} t={t} label={label} count={count} />
      )}
      <section className="reports-panel reports-section">
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

export function Reports({ location, navigate, revision }) {
  const { pathname, search } = location;
  const params = new URLSearchParams(search);
  const lang = params.get("lang") === "en" ? "en" : "ar";
  const t = copy[lang];
  const id = /^\/reports\/([^/]+)\/?$/.exec(pathname)?.[1];
  const project = params.get("project");
  const projectApi = /^[a-f0-9]{32}$/.test(project ?? "") ? `/api/platform/projects/${project}/reports` : null;
  const url = id ? (projectApi || "/api/reports") + "/" + id : (projectApi || "/api/history");
  const archiveRevision = id ? null : revision;
  const [state, setState] = useState(null);
  const [retry, reload] = useState(0);
  const heading = useRef(null);
  const current = state?.url === url && state.retry === retry && state.archiveRevision === archiveRevision ? state : null;

  useEffect(() => {
    const controller = new AbortController();
    fetchJson(url, { signal: controller.signal }).then(
      (data) => { if (!controller.signal.aborted) setState({ url, retry, archiveRevision, data }); },
      (error) => { if (!controller.signal.aborted) setState({ url, retry, archiveRevision, error: error.message }); },
    );
    return () => controller.abort();
  }, [url, retry, archiveRevision]);
  useEffect(() => { heading.current?.focus(); }, [pathname]);

  const back = reportPath("/reports", params, { finding: "", findingSeverity: "", findingDomain: "", baseline: "" });
  return (
    <section className="reports-workspace" lang={lang} dir={lang === "ar" ? "rtl" : "ltr"}>
      {id && <Link className="reports-back" href={back} navigate={navigate}>{lang === "ar" ? <ArrowRight size={17} aria-hidden="true" /> : <ArrowLeft size={17} aria-hidden="true" />}{t.back}</Link>}
      <div className="reports-heading">
        <div>
          <h1 tabIndex={-1} ref={heading}>{id ? (projectApi ? t.projectReport : t.report) : t.reports}</h1>
          {!id && <p>{t.archiveIntro}</p>}
        </div>
        <div className="reports-switch" aria-label={lang === "ar" ? "لغة التقرير" : "Report language"} role="group">
          {["ar", "en"].map((locale) => (
            <button key={locale} lang={locale} aria-pressed={lang === locale} onClick={() => navigate(reportPath(pathname, params, { lang: locale === "ar" ? "" : locale }))}>
              {locale === "ar" ? "العربية" : "English"}
            </button>
          ))}
        </div>
      </div>
      {!current && <div className="reports-panel reports-state" role="status">{t.loading}</div>}
      {current?.error && (
        <div className="reports-panel reports-state">
          <p role="alert" dir="auto">{lang === "ar" ? current.error : t.loadError}</p>
          <button className="reports-button" onClick={() => reload((value) => value + 1)}>{t.retry}</button>
        </div>
      )}
      {current?.data && (id ? (
        <ReportDetails report={current.data} t={t} lang={lang} params={params} pathname={pathname} navigate={navigate} reportApi={url} projectApi={projectApi} />
      ) : <Archive reports={current.data.reports || []} t={t} lang={lang} params={params} navigate={navigate} />)}
    </section>
  );
}
