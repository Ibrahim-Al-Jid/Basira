import React, { useEffect, useId, useRef, useState } from "react";
import { ClipboardPaste, FileCode2, FlaskConical, LoaderCircle, Upload, X } from "lucide-react";
import { num, sample } from "./data";
import "./source.css";

const MAX_BYTES = 1_000_000;
const MAX_CHARACTERS = 250_000;
const htmlName = /\.html?$/i;
const invalidName = /[\\/:\u0000-\u001F\u007F]/;

export const initialSource = { text: sample, kind: "sample" };

export function sourceMetadata({ text, kind, name }) {
  const normalized = text.replace(/\r\n?/g, "\n");
  return {
    kind,
    ...(kind === "file" && name ? { name } : {}),
    bytes: new TextEncoder().encode(text).length,
    lines: text ? normalized.split("\n").length : 0,
    encoding: "utf-8",
  };
}

export function sourceError(text) {
  if (!text.trim()) return "اختار ملف HTML أو الصق الكود.";
  if (text.length > MAX_CHARACTERS) {
    let characters = 0;
    for (const character of text) {
      characters++;
      if (characters > MAX_CHARACTERS) return "المصدر أطول من ٢٥٠ ألف حرف.";
    }
  }
  if (/[\uD800-\uDFFF]/u.test(text))
    return "المصدر فيه أحرف غير صالحة لترميز UTF-8.";
  if (/[\u0000-\u0008\u000B\u000E-\u001F]/.test(text))
    return "المصدر فيه بيانات غير نصية.";
  if (!text.includes(">") || !/<[A-Za-z][^<>\s/]*(?:[\s/>])/.test(text))
    return "المصدر لازم يحتوي على عنصر HTML واحد على الأقل.";
  return "";
}

