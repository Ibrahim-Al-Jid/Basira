import React, { useEffect, useId, useRef, useState } from "react";
import { ClipboardPaste, FileCode2, FlaskConical, LoaderCircle, Upload, X } from "lucide-react";
import { num, sample } from "./data";
import "./source.css";

const MAX_BYTES = 1_000_000;
const MAX_CHARACTERS = 250_000;
const htmlName = /\.html?$/i;
const invalidName = /[\\/:\u0000-\u001F\u007F]/;

const sampleSource = { text: sample, kind: "sample" };
export const emptySource = { text: "", kind: "empty" };

const sourceCopy = {
  ar: {
    empty: "اختار ملف HTML أو الصق الكود.", tooLong: "المصدر أطول من ٢٥٠ ألف حرف.",
    characters: "المصدر فيه أحرف غير صالحة لترميز UTF-8.", binary: "المصدر فيه بيانات غير نصية.",
    missingHtml: "المصدر لازم يحتوي على عنصر HTML واحد على الأقل.",
    extension: "اختار ملف بامتداد HTML أو HTM.", fileName: "اسم الملف طويل أو يحتوي على أحرف غير مسموح بها.",
    fileSize: "الملف أكبر من ١ ميجابايت.", encoding: "ملف HTML لازم يكون محفوظ بترميز UTF-8 صالح.",
    read: "تعذّرت قراءة الملف. اختاره مرة تانية.", oneFile: "اختار ملف واحد لكل فحص.",
    title: "مصدر الفحص", hint: "اختار ملف HTML أو HTM بترميز UTF-8، لحد ١ ميجابايت و٢٥٠ ألف حرف.",
    paste: "لصق HTML", sampleAction: "تحميل العينة", drop: "اسحب ملف هنا أو اختاره من جهازك",
    replace: "استبدال الملف", upload: "اختيار ملف HTML", input: "ملف HTML", reading: "قراءة",
    cancel: "إلغاء قراءة الملف", code: "كود HTML", sample: "عينة بصيرة", pasted: "HTML ملصوق",
    remove: "إزالة الملف", clear: "مسح المصدر",
    metadata: (bytes, lines) => `${num(bytes)} بايت · ${num(lines)} سطر`,
  },
  en: {
    empty: "Choose an HTML file or paste your code.", tooLong: "The source exceeds 250,000 characters.",
    characters: "The source contains invalid UTF-8 characters.", binary: "The source contains non-text data.",
    missingHtml: "The source must contain at least one HTML element.",
    extension: "Choose a file with the .html or .htm extension.", fileName: "The file name is too long or contains unsupported characters.",
    fileSize: "The file exceeds 1 MB.", encoding: "Save your HTML file as valid UTF-8.",
    read: "Couldn't read the file. Choose it again.", oneFile: "Choose one file per scan.",
    title: "Scan source", hint: "Choose a UTF-8 HTML or HTM file up to 1 MB and 250,000 characters.",
    paste: "Paste HTML", sampleAction: "Load sample", drop: "Drop a file here or choose it from your device",
    replace: "Replace file", upload: "Choose HTML file", input: "HTML file", reading: "Reading",
    cancel: "Cancel file reading", code: "HTML code", sample: "Basira sample", pasted: "Pasted HTML",
    remove: "Remove file", clear: "Clear source",
    metadata: (bytes, lines) => `${bytes.toLocaleString("en")} bytes · ${lines.toLocaleString("en")} lines`,
  },
};

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

function sourceIssue(text) {
  if (!text.trim()) return "empty";
  if (text.length > MAX_CHARACTERS) {
    let characters = 0;
    for (const character of text) {
      characters++;
      if (characters > MAX_CHARACTERS) return "tooLong";
    }
  }
  if (/[\uD800-\uDFFF]/u.test(text))
    return "characters";
  if (/[\u0000-\u0008\u000B\u000E-\u001F]/.test(text))
    return "binary";
  if (!text.includes(">") || !/<[A-Za-z][^<>\s/]*(?:[\s/>])/.test(text))
    return "missingHtml";
  return "";
}

export function sourceError(text, lang = "ar") {
  return sourceCopy[lang][sourceIssue(text)] || "";
}

export function SourcePicker({ source, setSource, disabled, onBusyChange, lang = "ar" }) {
  const t = sourceCopy[lang];
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
  const pasteError = source.kind === "paste" && source.text ? sourceError(source.text, lang) : "";

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
      setError("extension");
      return;
    }
    if (file.name.length > 255 || invalidName.test(file.name)) {
      setError("fileName");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("fileSize");
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
        setError("encoding");
        return;
      }
      const issue = sourceIssue(text);
      if (issue) {
        setError(issue);
        return;
      }
      setSource({ text, kind: "file", name: file.name });
    };
    pending.onerror = () => {
      if (reader.current !== pending) return;
      finish();
      setError("read");
    };
    pending.readAsArrayBuffer(file);
  }

  function filesDragged(event) {
    return event.dataTransfer.types.includes("Files");
  }

  return (
    <section className="basira-source" aria-labelledby={id + "-title"}>
      <div className="basira-source-heading">
        <div>
          <h2 id={id + "-title"}>{t.title}</h2>
          <p id={id + "-hint"}>{t.hint}</p>
        </div>
        <div className="basira-source-alternatives">
          {source.kind !== "paste" && (
            <button className="subtle" disabled={disabled} onClick={openPaste}>
              <ClipboardPaste size={15} aria-hidden="true" /> {t.paste}
            </button>
          )}
          {source.kind !== "sample" && (
            <button className="subtle" disabled={disabled} onClick={() => changeSource(sampleSource)}>
              <FlaskConical size={15} aria-hidden="true" /> {t.sampleAction}
            </button>
          )}
        </div>
      </div>

      <div
        className={"basira-source-drop" + (dragging ? " dragging" : "")}
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
          else if (files.length > 1) setError("oneFile");
        }}
      >
        <Upload size={20} aria-hidden="true" />
        <p>{t.drop}</p>
        <button
          className="btn"
          disabled={disabled}
          aria-describedby={id + "-hint"}
          onClick={() => input.current.click()}
        >
          {source.kind === "file" ? t.replace : t.upload}
        </button>
        <input
          ref={input}
          type="file"
          hidden
          disabled={disabled}
          accept=".html,.htm,text/html"
          aria-label={t.input}
          onChange={(event) => {
            const [file] = event.target.files;
            event.target.value = "";
            loadFile(file);
          }}
        />
      </div>

      {loadingName && (
        <div className="basira-source-reading">
          <p role="status"><LoaderCircle className="spin" size={15} aria-hidden="true" /> {t.reading} <bdi>{loadingName}</bdi></p>
          <button className="subtle" onClick={cancelRead}>{t.cancel}</button>
        </div>
      )}
      {error && <p className="error" role="alert">{t[error]}</p>}
      {source.kind === "paste" && (
        <div className="basira-source-editor">
          <label htmlFor={id + "-html"}>{t.code}</label>
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
        <div className="basira-source-current">
          <FileCode2 size={20} aria-hidden="true" />
          <div>
            <strong><bdi>{source.name || (source.kind === "sample" ? t.sample : t.pasted)}</bdi></strong>
            <small>{t.metadata(bytes, lines)} · <bdi>UTF-8</bdi></small>
          </div>
          <button className="subtle" disabled={disabled} onClick={() => changeSource(emptySource)}>
            <X size={15} aria-hidden="true" /> {source.kind === "file" ? t.remove : t.clear}
          </button>
        </div>
      )}
    </section>
  );
}
