import React, { useEffect, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, FileText, Folder, MoreHorizontal, Pencil, Pin, PinOff, Settings, SquarePen, Trash2 } from "lucide-react";
import { Menu } from "./Menu";
import { action, api, translate } from "./platformClient";
import { DirectoryLink } from "./ProjectDirectory";

const PIN_KEY = "basira-pinned-projects";
export function readPins() {
  try { const value = JSON.parse(localStorage.getItem(PIN_KEY) || "[]"); return Array.isArray(value) ? value : []; } catch { return []; }
}
export function writePins(ids) {
  try { localStorage.setItem(PIN_KEY, JSON.stringify(ids)); } catch { /* storage may be blocked */ }
}

const stateText = {
  queued: ["في الانتظار", "Queued"], running: ["شغّال", "Running"], completed: ["مكتمل", "Completed"],
  partial: ["جزئي", "Partial"], failed: ["فشل", "Failed"], cancelled: ["اتلغى", "Cancelled"],
};

// The scans of one project, nested under it like chats inside a ChatGPT project.
function Nested({ project, lang }) {
  const t = translate(lang);
  const [scans, setScans] = useState(null);
  useEffect(() => {
    const controller = new AbortController();
    action(api + "/projects/" + project.id + "/scans", { signal: controller.signal }).then(
      ({ scans: items }) => { if (!controller.signal.aborted) setScans(items); },
      () => { if (!controller.signal.aborted) setScans([]); },
    );
    return () => controller.abort();
  }, [project.id]);
  if (!scans) return <p className="group-note" role="status">{t("بنحمّل…", "Loading…")}</p>;
  if (!scans.length) return <p className="group-note">{t("لسه مفيش فحوصات.", "No scans yet.")}</p>;
  const shown = scans.slice(0, 5);
  return <ul className="group-scans">
    {shown.map((scan) => <li key={scan.id}>
      <a href={`/projects/${project.id}/scans/${scan.id}`}><FileText size={15} aria-hidden="true" /><bdi>{scan.artifact?.name || scan.id}</bdi></a>
      <span className="workspace-badge" data-state={scan.state}>{stateText[scan.state] ? t(...stateText[scan.state]) : scan.state}</span>
    </li>)}
    {scans.length > shown.length && <li className="group-more">
      <a href={`/projects?project=${project.id}&view=scans`}>{t("كل الفحوصات", "All scans")} ({scans.length})</a>
    </li>}
  </ul>;
}

export function ProjectGroup({ project, lang, open, onToggle, pinned, onPin, navigate, busy, onRename, onDelete }) {
  const t = translate(lang);
  const Chevron = open ? ChevronDown : lang === "ar" ? ChevronLeft : ChevronRight;
  const go = (path) => (event) => { event.preventDefault(); navigate(path); };
  const scanPath = "/new-scan?project=" + encodeURIComponent(project.id);
  const settingsPath = "/projects?project=" + project.id + "&view=management";
  return <div className="project-group" data-open={open}>
    <div className="project-group-head">
      <button type="button" className="group-toggle" aria-expanded={open} onClick={onToggle}
        aria-label={t((open ? "اطوي " : "افتح ") + project.name, (open ? "Collapse " : "Expand ") + project.name)}>
        <Chevron size={16} aria-hidden="true" />
      </button>
      <DirectoryLink className="group-name" to={"/projects?project=" + project.id} navigate={navigate}>
        <Folder size={17} aria-hidden="true" /><bdi>{project.name}</bdi>{pinned && <Pin size={13} className="group-pin" aria-label={t("مثبّت", "Pinned")} />}
      </DirectoryLink>
      <span className="group-actions">
        <a className="icon-action" href={scanPath} onClick={go(scanPath)} title={t("فحص جديد", "New scan")}
          aria-label={t("فحص جديد في " + project.name, "New scan in " + project.name)}><SquarePen size={16} aria-hidden="true" /></a>
        <Menu className="project-row-menu" label={t("إجراءات " + project.name, "Actions for " + project.name)}
          trigger={<MoreHorizontal size={18} aria-hidden="true" />}
          items={[
            { href: settingsPath, label: t("إعدادات المشروع", "Project settings"), icon: <Settings size={16} aria-hidden="true" />, onSelect: go(settingsPath) },
            { label: pinned ? t("إلغاء التثبيت", "Unpin project") : t("تثبيت المشروع", "Pin project"), icon: pinned ? <PinOff size={16} aria-hidden="true" /> : <Pin size={16} aria-hidden="true" />, onSelect: onPin },
            { label: t("تعديل اسم المشروع", "Rename project"), icon: <Pencil size={16} aria-hidden="true" />, disabled: busy, onSelect: onRename },
            { separator: true },
            { label: t("حذف المشروع", "Delete project"), icon: <Trash2 size={16} aria-hidden="true" />, danger: true, disabled: busy, onSelect: onDelete },
          ]} />
      </span>
    </div>
    {open && <Nested project={project} lang={lang} />}
  </div>;
}
