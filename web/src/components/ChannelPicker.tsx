import { CHANNEL_REGISTRY } from "../lib/channels";

// The channel picker and the chart legend are the same component
// (Spec 05 v0.2 §4) — active channels render as filled chips with a
// remove affordance, inactive ones as dashed "+ Label" add affordances.
export function ChannelPicker({ active, onToggle }: { active: string[]; onToggle: (id: string) => void }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 14 }}>
      {CHANNEL_REGISTRY.map((c) => {
        const isActive = active.includes(c.id);
        return (
          <span
            key={c.id}
            onClick={() => onToggle(c.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              padding: "5px 11px",
              borderRadius: 14,
              fontSize: 11,
              fontWeight: isActive ? 600 : 400,
              cursor: "pointer",
              background: isActive ? `${c.color}26` : "transparent",
              border: isActive ? `1px solid ${c.color}` : "1px dashed var(--border)",
              color: isActive ? c.color : "var(--text-secondary)",
            }}
          >
            {isActive && <span style={{ width: 7, height: 7, borderRadius: "50%", background: c.color }} />}
            {isActive ? `${c.label} ✕` : `+ ${c.label}`}
          </span>
        );
      })}
    </div>
  );
}
