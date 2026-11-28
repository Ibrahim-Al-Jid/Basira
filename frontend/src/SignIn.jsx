import React, { useEffect, useId, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Building2,
  Eye,
  EyeOff,
  FileCheck2,
  Mail,
  Moon,
  ScanLine,
  ShieldCheck,
  Sun,
} from "lucide-react";
import { post } from "./data";
import { api, action, errorText, translate } from "./platformClient";
import "./signin.css";

const fieldMessages = {
  first_name: ["اكتب الاسم الأول بحروف من غير أرقام أو شرطة سفلية.", "Enter a first name using letters, without digits or underscores."],
  last_name: ["اكتب اسم العائلة بحروف من غير أرقام أو شرطة سفلية.", "Enter a last name using letters, without digits or underscores."],
  email: ["اكتب البريد الإلكتروني بصيغة صحيحة.", "Enter a valid email address."],
  password: ["راجع كلمة المرور. الحد الأقصى ١٢٨ حرف.", "Check your password. The maximum length is 128 characters."],
};

const content = {
  ar: {
    kicker: "مراجعة أمنية للمشاريع",
    stageTitle: "من ملفات المشروع إلى تقرير واضح.",
    points: [
      [ShieldCheck, "كل نتيجة معاها دليلها", "الملف والسطر والقاعدة اللي انطبقت، وتقدر تفتح المصدر."],
      [FileCheck2, "عربي وإنجليزي من نفس الحقائق", "التقرير بيتكتب باللغتين من نفس البيانات، من غير فرق في الأرقام."],
      [ScanLine, "شغال من غير مزوّد موديل", "القواعد المحلية بتشتغل لوحدها، والموديل اختياري."],
    ],
    limits: "التغطية بتتكتب صريحة: اللي اتفحص واللي لأ. النتيجة النضيفة مش إثبات إن المشروع آمن.",
    home: "الرئيسية",
    toLight: "الوضع الفاتح",
    toDark: "الوضع الغامق",
    switchLanguage: "English",
    switchLanguageLabel: "التبديل إلى الإنجليزية",
  },
  en: {
    kicker: "Project security review",
    stageTitle: "From project files to a clear report.",
    points: [
      [ShieldCheck, "Every finding carries its evidence", "The file, the line and the check that applied, with the source one click away."],
      [FileCheck2, "Arabic and English from the same facts", "Both reports are written from the same data, with no difference in the numbers."],
      [ScanLine, "Works with no model provider", "The local checks run on their own; a model is optional."],
    ],
    limits: "Coverage is stated plainly: what was checked and what was not. A clean result is not proof the project is safe.",
    home: "Home",
    toLight: "Light theme",
    toDark: "Dark theme",
    switchLanguage: "ع",
    switchLanguageLabel: "Switch to Arabic",
  },
};

