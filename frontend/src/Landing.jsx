import React, { useState } from "react";
import {
  Activity, ArrowDownRight, ArrowLeft, ArrowRight, ArrowUpRight, AudioLines, Boxes,
  Braces, Check, CircleDot, Cloud, Code2, FileCheck2, FileSearch, GitBranch, Globe2,
  Layers3, Pause, Play, ScanLine, ShieldCheck, SlidersHorizontal, Workflow,
} from "lucide-react";
import "./landing.css";

const domains = [
  { id: "html", icon: Code2, names: ["أمان HTML", "HTML security"] },
  { id: "web", icon: Globe2, names: ["المتصفح والاستجابات", "Browser & responses"] },
  { id: "dependencies", icon: Boxes, names: ["التبعيات", "Dependencies"] },
  { id: "infrastructure", icon: Cloud, names: ["البنية التحتية", "Infrastructure"] },
  { id: "ci", icon: GitBranch, names: ["مسارات CI/CD", "CI/CD pipelines"] },
  { id: "application", icon: SlidersHorizontal, names: ["إعدادات التطبيق", "Application configuration"] },
];

const content = {
  ar: {
    eyebrow: "منصة مراجعة أمنية للمشاريع",
    headline: ["أمّن مشروعك.", "ابدأ من الدليل."],
    lead: "افحص ملفات مشروعك، وشوف المشاكل الأمنية وأدلتها وتوصيات إصلاحها في تقرير واحد.",
    start: "ابدأ مشروعك", demo: "جرّب العرض",
    graphicLabel: "تصوّر توضيحي للفحص",
    pipeline: "مسار تحليل الأدلة", active: "عرض توضيحي",
    inputs: "مدخلات التحليل", reviewing: "تحليل الأدلة", output: "التقرير",
    inputFile: "ملف المشروع", reportFile: "الأدلة والتغطية", ready: "جاهز للعرض",
    catalog: "قاعدة فحص", category: "مجالات أمنية", analysts: "أدوار تحليل",
    coverage: "مجالات الفحص", pause: "أوقف الحركة", resume: "شغّل الحركة", allChecks: "استكشف كتالوج الفحوصات",
    workflowTag: "طريقة العمل", workflowTitle: "من الملف إلى قرار واضح.",
    workflow: [
      ["اختار المصدر", "ارفع HTML، لقطة من الكود بصيغة ZIP، ملف HAR أو إعدادات JSON."],
      ["تابع الفحص", "تابع الأدلة وهي بتتحلل والقواعد اللي انطبقت على مدخلك."],
      ["راجع التقرير", "راجع أدلة النتائج وتوصيات الإصلاح، وصدّر التقرير أو قارنه بفحص سابق."],
    ],
    validation: "التقييم الداخلي", validationTitle: "نقيس على حالات مرجعية.",
    intro: "أرقام التقييم جاية من حالات اختبار اصطناعية مرجعية. التغطية في تقريرك بتعتمد على نوع الملفات والقواعد المنطبقة عليها.",
    metricLabels: ["حالة مرجعية", "قاعدة انطبقت", "عينة زمنية"],
    metricCopy: [
      "المجموعة بتجمع حالات متوقعة عشان نقارن نتائج الفحص بمرجع معروف.",
      "عدد القواعد اللي انطبقت على الأقل مرة في مجموعة التقييم دي.",
      "كل حالة مرجعية اتنفذت ٣ مرات للحصول على عينات توقيت للمحرك.",
    ],
    closingTitle: "جاهز تراجع مشروعك؟", closingCopy: "ابدأ بملف من مشروعك واستلم تقرير قابل للمراجعة.",
  },
  en: {
    eyebrow: "Project security review",
    headline: ["Secure your project.", "Start with evidence."],
    lead: "Review your project files for security issues. See the evidence and suggested fixes in one report.",
    start: "Start a project", demo: "Explore the demo",
    graphicLabel: "Illustration of a scan",
    pipeline: "Evidence pipeline", active: "Illustrative preview",
    inputs: "Scan input", reviewing: "Evidence analysis", output: "Report",
    inputFile: "Project artifact", reportFile: "Evidence and coverage", ready: "Ready to review",
    catalog: "Security checks", category: "Security domains", analysts: "Analysis roles",
    coverage: "Coverage domains", pause: "Pause motion", resume: "Play motion", allChecks: "Explore the check catalog",
    workflowTag: "How it works", workflowTitle: "From a file to a clear decision.",
    workflow: [
      ["Choose a source", "Upload HTML, a ZIP snapshot of your code, a HAR capture, or a JSON configuration."],
      ["Follow the scan", "See the stages of analysis and which checks applied to the source you chose."],
      ["Review the report", "Inspect evidence and suggested fixes, export a report, or compare it to an earlier scan."],
    ],
    validation: "Internal evaluation", validationTitle: "Measured on reference cases.",
    intro: "These figures describe synthetic reference fixtures. Your report coverage depends on the files you provide and the checks that apply.",
    metricLabels: ["Reference cases", "Applicable checks", "Timing samples"],
    metricCopy: [
      "The fixture set provides expected results for comparison with the engine's observations.",
      "The number of checks that applied at least once across this particular evaluation set.",
      "Each reference case ran three times to collect timing samples for the analysis engine.",
    ],
    closingTitle: "Ready to review your project?", closingCopy: "Start with one file and get a report you can review.",
  },
};

