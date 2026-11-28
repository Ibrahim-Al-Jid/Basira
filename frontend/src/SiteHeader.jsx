import React from "react";
import { Check, Languages, LogOut, Moon, Settings, ShieldCheck, Sun, GitBranch } from "lucide-react";
import { Menu } from "./Menu";
import { Avatar } from "./avatar";
import { action, api } from "./platformClient";

const labels = {
  ar: {
    overview: "نظرة عامة", projects: "المشاريع", main: "التنقل الرئيسي",
    account: "قائمة الحساب", signin: "تسجيل الدخول", settings: "الإعدادات", github: "اتصال GitHub", logout: "تسجيل الخروج",
    skip: "انتقلي إلى المحتوى", light: "الوضع الفاتح", dark: "الوضع الغامق", theme: "المظهر", language: "اللغة",
  },
  en: {
    overview: "Overview", projects: "Projects", main: "Main navigation",
    account: "Account menu", signin: "Sign in", settings: "Settings", github: "GitHub connection", logout: "Sign out",
    skip: "Skip to content", light: "Light mode", dark: "Dark mode", theme: "Theme", language: "Language",
  },
};

export const readPreference = (key, fallback) => {
  try { return localStorage.getItem("basira-" + key) ?? fallback; }
  catch { return fallback; }
};
export const savePreference = (key, value) => {
  try { localStorage.setItem("basira-" + key, value); }
  catch { /* Preferences are optional when storage is unavailable. */ }
};

export function WorkspaceBrand({ href, follow, lang }) {
  return <a className="site-brand" href={href} onClick={(event) => follow(event, href)}>
    <span className="site-brand-mark" aria-hidden="true"><ShieldCheck size={33} strokeWidth={1.7} /></span>
    <span className="site-brand-copy">
      <strong dir="ltr">BASIRA</strong>
      <small>{lang === "ar" ? "مراجعة أمان المشاريع" : "PROJECT SECURITY REVIEW"}</small>
    </span>
  </a>;
}

export function SiteHeader({ pathname, follow, navigate, lang, user, preferences, onLogout }) {
  const t = labels[lang];
  const authenticated = Boolean(user);
  const route = pathname.split("/").filter(Boolean)[0] ?? "";
  const links = authenticated ? [
    ["/projects", t.projects, ["projects", "new-scan", "scans", "reports"].includes(route)],
  ] : [];
  async function logout() {
    try { await action(api + "/auth/logout", { method: "POST" }); } catch { return; }
    onLogout();
  }
  const choose = (value) => (event) => { event.preventDefault?.(); value(); };
  const items = [
    ...(authenticated ? [
      { href: "/settings", label: t.settings, icon: <Settings size={16} aria-hidden="true" />, onSelect: (event) => follow(event, "/settings") },
      { href: "/settings?tab=github", label: t.github, icon: <GitBranch size={16} aria-hidden="true" />, onSelect: (event) => follow(event, "/settings?tab=github") },
      { separator: true },
    ] : []),
    { label: t.language + ": " + (lang === "ar" ? "English" : "العربية"), icon: <Languages size={16} aria-hidden="true" />,
      onSelect: () => preferences.setLang(lang === "ar" ? "en" : "ar") },
    { label: preferences.theme === "dark" ? t.light : t.dark, icon: preferences.theme === "dark" ? <Sun size={16} aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />,
      onSelect: () => preferences.setTheme(preferences.theme === "dark" ? "light" : "dark") },
    ...(authenticated ? [{ separator: true }, { label: t.logout, icon: <LogOut size={16} aria-hidden="true" />, onSelect: logout }] : []),
  ];
  const name = user ? (user.display_name || user.username || "").trim() : "";
  return <>
    <a className="site-skip" href="#main-content">{t.skip}</a>
    <header className="site-header">
      <div className="site-header-inner">
        <WorkspaceBrand href={authenticated ? "/projects" : "/"} follow={follow} lang={lang} />
        {links.length > 0 && <nav className="site-nav" aria-label={t.main}>
          {links.map(([path, label, current]) => <a key={path} href={path} aria-current={current ? "page" : undefined}
            onClick={(event) => follow(event, path)}>{label}</a>)}
        </nav>}
        <div className="site-controls">
          {authenticated ? <Menu label={t.account} className="account-menu"
            trigger={<Avatar user={user} size={32} />} items={items}>
            <div className="menu-heading"><strong><bdi>{name || t.account}</bdi></strong>
              {user.username && <small dir="ltr">@{user.username}</small>}</div>
          </Menu> : <>
            <Menu label={t.account} className="account-menu" trigger={<Avatar size={32} />} items={items} />
            <a className="btn primary site-signin" href="/signin" onClick={(event) => follow(event, "/signin")}>{t.signin}</a>
          </>}
        </div>
      </div>
    </header>
  </>;
}
