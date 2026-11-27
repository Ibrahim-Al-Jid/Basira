import React from "react";
import {
  Activity, ArrowDownRight, ArrowLeft, ArrowRight, AudioLines, Boxes,
  Braces, Check, Cloud, Code2, FileCheck2, FileSearch, GitBranch, Globe2,
  Layers3, ScanLine, ShieldCheck, SlidersHorizontal, Workflow,
} from "lucide-react";
import "./landing.css";

const domains = [
  { id: "html", icon: Code2, names: ["أمان HTML", "HTML security"] },
  { id: "web", icon: Globe2, names: ["المتصفح والاستجابات", "Browser & responses"] },
  { id: "dependencies", icon: Boxes, names: ["التبعيات", "Dependencies"] },
  { id: "infrastructure", icon: Cloud, names: ["البنية التحتية", "Infrastructure"] },
  { id: "ci", icon: GitBranch, names: ["مسارات CI/CD", "CI/CD pipelines"] },
  { id: "application", icon: SlidersHorizontal, names: ["إعدادات التطبيق", "Application configuration"] },
  { id: "source", icon: Braces, names: ["كود المصدر (PHP وJS وPython)", "Source code (PHP, JS, Python)"] },
];

const content = {
  ar: {
    eyebrow: "منصة مراجعة أمنية للمشاريع",
    headline: ["أمّن مشروعك.", "ابدأ من الدليل."],
    lead: "افحص ملفات مشروعك، وشوف المشاكل الأمنية وأدلتها وتوصيات إصلاحها في تقرير واحد.",
    start: "ابدأ مشروعك",
    graphicLabel: "تصوّر توضيحي للفحص",
    pipeline: "مسار تحليل الأدلة", active: "عرض توضيحي",
    inputs: "مدخلات التحليل", reviewing: "تحليل الأدلة", output: "التقرير",
    inputFile: "ملف المشروع", reportFile: "الأدلة والتغطية", ready: "جاهز للعرض",
    coverage: "مجالات الفحص",
    workflowTag: "طريقة العمل", workflowTitle: "من الملف إلى قرار واضح.",
    workflow: [
      ["اختار المصدر", "ارفع HTML، لقطة من الكود بصيغة ZIP، ملف HAR أو إعدادات JSON."],
      ["تابع الفحص", "تابع الأدلة وهي بتتحلل والقواعد اللي انطبقت على مدخلك."],
      ["راجع التقرير", "راجع أدلة النتائج وتوصيات الإصلاح، وصدّر التقرير أو قارنه بفحص سابق."],
    ],
  },
  en: {
    eyebrow: "Project security review",
    headline: ["Secure your project.", "Start with evidence."],
    lead: "Review your project files for security issues. See the evidence and suggested fixes in one report.",
    start: "Start a project",
    graphicLabel: "Illustration of a scan",
    pipeline: "Evidence pipeline", active: "Illustrative preview",
    inputs: "Scan input", reviewing: "Evidence analysis", output: "Report",
    inputFile: "Project artifact", reportFile: "Evidence and coverage", ready: "Ready to review",
    coverage: "Coverage domains",
    workflowTag: "How it works", workflowTitle: "From a file to a clear decision.",
    workflow: [
      ["Choose a source", "Upload HTML, a ZIP snapshot of your code, a HAR capture, or a JSON configuration."],
      ["Follow the scan", "See the stages of analysis and which checks applied to the source you chose."],
      ["Review the report", "Inspect evidence and suggested fixes, export a report, or compare it to an earlier scan."],
    ],
  },
};

const steps = [FileSearch, Workflow, FileCheck2];

function PipelinePreview({ copy }) {
  return (
    <figure className="landing-visual" aria-label={copy.graphicLabel}>
      <div className="landing-board">
        <header className="landing-board-header">
          <span><Activity size={16} /> {copy.pipeline}</span>
          <span className="landing-preview-label"><span aria-hidden="true" />{copy.active}</span>
        </header>
        <div className="landing-board-body">
          <div className="landing-grid-lines" />
          <div className="landing-radar" aria-hidden="true">
            <span className="landing-radar-circle landing-radar-outer" />
            <span className="landing-radar-circle landing-radar-middle" />
            <span className="landing-radar-circle landing-radar-inner" />
            <span className="landing-radar-sweep" />
            <span className="landing-radar-center"><ShieldCheck size={31} strokeWidth={1.6} /></span>
            <span className="landing-mailbox landing-mailbox-first"><Braces size={16} /></span>
            <span className="landing-mailbox landing-mailbox-last"><ScanLine size={16} /></span>
            <span className="landing-radar-blip" />
          </div>
          <div className="landing-stage landing-stage-input">
            <div className="landing-stage-icon"><Layers3 size={17} /></div>
            <div><strong>{copy.inputs}</strong><small>{copy.inputFile}</small></div>
          </div>
          <div className="landing-stage landing-stage-output">
            <div className="landing-stage-icon"><FileCheck2 size={17} /></div>
            <div><strong>{copy.output}</strong><small>{copy.reportFile}</small></div>
          </div>
        </div>
        <footer className="landing-board-footer">
          <span><AudioLines size={17} /> {copy.reviewing}</span>
          <span><Check size={15} /> {copy.ready}</span>
        </footer>
      </div>
    </figure>
  );
}

