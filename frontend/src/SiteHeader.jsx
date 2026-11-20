import React, { useEffect, useRef, useState } from "react";
import { ArrowUpRight, Languages, Menu, Moon, Plus, Sun, X } from "lucide-react";

const labels = {
  ar: {
    home: "الرئيسية", coverage: "التغطية", demo: "جرّب المختبر", dashboard: "نظرة عامة",
    projects: "المشاريع", scans: "الفحوصات", findings: "النتائج", reports: "التقارير",
    settings: "الإعدادات", start: "ابدأ الآن", scan: "فحص جديد", open: "افتح القائمة",
    close: "اقفل القائمة", nav: "التنقل الرئيسي", light: "الوضع الفاتح", dark: "الوضع الداكن",
    language: "Switch to English", skip: "انتقل إلى المحتوى",
  },
  en: {
    home: "Home", coverage: "Coverage", demo: "Try the demo", dashboard: "Overview",
    projects: "Projects", scans: "Scans", findings: "Findings", reports: "Reports",
    settings: "Settings", start: "Get started", scan: "New scan", open: "Open menu",
    close: "Close menu", nav: "Main navigation", light: "Light theme", dark: "Dark theme",
    language: "التبديل إلى العربية", skip: "Skip to content",
  },
};

const workspace = [
  ["dashboard", "/dashboard"], ["projects", "/projects"], ["scans", "/scans"],
  ["findings", "/findings"], ["reports", "/reports"], ["settings", "/settings"],
];
const publicNav = [["home", "/"], ["coverage", "/checks"], ["demo", "/demo"]];
export const readPreference = (key, fallback) => {
  try { return localStorage.getItem("marsad-" + key) ?? fallback; }
  catch { return fallback; }
};
export const savePreference = (key, value) => {
  try { localStorage.setItem("marsad-" + key, value); }
  catch { /* Preferences are optional when storage is unavailable. */ }
};

export function SiteHeader({ pathname, follow, lang, setLang, theme, setTheme, publicPage }) {
  const t = labels[lang];
  const [open, setOpen] = useState(false);
  const menu = useRef(null);
  useEffect(() => setOpen(false), [pathname]);
  const launch = publicPage ? "/dashboard" : "/new-scan";
  const links = publicPage ? publicNav : workspace;
  const action = <a className="site-cta" href={launch} onClick={(event) => follow(event, launch)}>
    {publicPage ? t.start : t.scan}{publicPage ? <ArrowUpRight size={16} aria-hidden="true" /> : <Plus size={16} aria-hidden="true" />}
  </a>;
  return <>
    <a className="site-skip" href="#main-content">{t.skip}</a>
    <header className="site-header" onKeyDown={(event) => {
      if (open && event.key === "Escape") {
        setOpen(false);
        menu.current?.focus();
      }
    }}>
      <div className="site-header-inner">
        <a className="site-brand" href="/" onClick={(event) => follow(event, "/")} aria-label={lang === "ar" ? "مرصد، الرئيسية" : "Marsad home"}>
          <span className="site-brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span dir="ltr">MARSAD</span>
        </a>
        <button ref={menu} className="site-icon site-mobile-menu" type="button" aria-label={open ? t.close : t.open} aria-controls="site-navigation"
          aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
        </button>
        <nav id="site-navigation" className={"site-nav" + (open ? " is-open" : "")} aria-label={t.nav}>
          {links.map(([key, path]) => {
            const current = pathname === path || (path !== "/" && pathname.startsWith(path + "/"));
            return <a key={path} href={path} onClick={(event) => { follow(event, path); setOpen(false); }}
              aria-current={current ? "page" : undefined}>{t[key]}</a>;
          })}
          <span className="site-mobile-action">{action}</span>
        </nav>
        <div className="site-controls">
          <button className="site-icon site-language" type="button" aria-label={t.language} onClick={() => setLang(lang === "ar" ? "en" : "ar")}>
            <Languages size={17} aria-hidden="true" /><span dir="ltr">{lang === "ar" ? "EN" : "AR"}</span>
          </button>
          <button className="site-icon" type="button" aria-label={theme === "dark" ? t.light : t.dark} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            {theme === "dark" ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
          </button>
          <span className="site-desktop-action">{action}</span>
        </div>
      </div>
    </header>
  </>;
}
