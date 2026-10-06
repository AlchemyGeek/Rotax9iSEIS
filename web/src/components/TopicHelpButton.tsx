import { useEffect, useRef, useState } from "react";
import type { TopicHelp } from "../types/contract";

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

  if (!help || !help.applies) return null;

  return (
    <span ref={ref} style={{ position: "relative", display: "inline-flex", marginLeft: 4 }}>
      <button
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
      {open && (
        <div
          role="dialog"
          aria-label={`About: ${help.title}`}
          onClick={(e) => e.stopPropagation()}
          style={{
            position: "absolute", top: "130%", left: 0, zIndex: 50, width: 300,
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
        </div>
      )}
    </span>
  );
}
