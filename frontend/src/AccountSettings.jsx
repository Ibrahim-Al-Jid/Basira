import React, { useEffect, useRef, useState } from "react";
import { KeyRound, Languages, LogOut, Palette, Pencil, UserPlus, UserRound } from "lucide-react";
import { Modal } from "./Dialogs";
import { GitHubConnections } from "./GitHubSources";
import { ProviderSettings } from "./ProviderSettings";
import { post } from "./data";
import { api, action, errorText, json, translate } from "./platformClient";
import "./accountSettings.css";

function JoinOrganization({ invitation, clearInvite, onJoined, lang }) {
  const t = translate(lang);
  const [pending, setPending] = useState(false);
  const [open, setOpen] = useState(Boolean(invitation));
  const [failure, setFailure] = useState(null);
  const [joined, setJoined] = useState(null);

  useEffect(() => { if (invitation) setOpen(true); }, [invitation]);

  const title = t("دعوات المؤسسات", "Organization invitations");
  const close = () => {
    if (pending) return;
    setFailure(null);
    setOpen(false);
    if (invitation) clearInvite();
  };
  return <section className="card project-panel account-invitations" aria-labelledby="account-invitations-title">
    <div>
      <h2 id="account-invitations-title">{title}</h2>
      {joined && <p role="status">{t("انضممت إلى", "You joined")} <bdi>{joined.name}</bdi>.</p>}
    </div>
    <button className="btn" type="button" onClick={() => setOpen(true)}>
      <UserPlus size={16} aria-hidden="true" />{t("قبول دعوة مؤسسة", "Accept an organization invitation")}
    </button>
    {open && <Modal title={title} close={close} lang={lang}><form className="project-form" onSubmit={async (event) => {
      event.preventDefault();
      if (pending) return;
      const form = event.currentTarget;
      const value = new FormData(form).get("invitation").trim();
      const token = /^https?:\/\//i.test(value) ? value.match(/#invite=([a-z0-9_-]+)$/i)?.[1] : value;
      if (!/^[a-z0-9_-]{43}$/i.test(token || "")) {
        setFailure({ message: ["استخدم رابط دعوة صحيح أو رمز الدعوة.", "Use a valid invitation link or token."] });
        return;
      }
      setPending(true);
      setFailure(null);
      setJoined(null);
      try {
        const organization = await action(api + "/invitations/accept", post({ token }));
        clearInvite();
        setOpen(false);
        setJoined(organization);
        onJoined();
      } catch (error) {
        setFailure([404, 409, 410].includes(error.status)
          ? { message: ["الدعوة غير متاحة. اطلب رابطًا جديدًا من مالك المؤسسة.", "This invitation is unavailable. Ask the organization owner for a new link."] }
          : { error });
      } finally { setPending(false); }
    }}>
      <label>{t("رابط الدعوة أو رمزها", "Invitation link or token")}
        <input key={invitation} name="invitation" dir="ltr" autoComplete="off" defaultValue={invitation}
          type="password" required disabled={pending} maxLength={1024} spellCheck={false} />
      </label>
      {failure && <p className="workspace-error" role="alert">{failure.message ? t(...failure.message) : errorText(failure.error, t)}</p>}
      <button className="btn primary" disabled={pending}>{pending ? t("جاري قبول الدعوة…", "Accepting invitation…") : t("قبول الدعوة", "Accept invitation")}</button>
    </form></Modal>}
  </section>;
}

