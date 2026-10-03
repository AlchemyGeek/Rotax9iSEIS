import type { ChartPreset } from "../types/contract";

export type ChartState = "preset" | "modified" | "insight";

interface Props {
  presets: ChartPreset[];
  chartState: ChartState;
  activePresetId: string | null;
  insightLabel?: string;
  previousLabel?: string;
  onSelectPreset: (id: string) => void;
  onRevert: () => void;
  onSaveAsPreset: () => void;
  onBack: () => void;
}

// The chart is always in exactly one of three states (Spec 07 §6.5) —
// this bar is what tells the pilot which one, and is the only place the
// state-specific actions (Revert, Save as preset…, Back) live.
export function PresetBar({ presets, chartState, activePresetId, insightLabel, previousLabel, onSelectPreset, onRevert, onSaveAsPreset, onBack }: Props) {
  if (chartState === "insight") {
    return (
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, fontSize: 12 }}>
        <span style={{ color: "var(--text-secondary)" }}>
          Showing: <strong style={{ color: "var(--text-primary)" }}>{insightLabel ?? "evidence"}</strong>
        </span>
        <a href="#" onClick={(e) => { e.preventDefault(); onBack(); }} style={{ color: "var(--accent)" }}>
          ← Back to {previousLabel ?? "previous view"}
        </a>
      </div>
    );
  }

  const activeLabel = presets.find((p) => p.id === activePresetId)?.label;

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10, flexWrap: "wrap" }}>
      <div style={{ display: "flex", gap: 6, overflowX: "auto" }}>
        {presets.map((p) => (
          <button
            key={p.id}
            onClick={() => onSelectPreset(p.id)}
            style={{
              flexShrink: 0, padding: "5px 11px", borderRadius: 14, fontSize: 11, fontWeight: 600, cursor: "pointer",
              background: p.id === activePresetId ? "rgba(79,195,176,0.15)" : "transparent",
              border: p.id === activePresetId ? "1px solid var(--accent)" : "1px solid var(--border)",
              color: p.id === activePresetId ? "var(--accent)" : "var(--text-secondary)",
            }}
          >
            {p.label}
          </button>
        ))}
      </div>
      {chartState === "modified" && (
        <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 11 }}>
          <span style={{ color: "var(--text-tertiary)" }}>{activeLabel ?? "Custom"} (modified)</span>
          <a href="#" onClick={(e) => { e.preventDefault(); onRevert(); }} style={{ color: "var(--accent)" }}>Revert</a>
          <a href="#" onClick={(e) => { e.preventDefault(); onSaveAsPreset(); }} style={{ color: "var(--accent)" }}>Save as preset…</a>
        </div>
      )}
    </div>
  );
}
