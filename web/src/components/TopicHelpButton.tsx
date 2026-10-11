import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { TopicHelp } from "../types/contract";

const POPOVER_WIDTH = 300;
const POPOVER_MARGIN = 8;

// Spec 02 §6.6: the engine returns canonical units; converting to the
// pilot's chosen system is a display concern, done here. Only °F and
// L/h actually have a metric/imperial pair among today's help
// placeholders — everything else (rpm, %, s) is the same in both.
function formatHelpValue(value: number | string, unit: string | null, units: "imperial" | "metric"): string {
  if (typeof value !== "number" || unit == null) return String(value);
  if (unit === "°F" && units === "metric") {
    const c = Math.round(((value - 32) * 5) / 9 * 10) / 10;
    return `${c}°C`;
  }
  if (unit === "L/h" && units === "imperial") {
    const gph = Math.round(value * 0.264172 * 10) / 10;
    return `${gph} gal/h`;
  }
  const noSpace = unit === "°F" || unit === "°C" || unit === "%";
  return noSpace ? `${value}${unit}` : `${value} ${unit}`;
}

export function renderHelpText(help: TopicHelp, units: "imperial" | "metric"): string {
  let text = help.template;
  for (const [placeholder, v] of Object.entries(help.values)) {
    text = text.split(placeholder).join(formatHelpValue(v.value, v.unit, units));
  }
  return text;
}

export function UnverifiedTag({ engine }: { engine: string }) {
  return (
    <span style={{ fontSize: 10, color: "var(--text-tertiary)", fontWeight: 500 }}>
      Not yet validated on the {engine}
    </span>
  );
}

export function TopicHelpButton({
  help, engine, units,
}: {
  help: TopicHelp | undefined;
  engine: string;
  units: "imperial" | "metric";
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  // Fixed to the viewport (not the button's scrollable ancestor — the
  // Analysis grid scrolls its own panel), with a placement computed from
  // the button's own position, so the popover is always fully visible
  // without having to scroll the page or the panel behind it.
  const [pos, setPos] = useState<{ top: number; left: number; placement: "above" | "below" } | null>(null);

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
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
      const popoverHeight = popoverRef.current?.offsetHeight || 220;
      const roomBelow = window.innerHeight - rect.bottom;
      const roomAbove = rect.top;
      // Prefer below; flip above only when below is tighter than above —
      // whichever side has more room, not a fixed threshold, so this
      // still picks the better side on a short viewport where neither
      // fits fully.
      const placement: "above" | "below" = roomBelow < popoverHeight + POPOVER_MARGIN && roomAbove > roomBelow
        ? "above" : "below";
      let top = placement === "below" ? rect.bottom + 4 : rect.top - 4 - popoverHeight;
      // Hard clamp: whatever the heuristic above decided, never let the
      // popover's top or bottom edge land outside the viewport — this is
      // the actual guarantee, the placement choice above is just about
      // picking the least-bad side first.
      top = Math.max(POPOVER_MARGIN, Math.min(top, window.innerHeight - popoverHeight - POPOVER_MARGIN));
      const left = Math.min(
        Math.max(rect.left, POPOVER_MARGIN),
        window.innerWidth - POPOVER_WIDTH - POPOVER_MARGIN,
      );
      setPos({ top, left, placement });
    }
    reposition();
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-measure once content is in the DOM
  }, [open, help?.text]);

  if (!help || !help.applies) return null;

  return (
    <span ref={ref} style={{ position: "relative", display: "inline-flex", marginLeft: 4 }}>
      <button
        ref={buttonRef}
        type="button"
        aria-label={`About: ${help.title}`}
        aria-expanded={open}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            setOpen(true);
          }
        }}
        style={{
          width: 15, height: 15, borderRadius: "50%", border: "1px solid var(--border)",
          background: "transparent", color: "var(--text-tertiary)", fontSize: 10, lineHeight: 1,
          cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center",
          padding: 0, flexShrink: 0,
        }}
      >
        ?
      </button>
      {open &&
        createPortal(
          <div
            ref={popoverRef}
            role="dialog"
            aria-label={`About: ${help.title}`}
            onClick={(e) => e.stopPropagation()}
            style={{
              position: "fixed",
              top: pos?.top ?? -9999,
              left: pos?.left ?? -9999,
              visibility: pos ? "visible" : "hidden",
              zIndex: 1000, width: POPOVER_WIDTH, maxHeight: "70vh", overflowY: "auto",
              background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8,
              padding: 12, boxShadow: "0 4px 16px rgba(0,0,0,0.25)",
            }}
          >
            <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, color: "var(--text-primary)" }}>
              {help.title}
            </div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>
              {renderHelpText(help, units)}
            </div>
            {!help.validated && (
              <div style={{ marginTop: 8 }}>
                <UnverifiedTag engine={engine} />
              </div>
            )}
          </div>,
          document.body,
        )}
    </span>
  );
}
