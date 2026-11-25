import type React from "react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { assignChannelColors } from "../../lib/channels";
import { channelShort, channelTitle } from "../../lib/notebookCard";

// Spec 03 v0.34 §5.10 — the small parts Research home and the notebook page
// share: one status vocabulary, the ⋯ / Actions menu, channel tags in the
// Flight view's colours, and the page's help popover.

// ── Status: one set of words across questions, candidates and notebooks ──

export type StatusWord = "new" | "investigating" | "watch" | "acted" | "nothing here" | "open" | "finished" | "reopened";

const STATUS_COLOR: Record<StatusWord, string> = {
  new: "var(--brand-tint)",
  investigating: "var(--ok)",
  open: "var(--ok)",
  reopened: "var(--ok)",
  watch: "var(--severity-watch)",
  acted: "var(--success)",
  "nothing here": "var(--text-tertiary)",
  finished: "var(--text-secondary)",
};

const STATUS_HINT: Record<StatusWord, string> = {
  new: "New: not looked at yet",
  investigating: "Investigating: a notebook took it up",
  open: "Open: the notebook is being written",
  reopened: "Reopened: a follow-up is adding to a finished notebook",
  watch: "Watch: kept in view",
  acted: "Acted: something was done about it",
  "nothing here": "Nothing here: looked at, nothing to follow",
  finished: "Finished",
};

/** An inbox status ("nothing-here") or a notebook status, as the one word set. */
export function statusWord(s: string | null | undefined): StatusWord {
  const w = String(s ?? "").replace("-", " ").toLowerCase();
  return (w in STATUS_COLOR ? w : "open") as StatusWord;
}

export function statusColor(s: string | null | undefined): string {
  return STATUS_COLOR[statusWord(s)];
}

/** A coloured dot and the lower-case word. `color` overrides (a finished notebook takes its resolution's). */
export function StatusMark({ status, color, title, testid }: { status: string | null | undefined; color?: string; title?: string; testid?: string }) {
  const w = statusWord(status);
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--text-secondary)", whiteSpace: "nowrap" }}
      title={title ?? STATUS_HINT[w]} data-testid={testid ?? "status-mark"} data-status={w}>
      <span aria-hidden style={{ width: 7, height: 7, borderRadius: "50%", background: color ?? STATUS_COLOR[w], flexShrink: 0 }} />
      {w}
    </span>
  );
}

// ── Channel tags ──────────────────────────────────────────────────────────

export function ChannelTags({ channels, max = 6 }: { channels: string[]; max?: number }) {
  if (!channels.length) return null;
  const colors = assignChannelColors(channels, {});
  const shown = channels.slice(0, max);
  const more = channels.length - shown.length;
  return (
    <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 4 }} data-testid="channel-tags">
      {shown.map((c) => (
        <span key={c} title={channelTitle(c)} data-channel={c} className="mono"
          style={{ fontSize: 10, lineHeight: "15px", padding: "0 5px", borderRadius: 4, color: colors[c], border: `1px solid ${colors[c]}`,
            background: `color-mix(in srgb, ${colors[c]} 12%, transparent)`, whiteSpace: "nowrap" }}>
          {channelShort(c)}
        </span>
      ))}
      {more > 0 && <span style={{ fontSize: 10, color: "var(--text-tertiary)" }} title={channels.slice(max).map(channelTitle).join(", ")}>+{more}</span>}
    </span>
  );
}

// ── A popover anchored to a button (fixed, so no panel clips it) ──────────

function usePopover(width: number) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      const t = e.target as Node;
      if (!anchor.current?.contains(t) && !pop.current?.contains(t)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") { setOpen(false); anchor.current?.focus(); }
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => { document.removeEventListener("mousedown", onDoc); document.removeEventListener("keydown", onKey); };
  }, [open]);

  useLayoutEffect(() => {
    if (!open || !anchor.current) { setPos(null); return; }
    function place() {
      const r = anchor.current!.getBoundingClientRect();
      const h = pop.current?.offsetHeight || 120;
      const below = window.innerHeight - r.bottom >= h + 8 || r.top < h + 8;
      const left = Math.min(Math.max(r.right - width, 8), Math.max(8, window.innerWidth - width - 8));
      setPos({ top: Math.max(8, below ? r.bottom + 4 : r.top - 4 - h), left });
    }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => { window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open, width]);

  return { open, setOpen, anchor, pop, pos };
}

