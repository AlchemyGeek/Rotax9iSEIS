import type { InsightSeverity } from "../types/contract";

const SEVERITY_COLOR: Record<InsightSeverity, string> = {
  limit: "var(--severity-limit)",
  warning: "var(--severity-warning)",
  watch: "var(--severity-watch)",
  info: "var(--severity-info)",
};

const SEVERITY_TEXT_COLOR: Record<InsightSeverity, string> = {
  limit: "var(--severity-limit)",
  warning: "var(--severity-warning)",
  watch: "var(--severity-watch)",
  info: "var(--severity-info-text)",
};

// warning/limit render as a triangle, watch/info as a circle (Spec 03
// v0.3 §5.2) — severity isn't color-only.
const TRIANGLE_SEVERITIES = new Set<InsightSeverity>(["warning", "limit"]);

const SIZES = {
  md: { dot: 7, triW: 4, triH: 7, font: 10 },
  sm: { dot: 5, triW: 3, triH: 5, font: 9 },
};

// One lookup table for severity -> color/shape, reused everywhere
// severity appears (insight list, Analysis cards, chart markers, ECU
// table) — Spec 03 §6.1: "a pilot should learn the color meaning once."
export function SeverityBadge({ severity, size = "md" }: { severity: InsightSeverity; size?: "sm" | "md" }) {
  const s = SIZES[size];
  return (
    <div style={{ display: "flex", alignItems: "center", gap: size === "sm" ? 4 : 6 }}>
      {TRIANGLE_SEVERITIES.has(severity) ? (
        <span
          style={{
            display: "inline-block",
            width: 0,
            height: 0,
            borderLeft: `${s.triW}px solid transparent`,
            borderRight: `${s.triW}px solid transparent`,
            borderBottom: `${s.triH}px solid ${SEVERITY_COLOR[severity]}`,
            flexShrink: 0,
          }}
        />
      ) : (
        <div
          style={{
            width: s.dot,
            height: s.dot,
            borderRadius: "50%",
            background: SEVERITY_COLOR[severity],
            flexShrink: 0,
          }}
        />
      )}
      <span
        style={{
          fontSize: s.font,
          fontWeight: 700,
          letterSpacing: 0.5,
          color: SEVERITY_TEXT_COLOR[severity],
        }}
      >
        {severity.toUpperCase()}
      </span>
    </div>
  );
}
