import { useEffect, useState } from "react";
import { createPortal } from "react-dom";

// Spec 14 §7.1 — "A small dialog takes the reason (required)... This is
// the entry point most pilots will use" — shared between the Flights row
// toggle and any insight card's "Exclude this flight from reference →",
// so the two entry points produce one identical interaction (same
// component, not a parallel reimplementation). FleetSelection.excluded
// stores a single `reason` string (Spec 02 §6.3) — no separate "note"
// field exists, so this dialog keeps one free-text field rather than
// adding new storage for a second one the data model doesn't have.
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

export function ExcludeConfirmDialog({
  flightLabel, busy, onConfirm, onCancel,
}: {
  flightLabel: string;
  busy?: boolean;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState("");

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return createPortal(
    <div style={SHELL_STYLE} onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <div role="dialog" aria-label={`Exclude ${flightLabel} from reference`} style={CARD_STYLE}>
        <div style={{ fontSize: 14, fontWeight: 700, marginBottom: 10 }}>Exclude this flight from reference</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5, marginBottom: 10 }}>
          {flightLabel} stops shaping other flights&rsquo; reference. It is still analyzed and still shows its own
          insights — this only changes what other flights are compared against.
        </div>
        <label style={{ display: "block", fontSize: 11, color: "var(--text-tertiary)" }}>
          Reason (required)
          <input
            autoFocus
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && reason.trim() && onConfirm(reason.trim())}
            placeholder="e.g. engine ground-run, not representative"
            style={{
              display: "block", width: "100%", marginTop: 4, fontSize: 12, padding: "6px 8px",
              borderRadius: 6, border: "1px solid var(--border)", background: "var(--panel-control)", color: "var(--text-primary)",
            }}
          />
        </label>
        <div style={BUTTON_ROW}>
          <button style={CANCEL_BUTTON} onClick={onCancel}>Cancel</button>
          <button
            style={{ ...CONFIRM_BUTTON, opacity: reason.trim() && !busy ? 1 : 0.5, cursor: reason.trim() && !busy ? "pointer" : "default" }}
            disabled={!reason.trim() || busy}
            onClick={() => onConfirm(reason.trim())}
          >
            {busy ? "Excluding…" : "Exclude from reference"}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
