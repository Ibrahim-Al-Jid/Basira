import React, { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { fetchJson, post } from "./data";
import "./platform.css";

const api = "/api/platform";
const kindLabels = { html: "HTML", repository: "لقطة مستودع ZIP", har: "لقطة استجابات HAR", config: "لقطة إعدادات JSON" };
const extensions = { html: ".html,.htm", repository: ".zip", har: ".har", config: ".json" };
const states = { queued: "في الانتظار", running: "قيد التنفيذ", completed: "مكتمل", partial: "جزئي", failed: "فشل", cancelled: "أُلغي" };
const projectApi = (id) => `${api}/projects/${id}`;
const scanLink = (project, scan) => `/projects/${project}/scans/${scan}`;
const reportLink = (project, report = "") => `/reports${report && "/" + report}?project=${project}`;
const json = (method, body) => ({ ...post(body), method });

async function action(path, options) {
  const response = await fetch(path, options);
  if (response.status === 204) return null;
  const value = await response.json().catch(() => null);
  if (!response.ok) {
    const fallback = response.status === 429 ? "محاولات كتير في وقت قصير. استنى شوية وحاول تاني." : "تعذّر تنفيذ الطلب.";
    throw Error(typeof value?.detail === "string" ? value.detail : fallback);
  }
  return value;
}

function encoded(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",", 2)[1]);
    reader.onerror = () => reject(Error("تعذّر قراءة الملف."));
    reader.readAsDataURL(file);
  });
}

function Panel({ title, children }) {
  return <section className="card project-panel"><h2>{title}</h2>{children}</section>;
}

