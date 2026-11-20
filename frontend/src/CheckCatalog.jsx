import React, { useEffect, useState } from "react";
import { fetchJson } from "./data";
import "./catalog.css";

const domains = {
  html: ["إعدادات HTML", "HTML configuration"], web: ["أمان المتصفح والاستجابات", "Browser and response security"],
  dependencies: ["التبعيات", "Dependencies"], infrastructure: ["البنية التحتية", "Infrastructure"],
  ci: ["خطوط CI/CD", "CI/CD workflows"], application: ["إعدادات التطبيق", "Application configuration"],
};

export function CheckCatalog({ lang = "ar" }) {
  const en = lang === "en";
  const t = (ar, english) => en ? english : ar;
  const format = new Intl.NumberFormat(lang);
  const [catalog, setCatalog] = useState(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [search, setSearch] = useState("");
  const [domain, setDomain] = useState("");
  const [tool, setTool] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    fetchJson("/api/catalog", { signal: controller.signal }).then(setCatalog, (err) => {
      if (!controller.signal.aborted) setError(err.message);
    });
    return () => controller.abort();
  }, [retry]);
  const toolTitle = (entry) => en ? entry.title || entry.id : entry.title_ar;
  const toolNames = new Map(catalog?.tools.map((entry) => [entry.id, toolTitle(entry)]));
  const query = search.trim().toLocaleLowerCase();
  const visible = catalog?.rules.filter((rule) => (!domain || domain === rule.domain)
    && (!tool || tool === rule.tool)
    && [rule.id, rule.title_ar, rule.title].some((value) => value.toLocaleLowerCase().includes(query))) || [];
  return <div className="check-catalog">
    <header className="heading">
      <div><h1>{t("كتالوج الفحوصات", "Security check catalog")}</h1>
        {catalog && <p>{t(
          format.format(catalog.rules.length) + " قاعدة في " + format.format(Object.keys(domains).length) + " مجالات",
          format.format(catalog.rules.length) + " checks across " + format.format(Object.keys(domains).length) + " domains",
        )} · <bdi>{catalog.version}</bdi></p>}
        <p>{t("التقرير بيبيّن القواعد اللي انطبقت على الملف اللي اخترته. فحوصات المشاريع بتدعم ZIP وHAR وإعدادات JSON.",
          "Each report shows the checks that applied to the supplied evidence. Project scans also support ZIP, HAR and JSON configurations.")}</p>
      </div>
      <a className="btn" href="/new-scan">{t("فحص جديد", "New scan")}</a>
    </header>
    {error && <p className="error" role="alert">{en ? "Could not load the catalog." : error} <button className="btn" onClick={() => {
      setError(""); setRetry((value) => value + 1);
    }}>{t("إعادة المحاولة", "Retry")}</button></p>}
    {!catalog && !error && <p role="status">{t("جاري تحميل الفحوصات…", "Loading checks…")}</p>}
    {catalog && <>
      <div className="card catalog-filters">
        <label>{t("بحث في الفحوصات", "Search checks")}<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <label>{t("المجال", "Domain")}<select value={domain} onChange={(event) => setDomain(event.target.value)}>
          <option value="">{t("كل المجالات", "All domains")}</option>
          {Object.entries(domains).map(([id, [ar, english]]) => <option key={id} value={id}>{t(ar, english)}</option>)}
        </select></label>
        <label>{t("أداة التحليل", "Analysis tool")}<select value={tool} onChange={(event) => setTool(event.target.value)}>
          <option value="">{t("كل الأدوات", "All tools")}</option>
          {catalog.tools.map((entry) => <option key={entry.id} value={entry.id}>{toolTitle(entry)}</option>)}
        </select></label>
      </div>
      <p role="status">{format.format(visible.length)} {t("قاعدة مطابقة", "matching checks")}</p>
      {visible.length ? <ul className="card catalog-rules">{visible.map((rule) => <li key={rule.id}>
        <code dir="ltr">{rule.id}</code>
        <div><strong>{t(rule.title_ar, rule.title)}</strong>{!en && <p lang="en" dir="ltr">{rule.title}</p>}</div>
        <small>{domains[rule.domain]?.[Number(en)]} · {toolNames.get(rule.tool)}</small>
      </li>)}</ul> : <p>{t("مفيش قواعد مطابقة للبحث ده.", "No checks match these filters.")}</p>}
    </>}
  </div>;
}