export function SourcePicker({ source, setSource, disabled, onBusyChange }) {
  const id = useId();
  const input = useRef(null);
  const editor = useRef(null);
  const focusEditor = useRef(false);
  const reader = useRef(null);
  const depth = useRef(0);
  const [error, setError] = useState("");
  const [loadingName, setLoadingName] = useState("");
  const [dragging, setDragging] = useState(false);
  const { bytes, lines } = sourceMetadata(source);
  const pasteError = source.kind === "paste" && source.text ? sourceError(source.text) : "";

  useEffect(() => () => {
    const pending = reader.current;
    reader.current = null;
    pending?.abort();
    onBusyChange?.(false);
  }, [onBusyChange]);

  useEffect(() => {
    if (source.kind === "paste" && focusEditor.current) {
      focusEditor.current = false;
      editor.current?.focus();
    }
  }, [source.kind]);

  function cancelRead() {
    const pending = reader.current;
    if (!pending) return;
    reader.current = null;
    pending.abort();
    setLoadingName("");
    onBusyChange?.(false);
  }

  function changeSource(next) {
    cancelRead();
    setError("");
    setSource(next);
  }

  function openPaste() {
    focusEditor.current = true;
    changeSource({ text: "", kind: "paste" });
  }

  function loadFile(file) {
    if (disabled || !file) return;
    cancelRead();
    if (!htmlName.test(file.name)) {
      setError("اختار ملف بامتداد HTML أو HTM.");
      return;
    }
    if (file.name.length > 255 || invalidName.test(file.name)) {
      setError("اسم الملف طويل أو يحتوي على أحرف غير مسموح بها.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("الملف أكبر من ١ ميجابايت.");
      return;
    }
    setError("");
    setLoadingName(file.name);
    onBusyChange?.(true);

    const pending = new FileReader();
    reader.current = pending;
    function finish() {
      reader.current = null;
      setLoadingName("");
      onBusyChange?.(false);
    }
    pending.onload = () => {
      if (reader.current !== pending) return;
      finish();
      let text;
      try {
        text = new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(pending.result);
      } catch {
        setError("ملف HTML لازم يكون محفوظ بترميز UTF-8 صالح.");
        return;
      }
      const message = sourceError(text);
      if (message) {
        setError(message);
        return;
      }
      setSource({ text, kind: "file", name: file.name });
    };
    pending.onerror = () => {
      if (reader.current !== pending) return;
      finish();
      setError("تعذّرت قراءة الملف. اختاره مرة تانية.");
    };
    pending.readAsArrayBuffer(file);
  }

  function filesDragged(event) {
    return event.dataTransfer.types.includes("Files");
  }

  return (
    <section className="marsad-source" aria-labelledby={id + "-title"}>
      <div className="marsad-source-heading">
        <div>
          <h2 id={id + "-title"}>مصدر الفحص</h2>
          <p id={id + "-hint"}>اختار ملف HTML أو HTM بترميز UTF-8، لحد ١ ميجابايت و٢٥٠ ألف حرف.</p>
        </div>
        <div className="marsad-source-alternatives">
          {source.kind !== "paste" && (
            <button className="subtle" disabled={disabled} onClick={openPaste}>
              <ClipboardPaste size={15} aria-hidden="true" /> لصق HTML
            </button>
          )}
          {source.kind !== "sample" && (
            <button className="subtle" disabled={disabled} onClick={() => changeSource(initialSource)}>
              <FlaskConical size={15} aria-hidden="true" /> استرجاع العينة
            </button>
          )}
        </div>
      </div>

      <div
        className={"marsad-source-drop" + (dragging ? " dragging" : "")}
        onDragEnter={(event) => {
          if (!filesDragged(event)) return;
          event.preventDefault();
          if (disabled) return;
          depth.current++;
          setDragging(true);
        }}
        onDragLeave={() => {
          depth.current = Math.max(depth.current - 1, 0);
          if (depth.current === 0) setDragging(false);
        }}
        onDragOver={(event) => {
          if (!filesDragged(event)) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = disabled ? "none" : "copy";
        }}
        onDrop={(event) => {
          if (!filesDragged(event)) return;
          event.preventDefault();
          depth.current = 0;
          setDragging(false);
          if (disabled) return;
          const { files } = event.dataTransfer;
          if (files.length === 1) loadFile(files[0]);
          else if (files.length > 1) setError("اختار ملف واحد لكل فحص.");
        }}
      >
        <Upload size={20} aria-hidden="true" />
        <p>اسحب ملف هنا أو اختاره من جهازك</p>
        <button
          className="btn"
          disabled={disabled}
          aria-describedby={id + "-hint"}
          onClick={() => input.current.click()}
        >
          {source.kind === "file" ? "استبدال الملف" : "اختيار ملف HTML"}
        </button>
        <input
          ref={input}
          type="file"
          hidden
          disabled={disabled}
          accept=".html,.htm,text/html"
          aria-label="ملف HTML"
          onChange={(event) => {
            const [file] = event.target.files;
            event.target.value = "";
            loadFile(file);
          }}
        />
      </div>

      {loadingName && (
        <div className="marsad-source-reading">
          <p role="status"><LoaderCircle className="spin" size={15} aria-hidden="true" /> قراءة <bdi>{loadingName}</bdi></p>
          <button className="subtle" onClick={cancelRead}>إلغاء قراءة الملف</button>
        </div>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {source.kind === "paste" && (
        <div className="marsad-source-editor">
          <label htmlFor={id + "-html"}>كود HTML</label>
          <textarea
            ref={editor}
            id={id + "-html"}
            dir="ltr"
            spellCheck={false}
            disabled={disabled || Boolean(loadingName)}
            aria-invalid={Boolean(pasteError)}
            aria-describedby={pasteError ? id + "-paste-error" : undefined}
            value={source.text}
            placeholder="&lt;main&gt;...&lt;/main&gt;"
            onChange={(event) => changeSource({ text: event.target.value, kind: "paste" })}
          />
          {pasteError && <p className="error" id={id + "-paste-error"}>{pasteError}</p>}
        </div>
      )}
      {source.text && (
        <div className="marsad-source-current">
          <FileCode2 size={20} aria-hidden="true" />
          <div>
            <strong><bdi>{source.name || (source.kind === "sample" ? "عينة مرصد" : "HTML ملصوق")}</bdi></strong>
            <small>{num(bytes)} بايت · {num(lines)} سطر · <bdi>UTF-8</bdi></small>
          </div>
          {source.kind === "file" && (
            <button className="subtle" disabled={disabled} onClick={openPaste}>
              <X size={15} aria-hidden="true" /> إزالة الملف
            </button>
          )}
        </div>
      )}
    </section>
  );
}