function AccountAccess({ onAuthenticated }) {
  const [options, setOptions] = useState(null);
  const [optionsError, setOptionsError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState("login");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const activeRequest = useRef(null);
  const titleId = useId();
  const passwordId = useId();
  const hintId = useId();
  const register = mode === "register";

  useEffect(() => {
    const controller = new AbortController();
    action(api + "/auth/options", { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setOptions(value); },
      (err) => { if (!controller.signal.aborted) setOptionsError(err.message); },
    );
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => () => activeRequest.current?.abort(), []);

  function changeMode(next) {
    if (next === mode) return;
    setMode(next);
    setError("");
    setShowPassword(false);
  }

  async function submit(event) {
    event.preventDefault();
    if (activeRequest.current) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const password = data.get("password");
    const length = [...password].length;
    if (length > 128 || (register && length < 12)) {
      setError(register ? "كلمة المرور لازم تكون بين ١٢ و١٢٨ حرف." : "الحد الأقصى لكلمة المرور ١٢٨ حرف.");
      return;
    }
    setError("");
    setBusy(true);
    const controller = new AbortController();
    activeRequest.current = controller;
    try {
      const account = await action(`${api}/auth/password/${mode}`, {
        ...post({ email: data.get("email").trim(), password }),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (!account?.id || typeof account.display_name !== "string") throw Error("رد تسجيل الدخول غير صالح.");
      form.reset();
      onAuthenticated(account);
    } catch (err) {
      if (!controller.signal.aborted) setError(err.message);
    } finally {
      activeRequest.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <section className="card project-panel project-account" aria-labelledby={titleId}>
      <header className="project-account-heading">
        <h1 id={titleId}>حساب المشاريع</h1>
        <p>سجّل الدخول عشان تستخدم مشاريع الفرق وتتابع الفحوصات والتقارير.</p>
      </header>
      {!options && !optionsError && <p role="status">جاري تحميل طرق تسجيل الدخول…</p>}
      {optionsError && (
        <div className="project-account-feedback">
          <p className="error" role="alert">{optionsError}</p>
          <button className="btn" type="button" onClick={() => {
            setOptionsError("");
            setAttempt((value) => value + 1);
          }}>إعادة المحاولة</button>
        </div>
      )}
      {options?.password && (
        <>
          {options.registration && (
            <div className="project-account-modes" role="group" aria-label="نوع الحساب">
              <button type="button" aria-pressed={!register} disabled={busy} onClick={() => changeMode("login")}>عندي حساب</button>
              <button type="button" aria-pressed={register} disabled={busy} onClick={() => changeMode("register")}>إنشاء حساب</button>
            </div>
          )}
          <form className="project-form project-account-form" onSubmit={submit} aria-busy={busy}>
            <label>البريد الإلكتروني
              <input name="email" type="email" autoComplete="username" dir="ltr" maxLength={254} required disabled={busy} />
            </label>
            <label htmlFor={passwordId}>كلمة المرور</label>
            <div className="project-password-field">
              <input key={mode} id={passwordId} name="password" type={showPassword ? "text" : "password"} dir="ltr"
                autoComplete={register ? "new-password" : "current-password"}
                aria-describedby={register ? hintId : undefined}
                maxLength={256} required disabled={busy} />
              <button className="btn" type="button" aria-controls={passwordId} disabled={busy}
                onClick={() => setShowPassword((value) => !value)}>
                {showPassword ? "إخفاء كلمة المرور" : "إظهار كلمة المرور"}
              </button>
            </div>
            {register && <p id={hintId} className="project-account-hint">من ١٢ إلى ١٢٨ حرف.</p>}
            {error && <p className="error" role="alert">{error}</p>}
            <button className="btn primary" disabled={busy}>
              {register ? "إنشاء الحساب" : "تسجيل الدخول"}
            </button>
            {busy && <p role="status" className="project-account-hint">{register ? "جاري إنشاء الحساب…" : "جاري تسجيل الدخول…"}</p>}
          </form>
        </>
      )}
      {options?.oidc && <a className="btn" href={api + "/auth/login"}>الدخول بحساب المؤسسة</a>}
      {options && !options.password && !options.oidc && <p role="status">تسجيل الدخول للمشاريع غير متاح حاليًا.</p>}
      <a className="project-account-lab" href="/">فتح المختبر المحلي من غير حساب</a>
    </section>
  );
}

function ScanStatus({ projectId, scanId }) {
  const [scan, setScan] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [reload, setReload] = useState(0);
  const [canScan, setCanScan] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer;
    let cursor = 0;
    setScan(null);
    setEvents([]);
    setError("");
    fetchJson(api + "/projects", { signal: controller.signal }).then(
      ({ projects }) => setCanScan(projects.some((item) => item.id === projectId && item.role !== "viewer")),
      () => {},
    );
    async function poll() {
      try {
        const view = await fetchJson(`${projectApi(projectId)}/scans/${scanId}?after=${cursor}`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        setScan(view);
        setError("");
        if (view.events.length) {
          cursor = view.events.at(-1).sequence;
          setEvents((current) => [...current, ...view.events]);
        }
        if (cursor < view.cursor || ["queued", "running"].includes(view.state)) timer = setTimeout(poll, 1200);
      } catch (err) {
        if (err.name !== "AbortError") setError(err.message);
      }
    }
    poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [projectId, scanId, reload]);
  async function cancel() {
    setCancelling(true);
    try {
      await action(projectApi(projectId) + "/scans/" + scanId + "/cancel", { method: "POST" });
      setReload((count) => count + 1);
    } catch (err) { setError(err.message); }
    finally { setCancelling(false); }
  }
  return (
    <div className="project-workspace">
      <a href={"/projects?project=" + projectId}>العودة للمشروع</a>
      <h1>متابعة الفحص</h1>
      {error && <p className="error" role="alert">{error} <button className="btn" onClick={() => setReload((n) => n + 1)}>إعادة المحاولة</button></p>}
      {!scan && !error && <p role="status">جاري تحميل حالة الفحص…</p>}
      {scan && <Panel title={states[scan.state] || scan.state}>
        <p><bdi>{scan.artifact.name}</bdi> · محاولة {scan.attempt}</p>
        {scan.report_available && <a className="btn primary" href={reportLink(projectId, scan.id)}>فتح التقرير</a>}
        {canScan && ["queued", "running"].includes(scan.state) &&
          <button className="btn" onClick={cancel} disabled={cancelling}>إلغاء الفحص</button>}
        <ol className="trace">{events.map((item) => <li key={item.sequence}>
          <b>{states[item.kind] || item.kind}</b>
          <p>{item.detail}</p>
          <time dateTime={item.occurred_at}>{new Date(item.occurred_at).toLocaleString("ar-EG")}</time>
        </li>)}</ol>
      </Panel>}
    </div>
  );
}

function Dashboard({ location, navigate, user, onLogout }) {
  const [organizations, setOrganizations] = useState([]);
  const [projects, setProjects] = useState([]);
  const [error, setError] = useState("");
  const [snapshotState, setSnapshot] = useState(null);
  const [memoryState, setMemory] = useState(null);
  const [busy, setBusy] = useState(false);
  const upload = useRef({ file: null, id: null });
  const selected = new URLSearchParams(location.search).get("project");
  const project = projects.find((item) => item.id === selected);
  const path = project ? projectApi(project.id) : null;
  const activePath = useRef(path);
  const snapshot = snapshotState?.path === path ? snapshotState : null;
  const memory = memoryState?.path === path ? memoryState.value : null;
  const manage = project && ["owner", "admin"].includes(project.role);
  useLayoutEffect(() => { activePath.current = path; }, [path]);

  async function loadMemory() {
    const value = await fetchJson(path + "/memory");
    if (activePath.current === path) setMemory({ path, value });
  }

  async function refreshDashboard(signal) {
    const [orgs, work] = await Promise.all([
      fetchJson(api + "/organizations", { signal }), fetchJson(api + "/projects", { signal }),
    ]);
    if (!signal?.aborted) {
      setOrganizations(orgs.organizations);
      setProjects(work.projects);
    }
  }
  useEffect(() => {
    const controller = new AbortController();
    refreshDashboard(controller.signal).catch((err) => {
      if (!controller.signal.aborted) setError(err.message);
    });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    setSnapshot(null);
    setMemory(null);
    upload.current = { file: null, id: null };
    if (!path) return;
    const controller = new AbortController();
    const signal = controller.signal;
    Promise.all([fetchJson(path + "/policy", { signal }), fetchJson(path + "/scans", { signal })])
      .then(([policy, scans]) => {
        if (!signal.aborted && activePath.current === path) setSnapshot({ ...policy, path, scans: scans.scans });
      })
      .catch((err) => { if (!signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [path]);
  async function submit(event, operation) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setError("");
    setBusy(true);
    try { await operation(form); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  }
  return <div className="project-workspace">
    <div className="project-header">
      <div><h1>المشاريع</h1><p><bdi>{user.display_name}</bdi> · <code dir="ltr">{user.id}</code></p></div>
      <button className="btn" disabled={busy} onClick={async () => {
        setBusy(true);
        setError("");
        try { await action(api + "/auth/logout", { method: "POST" }); onLogout(); }
        catch (err) { setError(err.message); }
        finally { setBusy(false); }
      }}>تسجيل الخروج</button>
    </div>
    <a href="/checks">كتالوج فحوصات المشاريع · ١٠٠ قاعدة</a>
    {error && <p className="error" role="alert">{error}</p>}
    <Panel title="المؤسسات والمشاريع">
      <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
        await action(api + "/organizations", post({ name: data.get("name") }));
        await refreshDashboard();
      })}>
        <label>اسم المؤسسة<input name="name" maxLength={120} required /></label>
        <button className="btn" disabled={busy}>إنشاء مؤسسة</button>
      </form>
      {organizations.some((org) => ["owner", "admin"].includes(org.role)) && (
        <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          const created = await action(api + "/organizations/" + data.get("org") + "/projects", post({ name: data.get("name") }));
          await refreshDashboard();
          navigate("/projects?project=" + created.id);
        })}>
          <label>المؤسسة<select name="org">{organizations.filter((org) => ["owner", "admin"].includes(org.role))
            .map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}</select></label>
          <label>اسم المشروع<input name="name" maxLength={120} required /></label>
          <button className="btn" disabled={busy}>إنشاء مشروع</button>
        </form>
      )}
      <label>المشروع الحالي
        <select value={selected || ""} onChange={(event) => navigate(event.target.value ? "/projects?project=" + event.target.value : "/projects")}>
          <option value="">اختار مشروع</option>
          {projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>
    </Panel>
    {project && snapshot && <div className="project-grid" key={project.id}>
      <Panel title="فحوصات المشروع">
        <a className="btn" href={reportLink(project.id)}>تقارير المشروع</a>
        {project.role !== "viewer" && <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          const file = data.get("file");
          const kind = data.get("kind");
          if (!file.size || file.size > 2_000_000) throw Error("الملف لازم يكون بين ١ بايت و٢ ميجابايت.");
          const tag = [file.name, file.size, file.lastModified, kind, data.has("enrich")].join(":");
          if (upload.current.file !== tag) upload.current = { file: tag, id: crypto.randomUUID() };
          const options = post({ kind, name: file.name, content: await encoded(file), enrich: data.has("enrich") });
          options.headers["Idempotency-Key"] = upload.current.id;
          const scan = await action(path + "/scans", options);
          upload.current = { file: null, id: null };
          if (activePath.current === path) navigate(scanLink(project.id, scan.id));
        })}>
          <label>نوع المدخل<select name="kind" onChange={(event) => {
            event.currentTarget.form.elements.file.accept = extensions[event.target.value];
            event.currentTarget.form.elements.file.value = "";
          }}>
            {snapshot.policy.allowed_kinds.map((kind) => <option key={kind} value={kind}>{kindLabels[kind]}</option>)}
          </select></label>
          <label>اختيار ملف<input name="file" type="file" required accept={extensions[snapshot.policy.allowed_kinds[0]]} /></label>
          <label className="project-check"><input name="enrich" type="checkbox" /> ترتيب أولويات بالموديل عند توفره</label>
          <button className="btn primary" disabled={busy}>إرسال الفحص</button>
        </form>}
        {snapshot.scans.length ? <ul className="project-list">{snapshot.scans.map((item) => <li key={item.id}>
          <a href={scanLink(project.id, item.id)}><bdi>{item.artifact.name}</bdi></a> · {states[item.state]}
        </li>)}</ul> : <p>لسه مفيش فحوصات للمشروع ده.</p>}
      </Panel>
      {manage && <Panel title="سياسة المدخلات والهدف">
        <p>عنوان الهدف للربط بس. الفحص بيحلل الملفات اللي رفعتها.</p>
        <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          const policy = await action(path + "/policy", json("PUT", {
            allowed_kinds: data.getAll("kinds"), base_url: data.get("url") || null,
            rules: JSON.parse(data.get("rules") || "{}"),
          }));
          if (activePath.current === path) setSnapshot((old) => old?.path === path ? { ...old, ...policy } : old);
        })}>
          <label>عنوان الهدف<input name="url" type="url" dir="ltr" defaultValue={snapshot.policy.base_url || ""} /></label>
          <fieldset><legend>أنواع المدخل المسموحة</legend>
            {Object.entries(kindLabels).map(([id, title]) => <label className="project-check" key={id}>
              <input type="checkbox" name="kinds" value={id} defaultChecked={snapshot.policy.allowed_kinds.includes(id)} /> {title}
            </label>)}
          </fieldset>
          <label>خيارات القواعد (JSON)<textarea name="rules" dir="ltr" rows={4}
            defaultValue={JSON.stringify(Object.fromEntries(Object.entries(snapshot.policy)
              .filter(([key]) => !["allowed_kinds", "base_url"].includes(key))), null, 2)} /></label>
          <button className="btn" disabled={busy}>حفظ السياسة</button>
        </form>
      </Panel>}
      <Panel title="ذاكرة المشروع">
        <button className="btn" onClick={async () => {
          try { await loadMemory(); }
          catch (err) { setError(err.message); }
        }}>تحميل سياق المشروع</button>
        {memory && <dl className="spec">{Object.entries({
          working: "حالة التشغيل", episodic: "تاريخ الفحوصات", semantic: "المراجع",
          procedural: "القواعد", project: "سياسة المشروع", finding: "تاريخ النتائج",
        }).map(([id, title]) => <React.Fragment key={id}>
          <dt>{title}</dt><dd>{Array.isArray(memory[id]) ? memory[id].length : memory[id].version}</dd>
        </React.Fragment>)}</dl>}
        {memory?.semantic?.map((note) => <article key={note.id}><h3>{note.title}</h3><p>{note.note}</p>
          <p dir="auto">{note.reference}</p>{manage && <button className="btn" onClick={async () => {
            try { await action(path + "/memory/knowledge/" + note.id, { method: "DELETE" });
              await loadMemory(); }
            catch (err) { setError(err.message); }
          }}>إلغاء المرجع</button>}</article>)}
        {manage && <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          await action(path + "/memory/knowledge", post(Object.fromEntries(data)));
          await loadMemory();
        })}>
          <label>العنوان<input name="title" maxLength={160} required /></label>
          <label>المصدر<input name="reference" maxLength={500} required /></label>
          <label>المعلومة<textarea name="note" maxLength={2000} required /></label>
          <button className="btn" disabled={busy}>إضافة مرجع</button>
        </form>}
      </Panel>
      {manage && <Panel title="إدارة صلاحيات الوصول">
        <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          const userId = encodeURIComponent(data.get("user_id").trim());
          const target = data.get("target");
          const remove = data.get("change") === "revoke";
          const endpoint = target === "project" ? path + "/grants" : api + "/organizations/" + project.org_id + "/members";
          await action(endpoint + (remove ? "/" + userId : ""), remove ? { method: "DELETE" } : post(
            target === "project" ? { user_id: userId } : { user_id: userId, role: data.get("role") },
          ));
          await refreshDashboard();
        })}>
          <label>معرّف المستخدم<input name="user_id" dir="ltr" required pattern="[a-f0-9]{32}" /></label>
          <label>النطاق<select name="target"><option value="project">إذن المشروع</option>
            {project.role === "owner" && <option value="org">عضوية المؤسسة</option>}</select></label>
          <label>الدور عند إضافة العضوية<select name="role"><option value="viewer">Viewer</option>
            <option value="analyst">Analyst</option><option value="admin">Admin</option></select></label>
          <label>الإجراء<select name="change"><option value="grant">إضافة أو تعديل</option><option value="revoke">إبطال</option></select></label>
          <button className="btn" disabled={busy}>حفظ الصلاحية</button>
        </form>
      </Panel>}
      {project.role !== "viewer" && <Panel title="ربط تقرير من الجلسة المحلية">
        <form className="project-form" onSubmit={(event) => submit(event, async (data) => {
          const id = encodeURIComponent(data.get("id").trim());
          await action(path + "/reports/" + id + "/claim", post({ confirm: true }));
          if (activePath.current === path) navigate(reportLink(project.id, id));
        })}>
          <label>معرّف التقرير<input name="id" dir="ltr" required pattern="[a-f0-9]{32}" /></label>
          <label className="project-check"><input type="checkbox" required /> أوافق على إضافة نسخة للمشروع</label>
          <button className="btn" disabled={busy}>ربط التقرير</button>
        </form>
      </Panel>}
    </div>}
  </div>;
}

function ProjectAccount({ location, navigate }) {
  const [user, setUser] = useState(undefined);
  useEffect(() => {
    const controller = new AbortController();
    fetchJson(api + "/auth/me", { signal: controller.signal }).then(
      (account) => { if (!controller.signal.aborted) setUser(account); },
      () => { if (!controller.signal.aborted) setUser(null); },
    );
    return () => controller.abort();
  }, []);

  if (user === undefined) return <p role="status">جاري التحقق من الجلسة…</p>;
  if (!user) return <AccountAccess onAuthenticated={setUser} />;
  return <Dashboard location={location} navigate={navigate} user={user} onLogout={() => setUser(null)} />;
}

export function Platform({ location, navigate }) {
  const match = /^\/projects\/([a-f0-9]{32})\/scans\/([a-f0-9]{32})\/?$/.exec(location.pathname);
  return match ? <ScanStatus key={match[2]} projectId={match[1]} scanId={match[2]} />
    : <ProjectAccount location={location} navigate={navigate} />;
}
