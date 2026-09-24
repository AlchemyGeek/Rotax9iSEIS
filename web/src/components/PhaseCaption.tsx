import type { Phase } from "../types/contract";
import { clipPhasesToWindow, phaseColor, phaseLabel, PHASE_ORDER } from "../lib/phases";

interface Props {
  phases: Phase[];
  windowStart: number;
  windowEnd: number;
  undifferentiatedNote?: string;
}

function captionText(segments: ReturnType<typeof clipPhasesToWindow>, undifferentiatedNote?: string): string {
  if (segments.length === 0) return "no phase data in view";
  if (segments.length === 1) {
    const seg = segments[0];
    const durS = Math.round(seg.end_s - seg.start_s);
    const name = undifferentiatedNote && seg.phase === "TAXI" ? undifferentiatedNote : phaseLabel(seg.phase);
    return `${name} (${durS}s)`;
  }
  return segments.map((seg) => `${phaseLabel(seg.phase)} (${Math.round(seg.end_s - seg.start_s)}s)`).join(" · ");
}

// Spec 03 v0.7 §5.2: the standalone colored phase band is gone — it was
// redundant with the minimap without adding real function of its own.
// What the band's color communicated now lives as a tint on the main
// chart's own background (ChannelTimeline); this component keeps only
// the two pieces of the old band that weren't the bar itself — the
// caption naming what's currently in view, and the persistent legend key
// (shown in full always, not trimmed to phases present in this flight,
// since it's meant to be learned once and reused across every flight).
export function PhaseCaption({ phases, windowStart, windowEnd, undifferentiatedNote }: Props) {
  const segments = clipPhasesToWindow(phases, windowStart, windowEnd);
  return (
    <div>
      <div style={{ fontSize: 11, color: "var(--text-secondary)", marginBottom: 10 }}>
        {captionText(segments, undifferentiatedNote)}
      </div>

      <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 14px", marginBottom: 14 }}>
        {PHASE_ORDER.map((phase) => (
          <span key={phase} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: "var(--text-secondary)" }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: phaseColor(phase), flexShrink: 0 }} />
            {phaseLabel(phase)}
          </span>
        ))}
      </div>
    </div>
  );
}