function Profile({ lang, user, onProfileChange }) {
  const t = translate(lang);
  const [editing, setEditing] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const [saved, setSaved] = useState(false);
  const name = user.display_name || t("حساب مرصد", "Marsad account");
  const joined = user.created_at ? new Date(user.created_at) : null;
  const title = t("تعديل البروفايل", "Edit profile");

  async function save(event) {
    event.preventDefault();
    if (pending) return;
    const fields = new FormData(event.currentTarget);
    const first_name = fields.get("first_name").trim();
    const last_name = fields.get("last_name").trim();
    const username = fields.get("username").trim() || null;
    setPending(true);
    setError(null);
    try {
      const updated = await action(api + "/auth/profile", json("PUT", { first_name, last_name, username }));
      onProfileChange(updated);
      setEditing(false);
      setSaved(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setPending(false);
    }
  }

  return <section className="card project-panel account-identity" aria-labelledby="account-profile-title">
    <h2 id="account-profile-title">{t("البروفايل", "Profile")}</h2>
    <div className="account-identity-person">
      <span className="account-avatar" aria-hidden="true"><UserRound size={22} /></span>
      <div>
        <strong><bdi>{name}</bdi></strong>
        {!user.display_name && <p>{t("ضيف اسمك عشان يظهر في نظرة عامة.", "Add your name so it appears in Overview.")}</p>}
      </div>
    </div>
    <dl className="account-profile-facts">
      <div><dt>{t("اسم المستخدم", "Username")}</dt><dd>{user.username ? <bdi dir="ltr">@{user.username}</bdi> : t("اختياري", "Optional")}</dd></div>
      {joined && <div><dt>{t("تاريخ إنشاء الحساب", "Member since")}</dt>
        <dd><time dateTime={user.created_at}>{joined.toLocaleDateString(lang === "ar" ? "ar-EG" : "en", { dateStyle: "long" })}</time></dd>
      </div>}
    </dl>
    <button type="button" className="btn" onClick={() => { setError(null); setSaved(false); setEditing(true); }}>
      <Pencil size={16} aria-hidden="true" />{title}
    </button>
    {saved && <p role="status">{t("تم حفظ البروفايل.", "Profile saved.")}</p>}
    {editing && <Modal title={title} close={() => { if (!pending) setEditing(false); }} lang={lang}>
      <form className="project-form account-edit-form" onSubmit={save} aria-busy={pending}>
        <div className="account-name-fields">
          <label>{t("الاسم الأول", "First name")}
            <input name="first_name" autoComplete="given-name" maxLength={80} dir="auto" required defaultValue={user.first_name || ""} disabled={pending} />
          </label>
          <label>{t("اسم العيلة", "Last name")}
            <input name="last_name" autoComplete="family-name" maxLength={80} dir="auto" required defaultValue={user.last_name || ""} disabled={pending} />
          </label>
        </div>
        <label>{t("اسم المستخدم (اختياري)", "Username (optional)")}
          <input name="username" autoComplete="off" maxLength={30} minLength={3} dir="ltr"
            pattern="[A-Za-z0-9][A-Za-z0-9._]{1,28}[A-Za-z0-9]" defaultValue={user.username || ""}
            aria-describedby="profile-username-hint" spellCheck={false} disabled={pending} />
        </label>
        <p id="profile-username-hint" className="workspace-hint">{t("من ٣ لـ٣٠ حرف إنجليزي أو رقم. النقطة والشرطة السفلية مسموح بيهم في النص.",
          "Use 3–30 English letters or digits. Dots and underscores are allowed in between.")}</p>
        {error && <p className="workspace-error" role="alert">{error.status === 409 ? t("اسم المستخدم مستخدم بالفعل.", "This username is taken.")
          : error.status === 422 ? t("راجع صيغة الاسم واسم المستخدم.", "Check the names and username.") : errorText(error, t)}</p>}
        <button className="btn primary" disabled={pending}>{pending ? t("جاري الحفظ…", "Saving…") : t("حفظ البروفايل", "Save profile")}</button>
      </form>
    </Modal>}
  </section>;
}

function ProjectModelAccess({ projects, connection, lang }) {
  const t = translate(lang);
  const [project, setProject] = useState("");
  const [snapshot, setSnapshot] = useState(null);
  const [failure, setFailure] = useState(null);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const [revision, setRevision] = useState(0);
  const endpoint = project ? api + "/projects/" + project + "/policy" : null;
  const assigned = Boolean(snapshot?.policy.model_connection);

  useEffect(() => {
    if (!endpoint) return;
    const controller = new AbortController();
    action(endpoint, { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setSnapshot(value); },
      (error) => { if (!controller.signal.aborted) setFailure(error); },
    );
    return () => controller.abort();
  }, [endpoint, revision]);

  async function changePermission() {
    if (!snapshot || pending || (!assigned && !connection)) return;
    setPending(true);
    setFailure(null);
    setNotice("");
    const { allowed_kinds, base_url, model_connection: _connection, ...rules } = snapshot.policy;
    try {
      const next = await action(endpoint, json("PUT", {
        allowed_kinds, base_url: base_url || null, rules,
        model_connection: assigned ? null : connection.id,
        expected_version: snapshot.version,
      }));
      setSnapshot(next);
      setNotice(assigned ? ["تم إيقاف استخدام الاتصال في المشروع.", "Project access revoked."]
        : ["بقى الاتصال متاح للمشروع.", "Model connection enabled for this project."]);
    } catch (error) {
      setFailure(error);
      if (error.status === 409) setSnapshot(null);
    } finally { setPending(false); }
  }

  if (!projects.length) return null;
  return <section className="workspace-management">
    <h3>{t("استخدام الموديل في المشاريع", "Model access for projects")}</h3>
    <label>{t("المشروع", "Project")}
      <select value={project} onChange={(event) => {
        setProject(event.target.value); setSnapshot(null); setNotice(""); setFailure(null);
      }} disabled={pending}>
        <option value="">{t("اختار مشروعًا", "Choose a project")}</option>
        {projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select>
    </label>
    {failure && <div className="workspace-error" role="alert">{errorText(failure, t)} <button className="btn" onClick={() => {
      setFailure(null);
      setRevision((value) => value + 1);
    }}>{t("تحديث صلاحية المشروع", "Refresh project access")}</button></div>}
    {endpoint && !snapshot && !failure && <p role="status">{t("جاري تحميل صلاحية المشروع…", "Loading project access…")}</p>}
    {snapshot && <>
      <p>{assigned ? t("الاتصال مسموح للمشروع. تشغيله اختياري عند إرسال الفحص.", "This project can opt in to use the connection when submitting scans.")
        : t("الفحص المحلي متاح لهذا المشروع.", "This project can run local scans.")}</p>
      <button className="btn" type="button" disabled={pending} onClick={changePermission}>
        {assigned ? t("إلغاء إذن الموديل للمشروع", "Revoke model access") : t("السماح بالموديل للمشروع", "Grant model access")}
      </button>
    </>}
    {notice && <p role="status">{t(...notice)}</p>}
  </section>;
}

function ModelCredentials({ org, projects, lang }) {
  const t = translate(lang);
  const endpoint = api + "/organizations/" + org + "/model-connection";
  const [view, setView] = useState(null);
  const [model, setModel] = useState("");
  const [failure, setFailure] = useState(null);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const [removing, setRemoving] = useState(false);
  const [replacing, setReplacing] = useState(false);
  const [revision, setRevision] = useState(0);
  const [accessRevision, setAccessRevision] = useState(0);
  const secret = useRef(null);
  const connection = view?.connection;
  const managed = connection?.source === "organization";
  const needKey = !managed || replacing;
  const options = { cache: "no-store" };

  function apply(value) {
    setView(value);
    setModel(value.connection?.model || "");
  }

  useEffect(() => {
    const controller = new AbortController();
    action(endpoint, { ...options, signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) apply(value); },
      (error) => { if (!controller.signal.aborted) setFailure(error); },
    );
    return () => controller.abort();
  }, [endpoint, revision]);

  async function save(event) {
    event.preventDefault();
    if (pending || !view?.available) return;
    const key = secret.current?.value.trim();
    if (secret.current) secret.current.value = "";
    if (needKey && !key) return;
    const payload = json("PUT", { model: model.trim(), ...(key ? { api_key: key } : {}) });
    await change(payload, ["تم التحقق من الاتصال وحفظه.", "Connection verified and saved."]);
  }

  async function change(request, success) {
    if (pending) return;
    setPending(true);
    setFailure(null);
    setNotice("");
    try {
      apply(await action(endpoint, { ...options, ...request }));
      setRemoving(false);
      setReplacing(false);
      setAccessRevision((value) => value + 1);
      setNotice(success);
    } catch (error) {
      setFailure(error);
    } finally {
      setPending(false);
    }
  }

  return <section className="workspace-management">
    {!view && !failure && <p role="status">{t("جاري تحميل الاتصال…", "Loading connection…")}</p>}
    {failure && <div role="alert" className="workspace-error">
      {errorText(failure, t)} {!view && <button type="button" className="btn" onClick={() => {
        setFailure(null);
        setRevision((value) => value + 1);
      }}>{t("إعادة المحاولة", "Retry")}</button>}
    </div>}
    {notice && <p role="status">{t(...notice)}</p>}
    {view && <>
      {connection && <dl className="workspace-summary">
        <div><dt>{t("الموديل المتاح", "Available model")}</dt><dd><bdi>{connection.model}</bdi></dd></div>
        <div><dt>{t("الحالة", "Connection status")}</dt><dd>{managed ? t("مُتحقَّق منه", "Verified") : t("باتصال المشغّل", "Operator-managed")}</dd></div>
        {connection.verified_at && <div><dt>{t("آخر تحقق", "Last verified")}</dt>
          <dd><time dateTime={connection.verified_at}>{new Date(connection.verified_at).toLocaleString(lang === "ar" ? "ar-EG" : "en")}</time></dd></div>}
      </dl>}
      {!view.available && <p>{t("إعداد اتصال المؤسسة غير متاح حاليًا. تقدر تكمّل الفحوصات المحلية.", "Connection setup is currently unavailable. Local scans remain available.")}</p>}
      {view.available && !removing && <form className="project-form" onSubmit={save} aria-busy={pending}>
        <label>{t("معرّف موديل OpenRouter", "OpenRouter model ID")}
          <input name="model" value={model} onChange={(event) => setModel(event.target.value)} dir="ltr" autoComplete="off"
            placeholder="provider/model" required maxLength={160} disabled={pending} spellCheck={false} />
        </label>
        {needKey && <label>{replacing ? t("مفتاح API الجديد", "New API key") : t("مفتاح API لـ OpenRouter", "OpenRouter API key")}
          <input name="api_key" ref={secret} type="password" required dir="ltr" maxLength={256} disabled={pending}
            autoComplete="new-password" spellCheck={false} />
        </label>}
        <p className="workspace-hint">{t("التحقق مش بيشغّل فحصًا. استخدام الموديل المدفوع في الفحص ممكن يكلّف رصيدًا.", "Verification does not run a scan. Using a paid model in a scan may incur charges.")}</p>
        <div className="workspace-actions">
          <button className="btn primary" disabled={pending}>{pending ? t("جاري التحقق…", "Verifying…") : t("تحقق واحفظ", "Verify and save")}</button>
          {managed && <button className="btn" type="button" disabled={pending} onClick={() => setReplacing((value) => !value)}>
            {replacing ? t("إلغاء تغيير المفتاح", "Cancel key rotation") : t("تغيير المفتاح", "Rotate key")}
          </button>}
        </div>
      </form>}
      {managed && (removing ? <div className="workspace-management">
        <p>{t("إزالة الاتصال هتمنع أي استخدام جديد لهذا المفتاح في مشاريع المؤسسة.", "Removing the connection prevents new scans from using this organization key.")}</p>
        <div className="workspace-actions">
          <button className="btn" disabled={pending} onClick={() => change({ method: "DELETE" }, ["تمت إزالة الاتصال.", "Connection removed."])}>{t("تأكيد الإزالة", "Confirm removal")}</button>
          <button className="btn" type="button" disabled={pending} onClick={() => setRemoving(false)}>{t("إلغاء", "Cancel")}</button>
        </div>
      </div> : <button className="btn" disabled={pending} type="button" onClick={() => { setRemoving(true); setReplacing(false); }}>{t("إزالة الاتصال", "Remove connection")}</button>)}
      {connection && <ProjectModelAccess key={accessRevision} projects={projects} connection={connection} lang={lang} />}
    </>}
  </section>;
}

function OrganizationConnections({ lang, revision }) {
  const t = translate(lang);
  const [view, setView] = useState(null);
  const [failure, setFailure] = useState(null);
  const [retry, setRetry] = useState(0);
  const [selected, setSelected] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    const options = { signal: controller.signal };
    Promise.all([action(api + "/organizations", options), action(api + "/projects", options)]).then(
      ([{ organizations }, { projects }]) => {
        if (controller.signal.aborted) return;
        setView({ organizations: organizations.filter((item) => ["owner", "admin"].includes(item.role)), projects });
      },
      (error) => { if (!controller.signal.aborted) setFailure(error); },
    );
    return () => controller.abort();
  }, [revision, retry]);
  if (view && !view.organizations.length) return null;
  if (!view && !failure) return null;
  const org = view?.organizations.find((item) => item.id === selected) || view?.organizations[0];
  const projects = view?.projects.filter((item) => item.org_id === org?.id) || [];
  return <section className="account-connections" aria-labelledby="account-connections-title">
    <div className="card project-panel account-model">
      <h2 id="account-connections-title">{t("اتصالات المؤسسة", "Organization connections")}</h2>
      {failure && <div className="workspace-error" role="alert">{errorText(failure, t)} <button type="button" className="btn" onClick={() => {
        setFailure(null);
        setRetry((value) => value + 1);
      }}>{t("إعادة المحاولة", "Retry")}</button></div>}
      {org && (view.organizations.length > 1 ? <label>{t("المؤسسة", "Organization")}
        <select value={org.id} onChange={(event) => setSelected(event.target.value)}>
          {view.organizations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label> : <p><bdi>{org.name}</bdi></p>)}
    </div>
    {org && <>
      <section className="card project-panel account-model">
        <h2><KeyRound size={19} aria-hidden="true" />{t("اتصال الموديل", "Model connection")}</h2>
        <ModelCredentials key={org.id} org={org.id} projects={projects} lang={lang} />
      </section>
      <GitHubConnections key={org.id} org={org} projects={projects} lang={lang} />
    </>}
  </section>;
}

