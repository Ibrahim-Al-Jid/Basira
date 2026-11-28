import React, { useEffect, useId, useRef, useState } from "react";

// One small dropdown used for the account menu and the three-dots menus.
// Items are links (href) or buttons (onSelect). Escape and a click outside close it.
export function Menu({ label, trigger, items, align = "end", className = "", children, onOpenChange }) {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  const button = useRef(null);
  const id = useId();

  function toggle(next) {
    setOpen(next);
    onOpenChange?.(next);
  }
  useEffect(() => {
    if (!open) return undefined;
    const away = (event) => { if (!root.current?.contains(event.target)) setOpen(false); };
    document.addEventListener("pointerdown", away);
    return () => document.removeEventListener("pointerdown", away);
  }, [open]);
  useEffect(() => {
    if (open) root.current?.querySelector('[role^="menuitem"]')?.focus();
  }, [open]);

  function keys(event) {
    if (!open) return;
    if (event.key === "Escape") {
      event.stopPropagation();
      toggle(false);
      button.current?.focus();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const nodes = [...root.current.querySelectorAll('[role^="menuitem"]')];
      const at = nodes.indexOf(document.activeElement);
      const step = event.key === "ArrowDown" ? 1 : -1;
      nodes[(at + step + nodes.length) % nodes.length]?.focus();
    } else if (event.key === "Tab") toggle(false);
  }

  return <div className={"menu " + className} ref={root} onKeyDown={keys}>
    <button ref={button} type="button" className="menu-trigger" aria-label={label} title={label}
      aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined} onClick={() => toggle(!open)}>
      {trigger}
    </button>
    {open && <div className="menu-list" id={id} role="menu" aria-label={label} data-align={align}>
      {children}
      {items.map((item, index) => {
        if (item.separator) return <hr key={index} role="separator" />;
        const content = <>{item.icon}<span>{item.label}</span>{item.hint && <small>{item.hint}</small>}</>;
        const close = () => toggle(false);
        return item.href
          ? <a key={index} role="menuitem" tabIndex={-1} href={item.href} className={item.danger ? "is-danger" : undefined}
            onClick={(event) => { close(); item.onSelect?.(event); }}>{content}</a>
          : <button key={index} type="button" role="menuitem" tabIndex={-1} disabled={item.disabled} className={item.danger ? "is-danger" : undefined}
            onClick={(event) => { close(); item.onSelect?.(event); }}>{content}</button>;
      })}
    </div>}
  </div>;
}
