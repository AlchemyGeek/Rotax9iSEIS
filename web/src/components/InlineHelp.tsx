import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { INLINE_HELP, type InlineHelpId } from "../lib/inlineHelp";

const POPOVER_WIDTH = 260;
const POPOVER_MARGIN = 8;

// Spec 14 §7.4 — inline help, disclosed: an ⓘ that opens its one sentence
// on click (Escape or a click elsewhere closes it), never a paragraph in
// the layout. Text comes only from the INLINE_HELP registry. Same
// viewport-fixed popover as TopicHelpButton, so a scrolling panel never
// clips it.
export function InlineHelp({ id }: { id: InlineHelpId }) {
  const text = INLINE_HELP[id];
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      const target = e.target as Node;
      if (!ref.current?.contains(target) && !popoverRef.current?.contains(target)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) {
      setPos(null);
      return;
    }
    function reposition() {
      const btn = buttonRef.current;
      if (!btn) return;
      const rect = btn.getBoundingClientRect();
      const height = popoverRef.current?.offsetHeight || 80;
      const below = window.innerHeight - rect.bottom >= height + POPOVER_MARGIN || rect.top < height + POPOVER_MARGIN;
      const top = below ? rect.bottom + 4 : rect.top - 4 - height;
      const left = Math.min(Math.max(rect.left - 8, POPOVER_MARGIN), window.innerWidth - POPOVER_WIDTH - POPOVER_MARGIN);
      setPos({ top: Math.max(POPOVER_MARGIN, top), left });
    }
    reposition();
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [open]);

  return (
    <span ref={ref} style={{ display: "inline-flex", marginLeft: 5, verticalAlign: "baseline" }}>
      <button
        ref={buttonRef}
        type="button"
        aria-label="What is this?"
        aria-expanded={open}
        data-help-id={id}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        style={{
          background: "none", border: "none", padding: 0, fontSize: 11, lineHeight: 1,
          color: open ? "var(--accent)" : "var(--text-tertiary)", cursor: "pointer", fontWeight: 400,
        }}
      >
        ⓘ
      </button>
      {open &&
        createPortal(
          <div
            ref={popoverRef}
            role="tooltip"
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "fixed",
              top: pos?.top ?? -9999,
              left: pos?.left ?? -9999,
              visibility: pos ? "visible" : "hidden",
              zIndex: 1000, width: POPOVER_WIDTH,
              background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8,
              padding: "9px 11px", boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
              fontSize: 12, fontWeight: 400, color: "var(--text-secondary)", lineHeight: 1.5,
              textAlign: "left", whiteSpace: "normal", letterSpacing: "normal", textTransform: "none",
            }}
          >
            {text}
          </div>,
          document.body,
        )}
    </span>
  );
}
