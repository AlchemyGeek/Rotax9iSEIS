import type { Phase } from "../types/contract";

export interface ClippedSegment {
  phase: string;
  start_s: number;
  end_s: number;
  widthPct: number;
}

// Fixed, one hue per phase (Spec 03 v0.5 §5.2) — chosen to avoid any
// collision with the severity palette or the channel-picker colors, so
// nothing on the Flight view screen accidentally reads as a severity
// signal. UNKNOWN is the fallback for anything not in this list.
export const PHASE_ORDER = [
  "PRE_START", "ENGINE_START", "WARMUP", "TAXI", "TAKEOFF_ROLL", "CLIMB",
  "CRUISE", "DESCENT", "APPROACH", "LANDING_ROLL", "SHUTDOWN", "UNKNOWN",
] as const;

const PHASE_COLORS: Record<string, string> = {
  PRE_START: "#4B5563",
  ENGINE_START: "#7C6F57",
  WARMUP: "#8B7E6A",
  TAXI: "#5B7290",
  TAKEOFF_ROLL: "#6366F1",
  CLIMB: "#22C55E",
  CRUISE: "#0EA5E9",
  DESCENT: "#A855F7",
  APPROACH: "#EC4899",
  LANDING_ROLL: "#14B8A6",
  SHUTDOWN: "#374151",
  UNKNOWN: "#1F2937",
};

export function phaseColor(phase: string): string {
  return PHASE_COLORS[phase] ?? PHASE_COLORS.UNKNOWN;
}

// For the Flight view chart's background tint (Spec 03 v0.7 §5.2) — a
// low-opacity wash behind the data, not a solid fill. Canvas fillStyle
// accepts rgba() literals fine (unlike CSS custom properties, which
// silently fail on <canvas> — see theme/colors.ts), so a plain hex->rgba
// conversion is all this needs.
export function phaseColorAlpha(phase: string, alpha: number): string {
  const hex = phaseColor(phase).replace("#", "");
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

export function phaseLabel(phase: string): string {
  return phase.toLowerCase().replace(/_/g, " ");
}

// Shared by the phase band (clipped to the current zoom window) and the
// minimap (always clipped to the full flight) — Spec 03 v0.4 §6.1: "two
// views of the same phase data at two different scopes... implement from
// one shared phase-segment calculation," not two pieces of logic that
// happen to agree today. Segment durations/widths are recomputed against
// [windowStart, windowEnd], never a phase's own full extent — a phase
// entirely outside the window is dropped, one straddling the edge is
// truncated to what's actually visible.
export function clipPhasesToWindow(phases: Phase[], windowStart: number, windowEnd: number): ClippedSegment[] {
  const span = windowEnd - windowStart || 1;
  const segments: ClippedSegment[] = [];
  for (const p of phases) {
    const s = Math.max(p.start_s, windowStart);
    const e = Math.min(p.end_s, windowEnd);
    if (e <= s) continue;
    segments.push({ phase: p.phase, start_s: s, end_s: e, widthPct: ((e - s) / span) * 100 });
  }
  return segments;
}
