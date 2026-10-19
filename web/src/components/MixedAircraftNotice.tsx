import { useState } from "react";
import { getEngineClient } from "../lib/engineClient";
import { useAircraftSummary } from "../lib/aircraftSummary";
import { workspaceSettings as fixtureWorkspaceSettings } from "../lib/fixtures";
import type { WorkspaceSettings } from "../types/contract";

// Spec 02 v0.8 §5.6/§6.6, Spec 03 v0.14 §5.1: shown on the Flights tab
// and in the Trends header when admitted flights carry more than one
// distinct aircraft (after aliases). Never blocks anything — it's
// informational, with an action to record that two idents are the same
// aircraft (a G3X ident typo, a re-registration).
export function MixedAircraftNotice({ usingFixture }: { usingFixture: boolean }) {
  const [refreshKey, setRefreshKey] = useState(0);
  const summary = useAircraftSummary(usingFixture, refreshKey);
  const [grouping, setGrouping] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);

  if (!summary || summary.idents.length <= 1) return null;

  async function saveAliases(nextAliases: string[][]) {
    setSaving(true);
    try {
      const client = getEngineClient();
      const current = usingFixture ? fixtureWorkspaceSettings : await client.getWorkspaceSettings();
      const settings: WorkspaceSettings = { ...current, aircraft_aliases: nextAliases };
      if (!usingFixture) await client.saveWorkspaceSettings(settings);
      setRefreshKey((k) => k + 1);
    } finally {
      setSaving(false);
      setGrouping(false);
      setSelected(new Set());
    }
  }

  function confirmGroup() {
    if (selected.size < 2) return;
    const group = [...selected];
    const others = summary!.aliases.filter((g) => !g.some((id) => selected.has(id)));
    void saveAliases([...others, group]);
  }

  function ungroup(group: string[]) {
    void saveAliases(summary!.aliases.filter((g) => g !== group));
  }

  return (
    <div style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8, padding: "10px 14px", marginBottom: 12, fontSize: 12 }}>
      <div style={{ color: "var(--text-secondary)" }}>
        This workspace contains flights from {summary.idents.length} aircraft ({summary.idents.join(", ")}). Comparisons
        with your usual treat them as one aircraft. For per-aircraft results, use one workspace per aircraft.
      </div>
      {summary.aliases.length > 0 && (
        <div style={{ marginTop: 6, color: "var(--text-tertiary)" }}>
          Grouped as the same aircraft:{" "}
          {summary.aliases.map((group, i) => (
            <span key={i} style={{ marginRight: 10 }}>
              {group.join(" = ")}{" "}
              <button
                onClick={() => ungroup(group)}
                disabled={saving}
                style={{ fontSize: 11, border: "none", background: "transparent", color: "var(--link)", textDecoration: "underline", textDecorationColor: "var(--link-underline)", textUnderlineOffset: 2, cursor: "pointer", padding: 0 }}
              >
                ungroup
              </button>
            </span>
          ))}
        </div>
      )}
      {!grouping ? (
        <button
          onClick={() => setGrouping(true)}
          style={{ marginTop: 6, fontSize: 11, border: "1px solid var(--border)", background: "transparent", color: "var(--text-secondary)", borderRadius: 6, padding: "3px 8px", cursor: "pointer" }}
        >
          These are the same aircraft…
        </button>
      ) : (
        <div style={{ marginTop: 8 }}>
          <div style={{ color: "var(--text-tertiary)", marginBottom: 4 }}>Select two or more tail numbers that are the same aircraft:</div>
          {summary.raw_idents.map((ident) => (
            <label key={ident} style={{ display: "inline-flex", alignItems: "center", gap: 4, marginRight: 12 }}>
              <input
                type="checkbox"
                checked={selected.has(ident)}
                onChange={(e) => {
                  const next = new Set(selected);
                  if (e.target.checked) next.add(ident);
                  else next.delete(ident);
                  setSelected(next);
                }}
              />
              {ident}
            </label>
          ))}
          <div style={{ marginTop: 8 }}>
            <button
              onClick={confirmGroup}
              disabled={selected.size < 2 || saving}
              style={{ fontSize: 11, border: "1px solid var(--border)", background: "var(--brand)", color: "var(--on-brand)", borderRadius: 6, padding: "3px 8px", cursor: "pointer", marginRight: 6 }}
            >
              Confirm same aircraft
            </button>
            <button
              onClick={() => { setGrouping(false); setSelected(new Set()); }}
              style={{ fontSize: 11, border: "1px solid var(--border)", background: "transparent", color: "var(--text-secondary)", borderRadius: 6, padding: "3px 8px", cursor: "pointer" }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
