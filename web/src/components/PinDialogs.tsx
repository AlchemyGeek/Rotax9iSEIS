import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { UnpinPreview } from "../types/contract";

// Spec 12 §5.7.1 items 2 and 5 (wording fixed v0.6, Session E) — the
// pin control opens a confirmation, not an immediate action; the unpin
// control shows the engine's own preview of what unpinning would do.
// Session B shipped the pin/unpin actions themselves with neither;
// Session D added this state; Session E aligns every word with v0.6's
// "baseline", not "reference", framing (D2 amended).

// Spec 12 §5.7.1 item 2 (v0.6): "say, under 10" — the comfort
// threshold below which the confirmation adds a caution. Decision
// (Session E, see report): exactly `n_min`/MIN_FLIGHTS_FOR_CONFIDENCE
// (10), the same number the rest of the system already uses for "not
// enough flights to be confident" — not a second, UI-only constant.
export const SMALL_BASELINE_THRESHOLD = 10;

const SHELL_STYLE: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)",
  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
};
const CARD_STYLE: React.CSSProperties = {
  width: 380, background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 12,
  padding: 20, boxShadow: "0 8px 32px rgba(0,0,0,0.35)",
};
const BUTTON_ROW: React.CSSProperties = { display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 };
const CANCEL_BUTTON: React.CSSProperties = {
  fontSize: 12, padding: "6px 14px", borderRadius: 999, border: "1px solid var(--border)",
  background: "transparent", color: "var(--text-secondary)", cursor: "pointer",
};
const CONFIRM_BUTTON: React.CSSProperties = {
  fontSize: 12, padding: "6px 14px", borderRadius: 999, border: "none",
  background: "var(--accent)", color: "#0f1214", fontWeight: 600, cursor: "pointer",
};

function DialogShell({ title, children, onCancel }: { title: string; children: React.ReactNode; onCancel: () => void }) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return createPortal(
    <div style={SHELL_STYLE} onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <div role="dialog" aria-label={title} style={CARD_STYLE}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10 }}>{title}</div>
        {children}
      </div>
    </div>,
    document.body,
  );
}

// §5.7/§5.7.1 item 2 (v0.9, Session G — R10.1): a resolved selection,
// either the flights currently in view (zoomed) or the recent window —
// TrendsPanelStrip computes both and hands them here; this dialog just
// picks between them and reports back whichever was chosen.
export interface Selection {
  flightIds: string[];
  n: number;
  hours: number;
  dateFrom: string | null;
  dateTo: string | null;
}

function dateSpanOf(s: Selection): string | null {
  if (!s.dateFrom || !s.dateTo) return null;
  return s.dateFrom === s.dateTo ? s.dateFrom : `${s.dateFrom} – ${s.dateTo}`;
}

// §5.7.1 item 2's own quoted sentence, filled in — "the same text is
// the help entry, written once": this is that one place; the pin
// control has no separate help popover, since the confirmation already
// is the full explanation. "in view" (v0.9) — the flights framed by
// the strip's current zoom, not necessarily the recent window anymore.
export function pinExplanation(n: number, hours: number, dateSpan: string | null): string {
  const dates = dateSpan ? `, ${dateSpan}` : "";
  return `The ${n} flight${n === 1 ? "" : "s"} in view (${hours.toFixed(1)} h${dates}) become this `
    + "metric's reference and stay fixed. Flights outside this span are no longer used for this metric. New "
    + "flights are compared against these flights until you unpin.";
}

interface PinConfirmProps {
  metricLabel: string;
  zoomSelection: Selection;
  windowSelection: Selection;
  // Whether `zoomSelection` already covers every eligible flight (the
  // strip is unzoomed) — §5.7's full-history notice.
  isFullHistory: boolean;
  onConfirm: (selection: Selection, label?: string) => void;
  onCancel: () => void;
}

