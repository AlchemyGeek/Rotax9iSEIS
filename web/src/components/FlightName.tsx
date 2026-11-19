import { useState } from "react";
import { getEngineClient } from "../lib/engineClient";

const client = getEngineClient();

// Spec 16 §4.4 / Spec 03 §5.1 (Session F): the pilot's name for a flight,
// edited in place in the Flights table (flight_set_name; empty clears).
// Searchable by Find a flight and by Claude's flights_find.
export function FlightName({ flightId, name, editable, onSaved }: {
  flightId: string;
  name: string | null | undefined;
  editable: boolean;
  onSaved: (name: string | null) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save() {
    const next = draft.trim();
    if (next === (name ?? "")) { setEditing(false); return; }
    setBusy(true);
    setError(null);
    try {
      const res = await client.flightSetName(flightId, next || null);
      onSaved(res.name ?? null);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (editing) {
    return (
      <span onClick={(e) => e.stopPropagation()} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        <input
          autoFocus value={draft} disabled={busy} maxLength={120} aria-label="Flight name" data-testid="flight-name-input"
          placeholder="e.g. Bellingham pattern work"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void save(); if (e.key === "Escape") { setDraft(name ?? ""); setEditing(false); } }}
          onBlur={() => void save()}
          style={{ fontSize: 11, padding: "2px 6px", borderRadius: 4, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text-primary)", width: 200 }}
        />
        {error && <span style={{ fontSize: 10, color: "var(--severity-warning)" }}>{error}</span>}
      </span>
    );
  }
  if (!editable) return name ? <div style={{ fontSize: 11, color: "var(--text-secondary)", fontFamily: "inherit" }}>{name}</div> : null;
  return (
    <div>
      <button
        type="button" data-testid="flight-name"
        onClick={(e) => { e.stopPropagation(); setDraft(name ?? ""); setEditing(true); }}
        title={name ? "Rename this flight" : "Name this flight (searchable)"}
        style={{ background: "none", border: "none", padding: 0, cursor: "text", fontSize: 11, color: name ? "var(--text-secondary)" : "var(--text-tertiary)", fontFamily: "var(--font-sans, inherit)" }}
      >
        {name || "+ name"}
      </button>
    </div>
  );
}
