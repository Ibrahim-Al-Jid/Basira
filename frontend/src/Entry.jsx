import React, { Suspense, lazy, useEffect, useState } from "react";
import { BadgeCheck, FileArchive, FileCheck2, FileText, Languages, LogIn, Moon, ScanSearch, SearchCheck, ShieldCheck, Sun, Users } from "lucide-react";

const Planet = lazy(() => import("./Planet").then((m) => ({ default: m.PlanetOrFallback })));

function DeferredGlobe() {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    const go = () => setReady(true);
    if ("requestIdleCallback" in window) {
      const id = window.requestIdleCallback(go, { timeout: 1200 });
      return () => window.cancelIdleCallback(id);
    }
    const id = setTimeout(go, 400);
    return () => clearTimeout(id);
  }, []);
  return ready ? <Suspense fallback={null}><Planet /></Suspense> : null;
}

function useReveal() {
  useEffect(() => {
    const items = [...document.querySelectorAll(".reveal")];
    if (!("IntersectionObserver" in window) || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      items.forEach((item) => item.classList.add("in"));
      return undefined;
    }
    const io = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) { entry.target.classList.add("in"); io.unobserve(entry.target); }
    }), { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    items.forEach((item) => io.observe(item));
    return () => io.disconnect();
  }, []);
}

