import React, { useEffect, useRef, useState } from "react";
import { Menu, UserRound, X } from "lucide-react";

const labels = {
  ar: {
    dashboard: "نظرة عامة", projects: "المشاريع", scans: "الفحوصات", reports: "التقارير",
    account: "الحساب", signin: "تسجيل الدخول", open: "افتح القائمة", close: "اقفل القائمة",
    nav: "التنقل الرئيسي", skip: "انتقل إلى المحتوى",
  },
  en: {
    dashboard: "Overview", projects: "Projects", scans: "Scans", reports: "Reports",
    account: "Account", signin: "Sign in", open: "Open menu", close: "Close menu",
    nav: "Main navigation", skip: "Skip to content",
  },
};

const workspace = [
  ["dashboard", "/dashboard"], ["projects", "/projects"], ["scans", "/scans"], ["reports", "/reports"],
];
export const readPreference = (key, fallback) => {
  try { return localStorage.getItem("marsad-" + key) ?? fallback; }
  catch { return fallback; }
};
export const savePreference = (key, value) => {
  try { localStorage.setItem("marsad-" + key, value); }
  catch { /* Preferences are optional when storage is unavailable. */ }
};

export function SiteHeader({ pathname, follow, lang, authenticated, showSignIn }) {
  const t = labels[lang];
  const [open, setOpen] = useState(false);
  const menu = useRef(null);
  useEffect(() => setOpen(false), [pathname]);
  const route = pathname.replace(/\/$/, "");
  const activeRoute = route === "/new-scan" || /^\/projects\/[^/]+\/scans\//.test(route) ? "/scans" : route;
  const destination = authenticated ? "/settings" : "/signin";
  const brandDestination = authenticated ? "/dashboard" : "/";
  const current = route === destination;
  return <>
    <a className="site-skip" href="#main-content">{t.skip}</a>
    <header className="site-header" onKeyDown={(event) => {
      if (open && event.key === "Escape") {
        setOpen(false);
        menu.current?.focus();
      }
    }}>
      <div className="site-header-inner">
        <a className="site-brand" href={brandDestination} onClick={(event) => { follow(event, brandDestination); setOpen(false); }}
          aria-label={authenticated ? (lang === "ar" ? "مرصد، نظرة عامة" : "Marsad overview") : (lang === "ar" ? "مرصد، الرئيسية" : "Marsad home")}>
          <span className="site-brand-mark" aria-hidden="true"><i /><i /><i /></span>
          <span dir="ltr">MARSAD</span>
        </a>
        {authenticated && <button ref={menu} className="site-icon site-mobile-menu" type="button" aria-label={open ? t.close : t.open}
          aria-controls="site-navigation" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}
        </button>}
        {authenticated && <nav id="site-navigation" className={"site-nav" + (open ? " is-open" : "")} aria-label={t.nav}>
          {workspace.map(([key, path]) => <a key={path} href={path} onClick={(event) => { follow(event, path); setOpen(false); }}
            aria-current={activeRoute === path || activeRoute.startsWith(path + "/") ? "page" : undefined}>{t[key]}</a>)}
        </nav>}
        <div className="site-controls">
          {(authenticated || showSignIn) && <a className="site-icon site-account" href={destination}
            aria-current={current ? "page" : undefined}
            onClick={(event) => { follow(event, destination); setOpen(false); }}>
            <UserRound size={17} aria-hidden="true" />
            {authenticated ? t.account : t.signin}
          </a>}
        </div>
      </div>
    </header>
  </>;
}
