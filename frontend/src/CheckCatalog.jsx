import React, { useEffect, useState } from "react";
import { fetchJson, num } from "./data";
import "./catalog.css";

export const domains = {
  html: "HTML", web: "أمان المتصفح والاستجابات", dependencies: "التبعيات",
  infrastructure: "البنية التحتية", ci: "خطوط CI/CD", application: "إعدادات التطبيق",
};

export function CheckCatalog() {
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
  const toolNames = new Map(catalog?.tools.map((entry) => [entry.id, entry.title_ar]));
  const query = search.trim().toLocaleLowerCase();
  const visible = catalog?.rules.filter((rule) => (!domain || domain === rule.domain)
    && (!tool || tool === rule.tool)
    && [rule.id, rule.title_ar, rule.title].some((value) => value.toLocaleLowerCase().includes(query))) || [];
  return <div className="check-catalog">
    <header className="heading">
      <div><h1>كتالوج الفحوصات</h1>
        {catalog && <p>{num(catalog.rules.length)} قاعدة في {num(Object.keys(domains).length)} مجالات · <bdi>{catalog.version}</bdi></p>}
        <p>التقرير بيبيّن القواعد اللي انطبقت على الملف اللي اخترته. فحوصات المشاريع بتدعم ZIP وHAR وإعدادات JSON.</p>
      </div>
      <a className="btn" href="/projects">فحوصات المشاريع</a>
    </header>
    {error && <p className="error" role="alert">{error} <button className="btn" onClick={() => {
      setError(""); setRetry((value) => value + 1);
    }}>إعادة المحاولة</button></p>}
    {!catalog && !error && <p role="status">جاري تحميل الفحوصات…</p>}
    {catalog && <>
      <div className="card catalog-filters">
        <label>بحث في الفحوصات<input type="search" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        <label>المجال<select value={domain} onChange={(event) => setDomain(event.target.value)}>
          <option value="">كل المجالات</option>
          {Object.entries(domains).map(([id, title]) => <option key={id} value={id}>{title}</option>)}
        </select></label>
        <label>أداة التحليل<select value={tool} onChange={(event) => setTool(event.target.value)}>
          <option value="">كل الأدوات</option>
          {catalog.tools.map((entry) => <option key={entry.id} value={entry.id}>{entry.title_ar}</option>)}
        </select></label>
      </div>
      <p role="status">{num(visible.length)} قاعدة مطابقة</p>
      {visible.length ? <ul className="card catalog-rules">{visible.map((rule) => <li key={rule.id}>
        <code dir="ltr">{rule.id}</code>
        <div><strong>{rule.title_ar}</strong><p dir="auto">{rule.title}</p></div>
        <small>{domains[rule.domain]} · {toolNames.get(rule.tool)}</small>
      </li>)}</ul> : <p>مفيش قواعد مطابقة للبحث ده.</p>}
    </>}
  </div>;
}
