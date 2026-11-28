import React, { Suspense, lazy, useEffect, useState } from "react";
import { FileArchive, LogIn, Moon, ScanSearch, ShieldCheck, Sun, FileCheck2, Users } from "lucide-react";

const HeroGlobe = lazy(() => import("./HeroGlobe"));

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
  return ready ? <Suspense fallback={null}><HeroGlobe /></Suspense> : null;
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
  return (
    <div className="entry" dir={lang === "ar" ? "rtl" : "ltr"} lang={lang}>
      <header className="entry-bar">
        <a className="entry-brand" href="/" onClick={(event) => follow(event, "/")} aria-label={t("بصيرة", "Basira")}>
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
            <h1 id="entry-title">{t("اعرف إيه الخطر في مشروعك قبل ما يتسلّم.", "See what is risky in your project before it ships.")}</h1>
            <p className="entry-lead">{t("ارفع ملف ZIP أو اربط المستودع. بصيرة بتفحصه وتوريك الدليل على كل نتيجة، وتطلّعلك تقرير واضح.",
              "Upload a ZIP or connect a repository. Basira checks it, shows the evidence for every finding and gives you a clear report.")}</p>
            <div className="entry-actions">
              <a className="entry-cta" href="/signin" onClick={(event) => follow(event, "/signin")}>
                <LogIn size={18} aria-hidden="true" />{t("تسجيل الدخول", "Sign in")}
              </a>
              <a className="entry-ghost" href="/overview" onClick={(event) => follow(event, "/overview")}>{t("شوف العرض التجريبي", "Try the demo")}</a>
            </div>
          </div>
          <div className="entry-globe" aria-hidden="true"><DeferredGlobe /></div>
        </section>
        <section className="entry-steps" aria-label={t("إزاي بتشتغل", "How it works")}>
          {steps.map(([Icon, title, text], index) => (
            <article key={title} style={{ "--i": index }}>
              <span className="entry-step-icon"><Icon size={20} aria-hidden="true" /></span>
              <h2>{title}</h2>
              <p>{text}</p>
            </article>
          ))}
        </section>
      </main>
    </div>
  );
}