// The public first page: shown at "/" to signed-out visitors, outside the workspace shell.
export function Entry({ follow, lang, preferences }) {
  const t = (ar, en) => lang === "ar" ? ar : en;
  const ThemeIcon = preferences.theme === "dark" ? Sun : Moon;
  const steps = [
    [FileArchive, t("ضيف مشروعك", "Add your project"), t("ارفع ملف ZIP أو اربط مستودع GitHub.", "Upload a ZIP or connect a GitHub repository.")],
    [Users, t("الوكلاء بيراجعوه", "Agents review it"), t("محلل ومدقق وكاتب تقرير، كل واحد بيشوف جزء.", "An analyst, a validator and a reporter each check a part.")],
    [FileCheck2, t("اقرا التقرير بالأدلة", "Read the report with evidence"), t("كل نتيجة معاها الملف والسطر والإصلاح المقترح.", "Every finding comes with the file, the line and a suggested fix.")],
  ];
  useReveal();
  const does = [
    [SearchCheck, t("نتايج بدليل", "Findings with evidence"), t("كل نتيجة مربوطة بالملف والسطر اللي طلعت منه، فتقدر تتأكد بنفسك.", "Each finding points to the file and line it came from, so you can check it yourself.")],
    [Users, t("فريق مراجعة", "A review team"), t("محلل بيفحص، ومدقق بيتأكد، وكاتب تقرير بيرتّب الأولويات.", "An analyst examines, a validator confirms and a reporter sorts the priorities.")],
    [FileText, t("تقرير جاهز للتسليم", "A report you can hand in"), t("تقرير واضح تنزّله PDF بالعربي أو بالإنجليزي.", "A clear report you can download as PDF in Arabic or English.")],
  ];
  const trust = [
    [BadgeCheck, t("مفيش نتيجة من غير مصدر", "No finding without a source"), t("لو مفيش دليل في الملفات، النتيجة مش بتتعرض.", "If the files do not show it, it is not reported.")],
    [ShieldCheck, t("بتقولك اللي ماتفحصش", "It tells you what was not checked"), t("التقرير بيوضّح الأجزاء اللي خرجت برا الفحص، مش بيدّعي تغطية كاملة.", "The report lists what fell outside the scan instead of claiming full coverage.")],
    [Languages, t("عربي وإنجليزي", "Arabic and English"), t("الواجهة والتقارير بالاتجاهين، يمين لشمال وشمال ليمين.", "The interface and reports work in both directions, right to left and left to right.")],
  ];
  return (
    <div className="entry" dir={lang === "ar" ? "rtl" : "ltr"} lang={lang}>
      <header className="entry-bar">
        <a className="entry-brand" href="/" onClick={(event) => follow(event, "/")}>
          <span className="entry-mark" aria-hidden="true"><ShieldCheck size={26} strokeWidth={1.7} /></span>
          <strong dir="ltr">BASIRA</strong>
        </a>
        <nav className="entry-nav" aria-label={t("التنقل", "Navigation")}>
          <a className="entry-link" href="/overview" onClick={(event) => follow(event, "/overview")}>{t("جرّب العرض التجريبي", "Demo")}</a>
          <button type="button" className="entry-icon" onClick={() => preferences.setTheme(preferences.theme === "dark" ? "light" : "dark")}
            aria-label={preferences.theme === "dark" ? t("الوضع الفاتح", "Light mode") : t("الوضع الغامق", "Dark mode")}>
            <ThemeIcon size={17} aria-hidden="true" />
          </button>
          <button type="button" className="entry-icon entry-lang" onClick={() => preferences.setLang(lang === "ar" ? "en" : "ar")}
            lang={lang === "ar" ? "en" : "ar"}>{lang === "ar" ? "EN" : "عربي"}</button>
          <a className="entry-cta entry-cta-small" href="/signin" onClick={(event) => follow(event, "/signin")}>
            <LogIn size={16} aria-hidden="true" />{t("تسجيل الدخول", "Sign in")}
          </a>
        </nav>
      </header>
      <main id="main-content" tabIndex={-1} className="entry-main">
        <section className="entry-hero" aria-labelledby="entry-title">
          <div className="entry-copy">
            <p className="entry-eyebrow"><ScanSearch size={16} aria-hidden="true" />{t("مراجعة أمان المشاريع", "Project security review")}</p>
            <h1 id="entry-title">{t("رؤية كاملة لمشروعك، دليل على كل نقطة.", "A full view of your project, evidence for every point.")}</h1>
            <p className="entry-lead">{t("ارفع ملف ZIP أو اربط المستودع. بصيرة بتفحصه وتوريك الدليل على كل نتيجة، وتطلّعلك تقرير واضح.",
              "Upload a ZIP or connect a repository. Basira checks it, shows the evidence for every finding and gives you a clear report.")}</p>
            <div className="entry-actions">
              <a className="entry-cta" href="/signin" onClick={(event) => follow(event, "/signin")}>
                <LogIn size={18} aria-hidden="true" />{t("تسجيل الدخول", "Sign in")}
              </a>
              <a className="entry-ghost" href="/overview" onClick={(event) => follow(event, "/overview")}>{t("شوف العرض التجريبي", "Try the demo")}</a>
            </div>
          </div>
          <figure className="entry-visual">
            <div className="entry-globe" aria-hidden="true"><DeferredGlobe /></div>
          </figure>
        </section>
        <section className="entry-section reveal" aria-labelledby="entry-does">
          <h2 id="entry-does">{t("بصيرة بتعمل إيه", "What Basira does")}</h2>
          <div className="entry-grid">
            {does.map(([Icon, title, text], index) => (
              <article key={title} className="entry-card reveal" style={{ "--i": index }}>
                <span className="entry-step-icon"><Icon size={20} aria-hidden="true" /></span>
                <h3>{title}</h3><p>{text}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="entry-section reveal" aria-labelledby="entry-how">
          <h2 id="entry-how">{t("إزاي بتشتغل", "How it works")}</h2>
          <div className="entry-grid entry-steps">
          {steps.map(([Icon, title, text], index) => (
            <article key={title} className="entry-card reveal" style={{ "--i": index }}>
              <span className="entry-num" aria-hidden="true">{index + 1}</span>
              <span className="entry-step-icon"><Icon size={20} aria-hidden="true" /></span>
              <h3>{title}</h3>
              <p>{text}</p>
            </article>
          ))}
          </div>
        </section>
        <section className="entry-section reveal" aria-labelledby="entry-trust">
          <h2 id="entry-trust">{t("مراجعة تقدر تثق فيها", "A review you can trust")}</h2>
          <div className="entry-grid">
            {trust.map(([Icon, title, text], index) => (
              <article key={title} className="entry-card reveal" style={{ "--i": index }}>
                <span className="entry-step-icon"><Icon size={20} aria-hidden="true" /></span>
                <h3>{title}</h3><p>{text}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="entry-final reveal" aria-labelledby="entry-final">
          <h2 id="entry-final">{t("جاهز تراجع مشروعك؟", "Ready to review your project?")}</h2>
          <p>{t("سجّل دخولك وارفع أول مشروع، أو شوف العرض التجريبي الأول.", "Sign in and add your first project, or look at the demo first.")}</p>
          <div className="entry-actions">
            <a className="entry-cta" href="/signin" onClick={(event) => follow(event, "/signin")}><LogIn size={18} aria-hidden="true" />{t("تسجيل الدخول", "Sign in")}</a>
            <a className="entry-ghost" href="/overview" onClick={(event) => follow(event, "/overview")}>{t("شوف العرض التجريبي", "Try the demo")}</a>
          </div>
        </section>
      </main>
      <footer className="entry-footer">
        <a className="entry-brand" href="/" onClick={(event) => follow(event, "/")}><span className="entry-mark" aria-hidden="true"><ShieldCheck size={20} strokeWidth={1.7} /></span><strong dir="ltr">BASIRA</strong></a>
        <span>{t("مراجعة أمان المشاريع", "Project security review")}</span>
        <nav aria-label={t("روابط", "Links")}>
          <a href="/signin" onClick={(event) => follow(event, "/signin")}>{t("تسجيل الدخول", "Sign in")}</a>
          <a href="/overview" onClick={(event) => follow(event, "/overview")}>{t("العرض التجريبي", "Demo")}</a>
        </nav>
      </footer>
    </div>
  );
}
