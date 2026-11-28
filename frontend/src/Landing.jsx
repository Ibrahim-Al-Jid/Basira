import React, { useState } from "react";
import {
  Activity, Braces, Bug, Cloud, FileCheck2, Folder, GitBranch, Globe2, Grid2X2, History,
  Layers3, ScanLine, Search, Settings, ShieldCheck, SlidersHorizontal, TriangleAlert, Workflow, Zap,
} from "lucide-react";
import { WorkspaceBrand } from "./SiteHeader";
import { CommandActivity, CommandMetrics, CoverageGauge, ReviewAgents, RiskDistribution } from "./CommandOverview";

const domains = [
  ["أمان HTML", "HTML security", "بنية الصفحة والنماذج", "Page structure and forms"],
  ["المتصفح والاستجابات", "Browser & responses", "سياسات الاستجابات والترويسات", "Response policies and headers"],
  ["التبعيات", "Dependencies", "المكتبات والحزم", "Libraries and packages"],
  ["البنية التحتية", "Infrastructure", "ملفات البناء والتشغيل", "Build and runtime files"],
  ["مسارات CI/CD", "CI/CD pipelines", "إعدادات التكامل والنشر", "Integration and deployment configuration"],
  ["إعدادات التطبيق", "Application configuration", "ملفات الضبط", "Configuration files"],
  ["كود المصدر", "Source code", "JavaScript وPython وPHP", "JavaScript, Python, and PHP"],
];

const steps = [
  [Folder, "اختاري مصدر المشروع", "Choose a project source", "حددي الملفات اللي هتتراجع.", "Select the files to review."],
  [ScanLine, "تابعي تحليل الأدلة", "Follow the evidence review", "شوفي القواعد اللي اتطبّقت على الملفات.", "See which checks applied to your files."],
  [FileCheck2, "راجعي التقرير", "Review the report", "افتحي الأدلة وتوصيات الإصلاح.", "Open the evidence and suggested fixes."],
];

const coverageIcons = [Braces, Globe2, Layers3, Cloud, GitBranch, SlidersHorizontal, Braces];
const exampleWeeks = [
  [[5, 2], [8, 4], [6, 3]],
  [[10, 5], [7, 2], [12, 6]],
  [[8, 3], [9, 5], [6, 2]],
  [[11, 4], [9, 3], [12, 5]],
];