function CoverageDomains({ copy, language, personal }) {
  if (personal) return (
    <section className="landing-coverage" aria-labelledby="landing-coverage-title">
      <div className="landing-inner">
        <h2 id="landing-coverage-title">{copy.coverage}</h2>
        <ul className="landing-domain-grid">
          {domains.map(({ id, names, icon: Icon }) => (
            <li key={id}><Icon size={20} aria-hidden="true" />{names[language]}</li>
          ))}
        </ul>
      </div>
    </section>
  );
  const group = (duplicate) => (
    <ul aria-hidden={duplicate || undefined} className="landing-marquee-group">
      {domains.map(({ id, names, icon: Icon }) => (
        <li key={id} dir={language ? "ltr" : "rtl"}><Icon size={18} aria-hidden="true" /> {names[language]}</li>
      ))}
    </ul>
  );
  return (
    <section className="landing-coverage" aria-labelledby="landing-coverage-title">
      <div className="landing-inner landing-coverage-heading">
        <h2 id="landing-coverage-title">{copy.coverage}</h2>
      </div>
      <div className="landing-marquee" dir="ltr">
        <div className="landing-marquee-track">
          {group(false)}{group(true)}
        </div>
      </div>
    </section>
  );
}

export function Landing({ follow, lang, theme, authenticated, personal }) {
  const language = lang === "en" ? 1 : 0;
  const copy = language ? content.en : content.ar;
  const workflow = personal ? [
    language ? ["Choose a source", "Upload a source ZIP. GitHub and authorized website evidence are planned."]
      : ["اختار المصدر", "ارفع كود المشروع بصيغة ZIP. ربط GitHub وجمع أدلة الموقع قيد التجهيز."],
    ...copy.workflow.slice(1),
  ] : copy.workflow;
  const start = authenticated ? "/projects" : personal ? "/signin?mode=register" : "/signin";
  const Arrow = language ? ArrowRight : ArrowLeft;
  return (
    <div className="basira-landing" data-landing-theme={theme || "dark"} data-personal={personal || undefined}
      lang={language ? "en" : "ar"} dir={language ? "ltr" : "rtl"}>
      <section className="landing-hero landing-inner" aria-labelledby="landing-title">
        <div className="landing-intro">
          <p className="landing-eyebrow"><span aria-hidden="true" />{copy.eyebrow}</p>
          <h1 id="landing-title">{copy.headline[0]}<br /><em>{copy.headline[1]}</em></h1>
          <p className="landing-lead">{copy.lead}</p>
          <div className="landing-actions">
            <a className="landing-button landing-primary" href={start} onClick={(event) => follow(event, start)}>
              {authenticated ? (language ? "Open projects" : "افتح مشاريعي") : copy.start} <Arrow size={19} aria-hidden="true" />
            </a>
          </div>
        </div>
        <PipelinePreview copy={copy} />
      </section>
      <CoverageDomains copy={copy} language={language} personal={personal} />
      <section className="landing-inner landing-workflow" id="workflow" aria-labelledby="landing-workflow-title">
        <div className="landing-section-head">
          {!personal && <p className="landing-eyebrow"><span aria-hidden="true" />{copy.workflowTag}</p>}
          <h2 id="landing-workflow-title">{personal ? copy.workflowTag : copy.workflowTitle}</h2>
        </div>
        <ol className="landing-steps">
          {workflow.map(([title, detail], index) => {
            const Icon = steps[index];
            return (
              <li key={title}>
                <div className="landing-step-top"><Icon size={24} aria-hidden="true" />{!personal && <ArrowDownRight size={20} aria-hidden="true" />}</div>
                <h3>{title}</h3><p>{detail}</p>
              </li>
            );
          })}
        </ol>
      </section>
    </div>
  );
}
