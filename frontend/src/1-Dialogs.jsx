import React, { useEffect, useRef } from "react";
import { X } from "lucide-react";

const dialogCopy = { ar: { close: "إغلاق" }, en: { close: "Close" } };

export function Modal({ title, children, close, wide = false, lang = "ar" }) {
  const ref = useRef(null);
  useEffect(() => {
    const d = ref.current;
    const opener = document.activeElement;
    d.showModal();
    // React autoFocus runs before showModal, so the dialog would focus its first control (Close).
    d.querySelector("[data-autofocus]")?.focus();
    return () => {
      d.close();
      if (opener && opener !== document.body && opener.isConnected) opener.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className={"modal " + (wide ? "wide" : "")}
      aria-label={title}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      onClick={(e) => {
        if (e.target === ref.current) close();
      }}
    >
      <div className="modal-body">
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="square" aria-label={dialogCopy[lang].close} onClick={close}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </dialog>
  );
}
