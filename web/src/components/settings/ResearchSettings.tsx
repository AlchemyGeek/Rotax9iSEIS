import { useEffect, useState } from "react";
import { getEngineClient } from "../../lib/engineClient";
import type { WorkspaceSettings } from "../../types/contract";

const client = getEngineClient();

export type Sensitivity = "quiet" | "normal" | "curious";

// Spec 16 §6 (S8): the three positions and what each means. N of M recent
// slices for a recurring pattern; the shift threshold as a multiple of
// Trends' outlier threshold (Spec 12). The engine owns the numbers
// (investigations/inbox.py SENSITIVITY); this is their description.
export const SENSITIVITY: { id: Sensitivity; label: string; n: number; m: number; factor: number; what: string }[] = [
  { id: "quiet", label: "Quiet", n: 8, m: 10, factor: 2.0, what: "only what is there nearly every time" },
  { id: "normal", label: "Normal", n: 6, m: 10, factor: 1.5, what: "the default" },
  { id: "curious", label: "Curious", n: 4, m: 10, factor: 1.0, what: "more candidates, more of them nothing" },
];

export function sensitivityMeaning(id: string | undefined | null): string {
  const s = SENSITIVITY.find((x) => x.id === id) ?? SENSITIVITY[1];
  return `${s.label}: a pattern in ${s.n} of the last ${s.m} slices; a shift beyond ${s.factor.toFixed(1)} × Trends' outlier threshold`;
}

// Settings → Research (Spec 16 §6, D5): the inbox's sensitivity, per
// workspace. Only the pilot changes it; an investigation may suggest a
// change in its notebook. Both hosts (the inbox runs on the website too).
export function ResearchSettings() {
  const [settings, setSettings] = useState<WorkspaceSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    client.getWorkspaceSettings().then(setSettings, (e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const current = (settings?.research_sensitivity ?? "normal") as Sensitivity;

  async function choose(id: Sensitivity) {
    if (!settings || id === current) return;
    setError(null);
    try {
      const next = await client.saveWorkspaceSettings({ ...settings, research_sensitivity: id });
      setSettings({ ...next, research_sensitivity: next.research_sensitivity ?? "normal" });
      setSaved(`Saved. The inbox scans again with ${SENSITIVITY.find((s) => s.id === id)!.label.toLowerCase()} sensitivity the next time Research opens.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div style={{ background: "var(--panel)", borderRadius: 12, padding: "16px 18px" }} data-testid="research-settings">
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6 }}>Inbox sensitivity</div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 12, maxWidth: 720 }}>
        After each Sync, EIS looks across this workspace's recent flights for something worth a question — a pattern that keeps
        coming back, a measurement that has moved, slices that group apart — and puts it in the inbox on Research. It never
        says what it means; that is the investigation's (yours, or Claude's).
      </div>
      {error && <div style={{ fontSize: 12, color: "var(--severity-warning)", marginBottom: 8 }}>{error}</div>}
      <div role="radiogroup" aria-label="Inbox sensitivity" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {SENSITIVITY.map((s) => (
          <label key={s.id} style={{ display: "flex", gap: 10, alignItems: "baseline", fontSize: 12, cursor: settings ? "pointer" : "default" }}>
            <input type="radio" name="sensitivity" value={s.id} checked={current === s.id} disabled={!settings}
              onChange={() => void choose(s.id)} data-testid={`sensitivity-${s.id}`} />
            <span style={{ fontWeight: 600, width: 64 }}>{s.label}</span>
            <span style={{ color: "var(--text-secondary)" }}>
              a recurring pattern in <span className="mono">{s.n} of {s.m}</span> recent slices; a shift beyond{" "}
              <span className="mono">{s.factor.toFixed(1)} ×</span> Trends' outlier threshold — {s.what}
            </span>
          </label>
        ))}
      </div>
      {saved && <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 10 }} data-testid="sensitivity-saved">{saved}</div>}
    </div>
  );
}