export function AccountSettings({ lang, user, preferences, invitation, clearInvite, onJoined, onLogout, onProfileChange, personal }) {
  const t = translate(lang);
  const [pending, setPending] = useState(false);
  const [failure, setFailure] = useState(null);
  const [organizationsRevision, setOrganizationsRevision] = useState(0);
  return <div className="project-workspace account-workspace">
    <div className="project-header"><h1>{personal ? t("الإعدادات", "Settings") : t("الحساب", "Account")}</h1>
      {!personal && <button className="btn" type="button" onClick={async () => {
        if (pending) return;
        setPending(true);
        setFailure(null);
        try { await action(api + "/auth/logout", { method: "POST" }); onLogout(); }
        catch (error) { setFailure(error); }
        finally { setPending(false); }
      }} disabled={pending}><LogOut size={16} aria-hidden="true" />{t("تسجيل الخروج", "Sign out")}</button>}
    </div>
    {failure && <p className="workspace-error" role="alert">{errorText(failure, t)}</p>}
    <div className="account-settings-grid">
      <Profile lang={lang} user={user} onProfileChange={onProfileChange} />
      <section className="card project-panel account-settings-preferences">
      <h2>{t("التفضيلات", "Preferences")}</h2>
      <div className="account-preferences">
        <label><span><Languages size={19} aria-hidden="true" />{t("اللغة", "Language")}</span>
          <select value={preferences.lang} onChange={(event) => preferences.setLang(event.target.value)}>
            <option value="ar" lang="ar">العربية</option>
            <option value="en" lang="en">English</option>
          </select>
        </label>
        <label><span><Palette size={19} aria-hidden="true" />{t("المظهر", "Theme")}</span>
          <select value={preferences.theme} onChange={(event) => preferences.setTheme(event.target.value)}>
            <option value="dark">{t("داكن", "Dark")}</option>
            <option value="light">{t("فاتح", "Light")}</option>
          </select>
        </label>
      </div>
      </section>
    </div>
    {personal ? <ProviderSettings lang={lang} /> : <><JoinOrganization invitation={invitation} clearInvite={clearInvite} lang={lang} onJoined={() => {
      setOrganizationsRevision((value) => value + 1);
      onJoined();
    }} />
    <OrganizationConnections lang={lang} revision={organizationsRevision} /></>}
  </div>;
}