const steps = [FileSearch, Workflow, FileCheck2];
const metrics = [18, 25, 54];

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

function CoverageTicker({ copy, language, follow, paused, onToggleMotion }) {
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
        <div>
          <h2 id="landing-coverage-title">{copy.coverage}</h2>
          <a className="landing-text-link" href="/checks" onClick={(event) => follow(event, "/checks")}>
            {copy.allChecks} <ArrowUpRight size={15} aria-hidden="true" />
          </a>
        </div>
        <button
          className="landing-motion-control"
          type="button"
          onClick={onToggleMotion}
        >
          {paused ? <Play size={15} /> : <Pause size={15} />}
          <span>{paused ? copy.resume : copy.pause}</span>
        </button>
      </div>
      <div className="landing-marquee" dir="ltr">
        <div className="landing-marquee-track">
          {group(false)}{group(true)}
        </div>
      </div>
    </section>
  );
}

export function Landing({ follow, lang, theme }) {
  const language = lang === "en" ? 1 : 0;
  const copy = language ? content.en : content.ar;
  const Arrow = language ? ArrowRight : ArrowLeft;
  const format = new Intl.NumberFormat(language ? "en" : "ar-EG");
  const [metric, setMetric] = useState(0);
  const [paused, setPaused] = useState(false);
  return (
    <div className="marsad-landing" data-landing-theme={theme || "dark"} data-motion={paused ? "paused" : "playing"}
      lang={language ? "en" : "ar"} dir={language ? "ltr" : "rtl"}>
      <section className="landing-hero landing-inner" aria-labelledby="landing-title">
        <div className="landing-intro">
          <p className="landing-eyebrow"><span aria-hidden="true" />{copy.eyebrow}</p>
          <h1 id="landing-title">{copy.headline[0]}<br /><em>{copy.headline[1]}</em></h1>
          <p className="landing-lead">{copy.lead}</p>
          <div className="landing-actions">
            <a className="landing-button landing-primary" href="/projects" onClick={(event) => follow(event, "/projects")}>
              {copy.start} <Arrow size={19} aria-hidden="true" />
            </a>
            <a className="landing-button landing-secondary" href="/demo" onClick={(event) => follow(event, "/demo")}>
              <Play size={16} aria-hidden="true" /> {copy.demo}
            </a>
          </div>
          <dl className="landing-hero-stats">
            {[[100, copy.catalog], [6, copy.category], [5, copy.analysts]].map(([number, label]) => (
              <div key={number}><dt>{label}</dt><dd>{format.format(number)}</dd></div>
            ))}
          </dl>
        </div>
        <PipelinePreview copy={copy} />
      </section>
      <CoverageTicker copy={copy} language={language} follow={follow} paused={paused} onToggleMotion={() => setPaused((value) => !value)} />
      <section className="landing-inner landing-workflow" id="workflow" aria-labelledby="landing-workflow-title">
        <div className="landing-section-head">
          <p className="landing-eyebrow"><span aria-hidden="true" />{copy.workflowTag}</p>
          <h2 id="landing-workflow-title">{copy.workflowTitle}</h2>
        </div>
        <ol className="landing-steps">
          {copy.workflow.map(([title, detail], index) => {
            const Icon = steps[index];
            return (
              <li key={title}>
                <div className="landing-step-top"><Icon size={24} aria-hidden="true" /><ArrowDownRight size={20} aria-hidden="true" /></div>
                <h3>{title}</h3><p>{detail}</p>
              </li>
            );
          })}
        </ol>
      </section>
      <section className="landing-inner landing-benchmark" id="evaluation" aria-labelledby="landing-benchmark-title">
        <div className="landing-section-head">
          <p className="landing-eyebrow"><span aria-hidden="true" />{copy.validation}</p>
          <h2 id="landing-benchmark-title">{copy.validationTitle}</h2>
          <p>{copy.intro}</p>
        </div>
        <div>
          <div className="landing-metrics" role="group" aria-label={copy.validation}>
            {metrics.map((value, index) => (
              <button type="button" aria-pressed={metric === index} onClick={() => setMetric(index)} key={value}>
                <strong>{format.format(value)}</strong><span>{copy.metricLabels[index]}</span>
              </button>
            ))}
          </div>
          <p className="landing-metric-detail" aria-live="polite"><CircleDot size={16} aria-hidden="true" /> {copy.metricCopy[metric]}</p>
        </div>
      </section>
      <footer className="landing-inner landing-closing">
        <div><h2>{copy.closingTitle}</h2><p>{copy.closingCopy}</p></div>
        <a className="landing-button landing-primary" href="/projects" onClick={(event) => follow(event, "/projects")}>
          {copy.start} <Arrow size={18} aria-hidden="true" />
        </a>
      </footer>
    </div>
  );
}
