import React from "react";
import { DirectoryLink } from "./ProjectDirectory";

export function ProjectTabs({ project, active, manage, personal, t, navigate, onNavigate }) {
  const base = "/projects?project=" + project.id;
  const tabs = [
    ["activity", t("نظرة عامة", "Overview"), base],
    ["scans", t("الفحوصات", "Scans"), base + "&view=scans"],
    ["reports", t("التقارير", "Reports"), "/reports?project=" + project.id],
    ["references", t("المراجع", "References"), base + "&view=references"],
    ...(manage && !personal ? [["access", t("الوصول", "Access"), base + "&view=access"]] : []),
    ...(manage ? [["management", t("الإعدادات", "Settings"), base + "&view=management"]] : []),
  ];
  return <nav className="project-section-nav" aria-label={t("أقسام المشروع", "Project sections")}>
    {tabs.map(([section, name, to]) => <DirectoryLink key={section} to={to}
      navigate={(next) => { onNavigate?.(); navigate(next); }}
      aria-current={active === section ? "page" : undefined}>{name}</DirectoryLink>)}
  </nav>;
}