function ActivityPreview({ t, number }) {
  const [selected, setSelected] = useState(0);
  const weeks = selected ? [exampleWeeks[selected - 1]] : exampleWeeks;
  const [reviews, findings] = weeks.flat().reduce(
    ([reviews, findings], [review, finding]) => [reviews + review, findings + finding], [0, 0],
  );
  return (
    <figure className="overview-card overview-chart">
      <figcaption>
        <strong><Activity size={19} aria-hidden="true" />{t("نشاط الفحوصات", "Assessment activity")}</strong>
        <span className="overview-pill">{t("عرض توضيحي", "Demo data")}</span>
      </figcaption>
      <div className="overview-chart-summary" aria-live="polite">
        <div><strong>{number(reviews)}</strong><span>{t("فحص مكتمل", "Completed scans")}</span></div>
        <div><strong>{number(findings)}</strong><span>{t("نتيجة موثّقة", "Verified findings")}</span></div>
      </div>
      <div className="overview-chart-area" aria-hidden="true">
        <div className="overview-chart-axis">{[12, 9, 6, 3, 0].map((tick) => <span key={tick}>{number(tick)}</span>)}</div>
        <div className="overview-chart-plot" data-single={Boolean(selected)}>
          {weeks.map((week, index) => (
            <div className="overview-chart-week" key={selected || index}>
              {week.map(([review, finding], day) => (
                <div className="overview-chart-pair" key={day}>
                  <span style={{ blockSize: (review / 12 * 100) + "%" }} />
                  <span style={{ blockSize: (finding / 12 * 100) + "%" }} />
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="overview-chart-filters" role="group" aria-label={t("الفترة المعروضة", "Displayed period")}>
        <button type="button" aria-pressed={!selected} onClick={() => setSelected(0)}>{t("الكل", "All")}</button>
        {exampleWeeks.map((_, index) => {
          const week = index + 1;
          return <button type="button" key={week} aria-pressed={selected === week} onClick={() => setSelected(week)}>
            {t("الأسبوع " + number(week), "Week " + week)}
          </button>;
        })}
      </div>
    </figure>
  );
}

function CoverageDirectory({ follow, t }) {
  const [query, setQuery] = useState("");
  const filter = query.trim().toLocaleLowerCase();
  const rows = domains.map((domain, index) => ({ domain, Icon: coverageIcons[index] }))
    .filter(({ domain }) => domain.some((field) => field.toLocaleLowerCase().includes(filter)));
  return (
    <section className="overview-card overview-coverage" id="coverage" aria-labelledby="overview-coverage-title">
      <div className="overview-section-head">
        <h2 id="overview-coverage-title">{t("مجالات الفحص", "Coverage domains")}</h2>
        <label className="overview-search">
          <Search size={16} aria-hidden="true" />
          <input type="search" value={query} onChange={(event) => setQuery(event.target.value)}
            aria-label={t("ابحثي في مجالات الفحص", "Search coverage domains")}
            placeholder={t("ابحثي في التغطية…", "Search coverage…")} />
        </label>
      </div>
      <table aria-labelledby="overview-coverage-title">
        <thead><tr><th scope="col">{t("المجال", "Domain")}</th><th scope="col">{t("أمثلة على التغطية", "Coverage examples")}</th></tr></thead>
        <tbody>
          {rows.map(({ domain: [ar, en, arDetail, enDetail], Icon }) => (
            <tr key={en}>
              <th scope="row"><span className="overview-domain"><Icon size={17} aria-hidden="true" />{t(ar, en)}</span></th>
              <td>{t(arDetail, enDetail)}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={2} role="status">{t("مفيش مجالات مطابقة للبحث.", "No matching coverage domains.")}</td></tr>}
        </tbody>
      </table>
      <a className="overview-text-link" href="/reports" onClick={(event) => follow(event, "/reports")}>{t("افتحي التقارير", "Open reports")}</a>
    </section>
  );
}

export function OverviewSidebar({ lang, follow, location, personal }) {
  const t = (ar, en) => lang === "ar" ? ar : en;
  const { pathname, hash } = location;
  const home = pathname === "/";
  const scanPath = personal === false ? "/demo" : "/new-scan";
  const links = [
    [Grid2X2, "/", t("نظرة عامة", "Overview")],
    [Folder, "/projects", t("المشاريع", "Projects")],
    [ScanLine, scanPath, t("فحص جديد", "New scan")],
    ...(home ? [
      [Workflow, "#agents", t("فريق المراجعة", "Review agents")],
    ] : []),
    [FileCheck2, "/reports", t("التقارير", "Reports")],
    [History, "/scans", t("سجل الفحوصات", "Scan history")],
    [Settings, "/settings", t("الإعدادات", "Settings")],
  ];
  return (
    <aside className="overview-sidebar">
      <WorkspaceBrand href="/" follow={follow} lang={lang} />
      <nav className="overview-nav" aria-label={t("التنقل الرئيسي", "Main navigation")}>
        {links.map(([Icon, path, label]) => (
          <a key={path} href={path} aria-label={label} title={label}
            aria-current={path === hash ? "location"
              : (path === pathname && (!home || !hash)) ? "page" : undefined}
            onClick={path.startsWith("#") ? undefined : (event) => follow(event, path)}>
            <Icon size={18} aria-hidden="true" />
            <span>{label}</span>
          </a>
        ))}
      </nav>
    </aside>
  );
}

export function Landing({ follow, lang, authenticated, personal }) {
  const t = (ar, en) => lang === "ar" ? ar : en;
  const number = (value) => value.toLocaleString(lang === "ar" ? "ar-EG" : "en");
  const start = !personal ? "/demo" : authenticated ? "/new-scan" : "/signin?mode=register";
  const sampleRisk = { high: 5, medium: 17, low: 12 };
  const sampleScans = [
    [t("متجر إلكتروني", "E-commerce store"), "completed", 8, t("دقيقتان و١٤ ثانية", "2m 14s")],
    [t("بوابة الشركة", "Company portal"), "running", 3, t("دقيقة و٣٢ ثانية", "1m 32s")],
    [t("واجهة العملاء", "Customer portal"), "completed", 12, t("٣ دقائق و٢٠ ثانية", "3m 20s")],
  ];
  const metrics = [
    { icon: ShieldCheck, label: t("تغطية الفحص", "Review coverage"), value: number(92) + "%", points: [18, 22, 28, 24, 41, 38, 54, 47, 70, 65, 83, 92] },
    { icon: Folder, tone: "blue", label: t("المشاريع", "Total projects"), value: number(12), points: [1, 1, 3, 2, 4, 5, 5, 7, 6, 8, 12, 12] },
    { icon: Bug, tone: "red", label: t("إجمالي النتائج", "Total findings"), value: number(34), points: [2, 4, 4, 8, 14, 10, 19, 22, 18, 29, 30, 34] },
    { icon: TriangleAlert, tone: "amber", label: t("نتائج عالية الخطورة", "High severity issues"), value: number(sampleRisk.high), points: [0, 0, 1, 2, 1, 3, 2, 4, 3, 5, 4, 5] },
    { icon: ScanLine, tone: "blue", label: t("فحوصات نشطة", "Active scans"), value: number(1), points: [0, 1, 1, 2, 1, 3, 2, 1, 3, 2, 1, 1] },
  ];
  return (
    <div className="security-overview">
      <section className="command-hero" aria-labelledby="landing-title">
        <div>
          <h1 id="landing-title">{t("أهلًا بيك في بصيرة", "Welcome to BASIRA")}</h1>
          <p>{t("لوحة أمان المشاريع · بيانات توضيحية", "Project security overview · Demo data")}</p>
        </div>
        <a className="overview-primary" href={start} onClick={(event) => follow(event, start)}>
          <Zap size={18} aria-hidden="true" />
          {t("فحص جديد", "New scan")}
        </a>
      </section>

      <CommandMetrics metrics={metrics} />

      <div className="command-panels">
        <CoverageGauge t={t} number={number} cover={{ ran: 105, total: 114 }} example />
        <RiskDistribution t={t} number={number} counts={sampleRisk} example />
        <ReviewAgents t={t} lang={lang} overview />
      </div>

      <div className="command-lower">
        <section className="overview-card command-panel command-recent">
          <header className="command-panel-head">
            <h2>{t("أحدث الفحوصات", "Recent scans")}</h2>
            <a href="/scans" onClick={(event) => follow(event, "/scans")}>{t("عرض الكل", "View all")}</a>
          </header>
          <div className="command-table-wrap">
            <table className="command-table">
              <thead><tr><th scope="col">{t("المشروع", "Project")}</th><th scope="col">{t("الحالة", "Status")}</th>
                <th scope="col">{t("النتائج", "Findings")}</th><th scope="col">{t("المدة", "Duration")}</th></tr></thead>
              <tbody>{sampleScans.map(([name, state, findings, duration]) => (
                <tr key={name}><th scope="row"><span className="command-scan-name"><Globe2 size={17} aria-hidden="true" />{name}</span></th>
                  <td><span className="workspace-badge" data-state={state}>{state === "completed" ? t("مكتمل", "Completed") : t("قيد التنفيذ", "Running")}</span></td>
                  <td>{number(findings)}</td><td>{duration}</td></tr>
              ))}</tbody>
            </table>
          </div>
        </section>
        <CommandActivity t={t} historyHref="/scans" events={[
          { id: "complete", state: "completed", title: t("اكتمل فحص المتجر الإلكتروني", "E-commerce scan completed"), detail: t("من دقيقتين", "2 minutes ago") },
          { id: "finding", state: "failed", title: t("اتسجّلت نتيجة عالية الخطورة", "A high-severity finding was recorded"), detail: t("من ٣ دقايق", "3 minutes ago") },
          { id: "analysis", state: "running", title: t("بدأ تحليل ملفات بوابة الشركة", "Company portal analysis started"), detail: t("من ٥ دقايق", "5 minutes ago") },
          { id: "report", title: t("تقرير واجهة العملاء جاهز للمراجعة", "Customer portal report ready"), detail: t("من ٧ دقايق", "7 minutes ago") },
        ]} />
      </div>

      <div className="overview-panels">
        <ActivityPreview t={t} number={number} />

        <section className="overview-card overview-workflow" id="workflow" aria-labelledby="overview-workflow-title">
          <h2 id="overview-workflow-title">{t("سير الفحص", "Review workflow")}</h2>
          <ol>
            {steps.map(([Icon, ar, en, arDetail, enDetail]) => (
              <li key={en}>
                <span className="overview-step-icon"><Icon size={19} aria-hidden="true" /></span>
                <div><strong>{t(ar, en)}</strong><p>{t(arDetail, enDetail)}</p></div>
              </li>
            ))}
          </ol>
          <a href="/scans" onClick={(event) => follow(event, "/scans")}>
            {t("سجل الفحوصات", "Scan history")}
          </a>
        </section>
      </div>

      <CoverageDirectory follow={follow} t={t} />
    </div>
  );
}