export function SignIn({ onAuthenticated, lang, personal, startInRegister, navigate, preferences }) {
  const t = translate(lang);
  const copy = content[lang === "en" ? "en" : "ar"];
  const [options, setOptions] = useState(null);
  const [optionsError, setOptionsError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [mode, setMode] = useState(startInRegister ? "register" : "login");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const activeRequest = useRef(null);
  const titleId = useId();
  const title = useRef(null);
  const focusTitle = useRef(false);
  const passwordId = useId();
  const hintId = useId();
  const errorId = useId();
  const register = mode === "register" && options?.registration !== false;
  const DirectionArrow = lang === "ar" ? ArrowLeft : ArrowRight;
  const home = (event) => {
    if (!navigate || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button) return;
    event.preventDefault();
    navigate("/");
  };

  function fieldError(name) {
    return error?.fields.includes(name)
      ? { "aria-invalid": true, "aria-errormessage": errorId }
      : {};
  }

  useEffect(() => {
    const controller = new AbortController();
    action(api + "/auth/options", { signal: controller.signal }).then(
      (value) => { if (!controller.signal.aborted) setOptions(value); },
      (err) => { if (!controller.signal.aborted) setOptionsError(errorText(err, t)); },
    );
    return () => controller.abort();
  }, [attempt]);
  useEffect(() => () => activeRequest.current?.abort(), []);
  useEffect(() => {
    if (focusTitle.current) title.current?.focus();
  }, [mode]);

  function changeMode(next) {
    if (next === mode) return;
    focusTitle.current = true;
    setMode(next);
    setError(null);
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
      setError({
        fields: ["password"],
        message: register ? t("كلمة المرور لازم تكون بين ١٢ و١٢٨ حرف.", "Use a password with 12 to 128 characters.")
          : t("الحد الأقصى لكلمة المرور ١٢٨ حرف.", "Your password can have up to 128 characters."),
      });
      return;
    }
    setError(null);
    setBusy(true);
    const controller = new AbortController();
    activeRequest.current = controller;
    try {
      const account = await action(`${api}/auth/password/${register ? "register" : "login"}`, {
        ...post({
          email: data.get("email").trim(), password,
          ...(register ? { first_name: data.get("first_name").trim(), last_name: data.get("last_name").trim() } : {}),
        }),
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      if (!account?.id || typeof account.display_name !== "string") throw Error("رد تسجيل الدخول غير صالح.");
      form.reset();
      onAuthenticated(account);
    } catch (err) {
      if (!controller.signal.aborted) {
        const fields = (err.fields ?? []).filter((field) => Object.hasOwn(fieldMessages, field));
        const message = fields.map((field) => t(...fieldMessages[field])).join(" ") || errorText(err, t);
        setError({ fields, message });
      }
    } finally {
      activeRequest.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  return (
    <div className="signin-page">
      <div className="signin-topbar">
        <a className="signin-brand" href="/" onClick={home}>
          <span className="signin-brand-mark" aria-hidden="true"><ShieldCheck size={26} strokeWidth={1.7} /></span>
          <span dir="ltr">BASIRA</span>
        </a>
        <div className="signin-controls">
          {preferences && (
            <>
              <button type="button" className="signin-control" aria-pressed={preferences.theme === "dark"}
                aria-label={preferences.theme === "dark" ? copy.toLight : copy.toDark}
                onClick={() => preferences.setTheme(preferences.theme === "dark" ? "light" : "dark")}>
                {preferences.theme === "dark" ? <Sun size={18} aria-hidden="true" /> : <Moon size={18} aria-hidden="true" />}
              </button>
              <button type="button" className="signin-control signin-control-word" aria-label={copy.switchLanguage + ", " + copy.switchLanguageLabel}
                onClick={() => preferences.setLang(lang === "ar" ? "en" : "ar")}>
                {copy.switchLanguage}
              </button>
            </>
          )}
          <a className="signin-control signin-control-word" href="/" onClick={home}>{copy.home}</a>
        </div>
      </div>
      <div className="signin-shell">
        <section className="signin-stage" aria-labelledby="signin-stage-title">
          <p className="signin-kicker"><span aria-hidden="true" />{copy.kicker}</p>
          <p className="signin-stage-title" id="signin-stage-title">{copy.stageTitle}</p>
          <ul className="signin-points">
            {copy.points.map(([Icon, heading, detail]) => (
              <li key={heading}>
                <span className="signin-point-icon" aria-hidden="true"><Icon size={19} /></span>
                <span><strong>{heading}</strong><small>{detail}</small></span>
              </li>
            ))}
          </ul>
          <p className="signin-limits">{copy.limits}</p>
        </section>
        <div className="signin-card">
          <header className="signin-heading">
            <h1 id={titleId} ref={title} tabIndex={-1}>{register ? t("أنشئ حسابك", "Create your account") : t("سجّل دخولك إلى بصيرة", "Sign in to Basira")}</h1>
            <p>{register ? t("ابدأ مشروعك الأول واحتفظ بتقاريرك في مكان واحد.", "Start your first project and keep your reports in one place.")
              : t("ادخل على مشاريعك وتقاريرك.", "Access your projects and reports.")}</p>
          </header>
          {!options && !optionsError && <p className="signin-status" role="status">{t("جاري تحميل طرق تسجيل الدخول…", "Loading sign-in options…")}</p>}
          {optionsError && <div className="signin-feedback">
            <p className="signin-error" role="alert">{optionsError}</p>
            <button className="signin-secondary" type="button" onClick={() => {
              setOptionsError("");
              setAttempt((value) => value + 1);
            }}>{t("إعادة المحاولة", "Retry")}</button>
          </div>}
          {options?.password && <form className="signin-form" onSubmit={submit} aria-busy={busy}>
            {register && <div className="signin-row">
              <label className="signin-field">{t("الاسم الأول", "First name")}
                <input name="first_name" dir="auto" autoComplete="given-name" maxLength={80} required disabled={busy} {...fieldError("first_name")} />
              </label>
              <label className="signin-field">{t("اسم العائلة", "Last name")}
                <input name="last_name" dir="auto" autoComplete="family-name" maxLength={80} required disabled={busy} {...fieldError("last_name")} />
              </label>
            </div>}
            <label className="signin-field">{t("البريد الإلكتروني", "Email")}
              <span className="signin-input">
                <Mail size={17} aria-hidden="true" />
                <input name="email" type="email" autoComplete="username" dir="ltr" maxLength={254} required disabled={busy} {...fieldError("email")} />
              </span>
            </label>
            <div className="signin-field">
              <label htmlFor={passwordId}>{t("كلمة المرور", "Password")}</label>
              <div className="signin-input signin-secret">
                <input key={mode} id={passwordId} name="password" type={showPassword ? "text" : "password"} dir="ltr"
                  autoComplete={register ? "new-password" : "current-password"}
                  aria-describedby={register ? hintId : undefined}
                  maxLength={256} required disabled={busy} {...fieldError("password")} />
                <button type="button" aria-controls={passwordId} disabled={busy}
                  aria-label={showPassword ? t("إخفاء كلمة المرور", "Hide password") : t("إظهار كلمة المرور", "Show password")}
                  onClick={() => setShowPassword((value) => !value)}>
                  {showPassword ? <EyeOff size={19} aria-hidden="true" /> : <Eye size={19} aria-hidden="true" />}
                </button>
              </div>
              {register && <p id={hintId} className="signin-hint">{t("من ١٢ إلى ١٢٨ حرف.", "12 to 128 characters.")}</p>}
            </div>
            {error && <p id={errorId} className="signin-error" role="alert">{error.message}</p>}
            <button className="signin-submit" disabled={busy}>
              {busy ? (register ? t("جاري إنشاء الحساب…", "Creating account…") : t("جاري تسجيل الدخول…", "Signing in…"))
                : (register ? t("إنشاء الحساب", "Create account") : t("تسجيل الدخول", "Sign in"))}
              <DirectionArrow size={18} aria-hidden="true" />
            </button>
          </form>}
          {options?.oidc && <a className="signin-secondary signin-oidc" href={api + "/auth/login"}>
            <Building2 size={18} aria-hidden="true" />{personal ? t("الدخول بمزوّد الهوية", "Sign in with identity provider")
              : t("الدخول بحساب المؤسسة", "Sign in with your organization")}
          </a>}
          {options && !options.password && !options.oidc && <p className="signin-status" role="status">{t("تسجيل الدخول للمشاريع غير متاح حاليًا.", "Project sign-in is currently unavailable.")}</p>}
          {options?.password && options.registration && <div className="signin-switch">
            <span>{register ? t("عندك حساب بالفعل؟", "Already have an account?") : t("أول مرة تستخدم بصيرة؟", "New to Basira?")}</span>
            <button type="button" disabled={busy} onClick={() => changeMode(register ? "login" : "register")}>
              {register ? t("عندي حساب", "I have an account") : t("إنشاء حساب", "Create an account")}
            </button>
          </div>}
        </div>
      </div>
    </div>
  );
}
