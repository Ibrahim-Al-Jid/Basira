import React, { useEffect, useState } from "react";
import { post } from "./data";
import { api, action, errorText, translate } from "./platformClient";

const roles = {
  owner: ["مالك", "Owner"], admin: ["مدير", "Admin"],
  analyst: ["محلل", "Analyst"], viewer: ["مشاهد", "Viewer"],
};
const inviteRoles = ["analyst", "viewer", "admin"];
const when = (value, lang) => new Date(value).toLocaleString(lang === "ar" ? "ar-EG" : "en");

function Invitations({ endpoint, invitations, load, run, pending, lang }) {
  const t = translate(lang);
  const [share, setShare] = useState(null);
  const [copied, setCopied] = useState(false);
  return <section className="workspace-management">
    <h3>{t("دعوات المؤسسة", "Organization invitations")}</h3>
    <form className="project-form" onSubmit={(event) => {
      event.preventDefault();
      const { role } = Object.fromEntries(new FormData(event.currentTarget));
      run(async () => {
        const created = await action(endpoint, post({ role }));
        const url = new URL("/settings", window.location.origin);
        url.hash = "invite=" + encodeURIComponent(created.token);
        setShare({ id: created.id, url: url.href });
        setCopied(false);
        await load();
      }, ["تم إنشاء الدعوة.", "Invitation created."]);
    }}>
      <label>{t("دور المدعو", "Invitation role")}
        <select name="role" disabled={pending}>
          {inviteRoles.map((role) => <option key={role} value={role}>{t(...roles[role])}</option>)}
        </select>
      </label>
      <p className="workspace-hint">{t("شارك الرابط مع الشخص المقصود. ينضم للمؤسسة بعد تسجيل الدخول، وتقدر بعدها تضيفه للمشروع.",
        "Share the link with the intended recipient. They join the organization after signing in, then you can add them to the project.")}</p>
      <button className="btn" disabled={pending}>{t("إنشاء دعوة", "Create invitation")}</button>
    </form>
    {share && <div className="workspace-management">
      <label>{t("رابط الدعوة", "Invitation link")}
        <input readOnly value={share.url} dir="ltr" onFocus={(event) => event.currentTarget.select()} />
      </label>
      <button type="button" className="btn" onClick={async (event) => {
        const input = event.currentTarget.previousElementSibling?.querySelector("input");
        try { await navigator.clipboard.writeText(share.url); setCopied(true); }
        catch { input?.focus(); input?.select(); }
      }}>{copied ? t("تم النسخ", "Copied") : t("نسخ الرابط", "Copy link")}</button>
    </div>}
    {invitations.length > 0 && <ul className="workspace-access-list">
      {invitations.map((invite) => <li key={invite.id}>
        <span><strong>{t(...roles[invite.role])}</strong> · {t("تنتهي", "Expires")} <time dateTime={invite.expires_at}>{when(invite.expires_at, lang)}</time></span>
        <button className="btn" type="button" disabled={pending} onClick={() => run(async () => {
          await action(endpoint + "/" + invite.id, { method: "DELETE" });
          if (share?.id === invite.id) setShare(null);
          await load();
        }, ["تم إلغاء الدعوة.", "Invitation revoked."])}>{t("إلغاء الدعوة", "Revoke invitation")}</button>
      </li>)}
    </ul>}
  </section>;
}