const POP: React.CSSProperties = {
  position: "fixed", zIndex: 50, background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8,
  boxShadow: "0 6px 24px rgba(0,0,0,0.25)", padding: 4, display: "flex", flexDirection: "column",
};

export interface MenuItem {
  label: string;
  onSelect: () => void;
  testid?: string;
  hint?: string;
  disabled?: boolean;
  danger?: boolean;
}

/** `⋯` (or a labelled button, e.g. *Actions*) opening a menu of the item's other actions. */
export function ActionMenu({ items, label, title = "More actions", testid = "item-menu", buttonStyle }: {
  items: MenuItem[]; label?: string; title?: string; testid?: string; buttonStyle?: React.CSSProperties;
}) {
  const p = usePopover(220);
  const shown = items.filter(Boolean);
  if (!shown.length) return null;
  return (
    <>
      <button ref={p.anchor} type="button" aria-haspopup="menu" aria-expanded={p.open} aria-label={label ? undefined : title} title={title}
        data-testid={testid}
        onClick={(e) => { e.preventDefault(); e.stopPropagation(); p.setOpen((o) => !o); }}
        style={buttonStyle ?? { background: "none", border: "1px solid transparent", borderRadius: 6, padding: "0 6px", fontSize: 15, lineHeight: "20px",
          color: "var(--text-secondary)", cursor: "pointer" }}>
        {label ?? "⋯"}
      </button>
      {p.open && createPortal(
        <div ref={p.pop} role="menu" style={{ ...POP, width: 220, top: p.pos?.top ?? -9999, left: p.pos?.left ?? -9999 }} data-testid={`${testid}-list`}
          onClick={(e) => e.stopPropagation()}>
          {shown.map((it) => (
            <button key={it.label} type="button" role="menuitem" disabled={it.disabled} title={it.hint} data-testid={it.testid}
              onClick={() => { p.setOpen(false); it.onSelect(); }}
              style={{ textAlign: "left", background: "none", border: "none", borderRadius: 5, padding: "6px 10px", fontSize: 12,
                color: it.danger ? "var(--severity-warning)" : "var(--text-primary)", cursor: it.disabled ? "default" : "pointer", opacity: it.disabled ? 0.5 : 1 }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "var(--panel-control)"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "none"; }}>
              {it.label}
            </button>
          ))}
        </div>,
        document.body)}
    </>
  );
}

/** The page's `?`: what used to be said on the page, now on request. */
export function PageHelp({ children, testid = "page-help" }: { children: React.ReactNode; testid?: string }) {
  const p = usePopover(320);
  return (
    <>
      <button ref={p.anchor} type="button" aria-label="About this page" aria-expanded={p.open} data-testid={testid}
        onClick={() => p.setOpen((o) => !o)}
        style={{ width: 20, height: 20, borderRadius: "50%", border: "1px solid var(--border)", background: "var(--panel-control)",
          color: p.open ? "var(--brand-tint)" : "var(--text-secondary)", fontSize: 11, fontWeight: 700, cursor: "pointer", padding: 0, lineHeight: "18px" }}>
        ?
      </button>
      {p.open && createPortal(
        <div ref={p.pop} role="dialog" aria-label="About this page" data-testid={`${testid}-body`}
          style={{ ...POP, width: 320, padding: "10px 12px", fontSize: 12, lineHeight: 1.5, color: "var(--text-secondary)", top: p.pos?.top ?? -9999, left: p.pos?.left ?? -9999 }}>
          {children}
        </div>,
        document.body)}
    </>
  );
}

/** "Nov 18" (this year) or "Nov 18, 2025" — the card's *updated*. */
export function shortDate(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return String(iso);
  return d.toLocaleDateString(undefined, d.getFullYear() === now.getFullYear()
    ? { month: "short", day: "numeric" } : { month: "short", day: "numeric", year: "numeric" });
}
