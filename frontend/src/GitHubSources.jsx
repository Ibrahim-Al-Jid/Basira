import React, { useEffect, useState } from "react";
import { GitBranch } from "lucide-react";
import { api, action, errorText, json, translate } from "./platformClient";

export function GitHubConnections({ org, projects, lang }) {
  const t = translate(lang);
  const url = `${api}/organizations/${encodeURIComponent(org.id)}/github-source`;
  const [project, setProject] = useState("");
  const [view, setView] = useState(null);
  const [failure, setFailure] = useState(null);
  const [notice, setNotice] = useState(null);
  const [pending, setPending] = useState(false);
  const [revision, setRevision] = useState(0);
  const selected = projects.find((item) => item.id === project) || projects[0];
  const existing = view?.connections?.find((item) => item.project_id === selected?.id);

  useEffect(() => {
    const controller = new AbortController();
    action(url, { signal: controller.signal }).then((next) => {
      if (!controller.signal.aborted) setView(next);
    }, (error) => {
      if (!controller.signal.aborted) setFailure(error);
    });
    return () => controller.abort();
  }, [url, revision]);

  async function change(options, message) {
    if (pending) return;
    setPending(true);
    setFailure(null);
    setNotice(null);
    try {
      await action(options.url, options.request);
      setView(await action(url));
      setNotice(message);
    } catch (error) {
      setFailure(error);
    } finally {
      setPending(false);
    }
  }

  return <section className="card project-panel account-model">
    <h2><GitBranch size={19} aria-hidden="true" />{t("مصادر GitHub", "GitHub sources")}</h2>
    {!view && !failure && <p role="status">{t("بنحمّل إعدادات GitHub…", "Loading GitHub settings…")}</p>}
    {failure && <div className="workspace-error" role="alert">{errorText(failure, t)}{" "}
      <button className="btn" type="button" disabled={pending} onClick={() => {
        setFailure(null);
        setRevision((value) => value + 1);
      }}>{t("إعادة المحاولة", "Retry")}</button>
    </div>}
    {notice && <p role="status">{notice}</p>}
    {view && !view.available && <p>{t("تكامل GitHub محتاج إعداد GitHub App من مشغّل المنصة. رفع ZIP متاح من شاشة الفحص.",
      "GitHub App setup is required from the platform operator. You can upload a ZIP in New scan.")}</p>}
    {view?.available && !selected && <p>{t("أنشئ مشروع داخل المؤسسة علشان تربطه بمستودع.", "Create a project in this organization to connect a repository.")}</p>}
    {view && selected && (view.available || view.connections?.length > 0) && <>
      <label>{t("المشروع", "Project")}
        <select value={selected.id} disabled={pending} onChange={(event) => {
          setProject(event.target.value);
          setNotice(null);
          setFailure(null);
        }}>
          {projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
      {existing && <p>{t("المستودع المرتبط", "Connected repository")} · <bdi>{existing.repository}</bdi></p>}
      {view.available && <form className="project-form" key={`${selected.id}:${existing?.repository || ""}:${existing?.installation_id || ""}`}
        aria-busy={pending} onSubmit={(event) => {
          event.preventDefault();
          const data = new FormData(event.currentTarget);
          void change({ url, request: json("PUT", {
            project_id: selected.id,
            repository: data.get("repository").trim(),
            installation_id: Number(data.get("installation")),
          }) }, t("تم حفظ الربط.", "Connection saved."));
        }}>
        <label>{t("مستودع GitHub", "GitHub repository")}
          <input name="repository" dir="ltr" placeholder="owner/repo" maxLength={140}
            defaultValue={existing?.repository || ""} required disabled={pending} />
        </label>
        <label>{t("تثبيت GitHub App", "GitHub App installation")}
          <select name="installation" defaultValue={existing?.installation_id || view.installation_ids?.[0] || ""} required disabled={pending}>
            <option value="" disabled>{t("اختار تثبيت التطبيق", "Choose an installation")}</option>
            {(view.installation_ids || []).map((id) => <option key={id} value={id}>{id}</option>)}
          </select>
        </label>
        <p className="workspace-hint">{t("الربط للقراءة فقط. راجع صلاحية التطبيق على المستودع المختار.",
          "This connection is read-only. Check that the application has access to the selected repository.")}</p>
        <div className="workspace-actions">
          <button className="btn" type="submit" disabled={pending || !view.installation_ids?.length}>
            {existing ? t("حدّث الربط", "Update connection") : t("اربط المستودع", "Connect repository")}
          </button>
        </div>
      </form>}
      {existing && <div className="workspace-actions">
        <button className="btn" type="button" disabled={pending} onClick={() => {
          void change({ url: url + "?" + new URLSearchParams({ project_id: selected.id }), request: { method: "DELETE" } },
            t("تم إلغاء ربط المستودع.", "Repository disconnected."));
        }}>{t("ألغِ الربط", "Disconnect repository")}</button>
      </div>}
    </>}
  </section>;
}