export function ProjectAccess({ project, lang, active }) {
  const t = translate(lang);
  const owner = project.role === "owner";
  const membersPath = api + "/organizations/" + project.org_id + "/members";
  const grantsPath = api + "/projects/" + project.id + "/grants";
  const invitationPath = api + "/organizations/" + project.org_id + "/invitations";
  const [view, setView] = useState(null);
  const [failure, setFailure] = useState(null);
  const [revision, setRevision] = useState(0);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const [memberId, setMemberId] = useState("");
  const [role, setRole] = useState("viewer");

  async function load(signal) {
    const options = { signal };
    const [members, grants, invitations] = await Promise.all([
      action(membersPath, options),
      action(grantsPath, options),
      owner ? action(invitationPath, options) : { invitations: [] },
    ]);
    if (!signal?.aborted) setView({ members: members.members, grants: grants.grants, invitations: invitations.invitations });
  }

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setFailure(null);
    load(controller.signal).catch((error) => { if (!controller.signal.aborted) setFailure(error); });
    return () => controller.abort();
  }, [active, revision, project.id, owner]);

  async function run(task, success) {
    if (pending) return;
    setPending(true);
    setFailure(null);
    setNotice("");
    try { await task(); setNotice(success); }
    catch (error) { setFailure(error); }
    finally { setPending(false); }
  }

  const eligible = view?.members.filter((member) => ["analyst", "viewer"].includes(member.role)
    && !view.grants.some((grant) => grant.user_id === member.user_id)) || [];
  const member = view?.members.find((item) => item.user_id === memberId && item.role !== "owner");
  if (!active) return null;
  return <section className="workspace-management">
    <h2>{t("الأعضاء والصلاحيات", "Members and access")}</h2>
    {!view && !failure && <p role="status">{t("جاري تحميل الأعضاء…", "Loading members…")}</p>}
    {failure && <div className="workspace-error" role="alert">
      {errorText(failure, t)} <button className="btn" onClick={() => setRevision((value) => value + 1)}>{t("تحديث القائمة", "Refresh list")}</button>
    </div>}
    {notice && <p role="status">{t(...notice)}</p>}
    {view && <>
      <h3>{t("صلاحية المشروع", "Project access")}</h3>
      {eligible.length > 0 && <form className="project-form" onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const { member } = Object.fromEntries(new FormData(form));
        run(async () => {
          await action(grantsPath, post({ user_id: member }));
          form.reset();
          await load();
        }, ["تمت إضافة العضو للمشروع.", "Member added to the project."]);
      }}>
        <label>{t("عضو المؤسسة", "Organization member")}
          <select name="member" required defaultValue="" disabled={pending}>
            <option value="" disabled>{t("اختار عضوًا", "Choose a member")}</option>
            {eligible.map((item) => <option key={item.user_id} value={item.user_id}>{item.display_name} · {t(...roles[item.role])}</option>)}
          </select>
        </label>
        <button className="btn" disabled={pending}>{t("إضافة للمشروع", "Add to project")}</button>
      </form>}
      {!eligible.length && !view.grants.length && <p>{t("مفيش أعضاء محتاجين إذن للمشروع حالياً.", "There are no organization members to grant project access yet.")}</p>}
      {view.grants.length > 0 && <ul className="workspace-access-list">
        {view.grants.map((grant) => <li key={grant.user_id}>
          <span><bdi>{grant.display_name}</bdi> · {t(...roles[grant.role])}</span>
          <button className="btn" type="button" disabled={pending} onClick={() => run(async () => {
            await action(grantsPath + "/" + grant.user_id, { method: "DELETE" });
            await load();
          }, ["تم إلغاء صلاحية المشروع.", "Project access revoked."])}>{t("إلغاء إذن المشروع", "Revoke project access")}</button>
        </li>)}
      </ul>}
      {owner && view.members.some((item) => item.role !== "owner") && <div className="workspace-management">
        <h3>{t("عضوية المؤسسة", "Organization membership")}</h3>
        <form className="project-form" onSubmit={(event) => {
          event.preventDefault();
          if (!member || role === member.role) return;
          run(async () => {
            await action(membersPath, post({ user_id: member.user_id, role }));
            await load();
          }, ["تم حفظ دور العضو.", "Membership role saved."]);
        }}>
          <label>{t("عضو لتعديل صلاحياته", "Member to manage")}
            <select value={member?.user_id || ""} disabled={pending} onChange={(event) => {
              const selected = view.members.find((item) => item.user_id === event.target.value);
              setMemberId(selected?.user_id || "");
              if (selected) setRole(selected.role);
            }}>
              <option value="">{t("اختار عضوًا", "Choose a member")}</option>
              {view.members.filter((item) => item.role !== "owner").map((item) =>
                <option key={item.user_id} value={item.user_id}>{item.display_name} · {t(...roles[item.role])}</option>)}
            </select>
          </label>
          {member && <>
            <label>{t("دور العضو", "Membership role")}
              <select value={role} disabled={pending} onChange={(event) => setRole(event.target.value)}>
                {inviteRoles.map((role) => <option key={role} value={role}>{t(...roles[role])}</option>)}
              </select>
            </label>
            <div className="workspace-actions">
              <button className="btn" disabled={pending || role === member.role}>{t("حفظ دور العضو", "Save membership role")}</button>
              <button className="btn" type="button" disabled={pending} onClick={() => run(async () => {
                await action(membersPath + "/" + member.user_id, { method: "DELETE" });
                setMemberId("");
                await load();
              }, ["تم إلغاء عضوية المؤسسة.", "Organization membership revoked."])}>{t("إلغاء العضوية وكل أذونات المشاريع", "Revoke membership and project access")}</button>
            </div>
          </>}
        </form>
      </div>}
      {owner && <Invitations endpoint={invitationPath} invitations={view.invitations} run={run} load={load} pending={pending} lang={lang} />}
    </>}
  </section>;
}