export function PinConfirmDialog({ metricLabel, zoomSelection, windowSelection, isFullHistory, onConfirm, onCancel }: PinConfirmProps) {
  const [label, setLabel] = useState("");
  // §5.7: "the confirmation offers Use the recent window instead" —
  // zoomed-in-view is the default selection; switching is a one-click
  // toggle in both directions (the spec names only zoom -> window, but
  // window -> zoom is the same affordance and costs nothing extra).
  const [mode, setMode] = useState<"zoom" | "window">("zoom");
  const selection = mode === "zoom" ? zoomSelection : windowSelection;

  return (
    <DialogShell title={`Pin reference: ${metricLabel}`} onCancel={onCancel}>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>
        {mode === "zoom" && isFullHistory ? (
          <p style={{ margin: "0 0 8px" }}>
            All {zoomSelection.n} flights are selected — zoom to the flights you want first, or use the recent window.
          </p>
        ) : (
          <p style={{ margin: "0 0 8px" }}>{pinExplanation(selection.n, selection.hours, dateSpanOf(selection))}</p>
        )}
        {selection.n < SMALL_BASELINE_THRESHOLD && (
          <p style={{ margin: "0 0 8px", color: "var(--severity-warning)" }}>
            A reference of {selection.n} flight{selection.n === 1 ? "" : "s"} makes comparisons noisier than your full history.
          </p>
        )}
        <p style={{ margin: "0 0 8px" }}>Useful after maintenance or a change you want to measure from.</p>
      </div>
      <button
        type="button"
        onClick={() => setMode((m) => (m === "zoom" ? "window" : "zoom"))}
        style={{ ...CANCEL_BUTTON, fontSize: 11, padding: "4px 10px" }}
      >
        {mode === "zoom" ? "Use the recent window instead" : "Use the flights in view instead"}
      </button>
      <label style={{ display: "block", fontSize: 11, color: "var(--text-tertiary)", marginTop: 10 }}>
        Label (optional)
        <input
          type="text" value={label} onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. after oil change"
          style={{
            display: "block", width: "100%", marginTop: 4, fontSize: 12, padding: "6px 8px",
            borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel-control)", color: "var(--text-primary)",
          }}
        />
      </label>
      <div style={BUTTON_ROW}>
        <button style={CANCEL_BUTTON} onClick={onCancel}>Cancel</button>
        <button style={CONFIRM_BUTTON} onClick={() => onConfirm(selection, label.trim() || undefined)}>Pin reference</button>
      </div>
    </DialogShell>
  );
}

interface UnpinConfirmProps {
  metricLabel: string;
  preview: UnpinPreview | null; // null while loading
  onConfirm: () => void;
  onCancel: () => void;
}

export function UnpinConfirmDialog({ metricLabel, preview, onConfirm, onCancel }: UnpinConfirmProps) {
  // §5.7.1 item 5's own two phrasings, plus the symmetric third case
  // (unpinning reveals a shift the pin had been hiding) the spec's
  // prose doesn't name but the preview can still answer.
  let line = "Checking…";
  if (preview) {
    line = !preview.changes
      ? "No change to the summary."
      : preview.would_be_in_summary
        ? "This metric will newly appear in the change summary."
        : "This metric will no longer appear in the change summary.";
  }
  return (
    <DialogShell title={`Unpin reference: ${metricLabel}`} onCancel={onCancel}>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>
        <p style={{ margin: "0 0 8px" }}>The reference will again include all earlier flights and grow as you fly. Shift-history events recorded while pinned are unaffected.</p>
        <p style={{ margin: "0 0 8px", fontWeight: 600, color: "var(--text-primary)" }}>{line}</p>
      </div>
      <div style={BUTTON_ROW}>
        <button style={CANCEL_BUTTON} onClick={onCancel}>Cancel</button>
        <button style={CONFIRM_BUTTON} onClick={onConfirm} disabled={!preview}>Unpin reference</button>
      </div>
    </DialogShell>
  );
}
