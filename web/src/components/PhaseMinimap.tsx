import { useRef } from "react";
import type { Phase } from "../types/contract";
import { clipPhasesToWindow, phaseColor } from "../lib/phases";

interface Props {
  phases: Phase[];
  fullEnd: number;
  windowStart: number;
  windowEnd: number;
  onNavigate?: (start: number, end: number) => void;
}

// The full-flight phase overview (Spec 03 v0.7 §5.2/§6.1) — now the only
// navigational bar in Flight view. Its job is unchanged from before the
// merge: full-flight orientation, with the current zoom window outlined
// on it, and drag-to-navigate. Shares clipPhasesToWindow with the main
// chart's phase tint (ChannelTimeline) rather than each computing
// segments independently.
export function PhaseMinimap({ phases, fullEnd, windowStart, windowEnd, onNavigate }: Props) {
  const total = fullEnd || 1;
  const segments = clipPhasesToWindow(phases, 0, total);
  const left = Math.max(0, Math.min(100, (windowStart / total) * 100));
  const width = Math.max(((windowEnd - windowStart) / total) * 100, 0.6);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; startT: number } | null>(null);

  // A highlight drawn only on the current window is invisible at the
  // most common landing state — full flight, zero zoom — since it then
  // covers exactly 100% of the bar and there's nothing left to contrast
  // it against ("where we are" reads as "everywhere," i.e. nowhere in
  // particular). Dimming the portions *outside* the window instead means
  // the indicator is legible at any zoom level by construction: those
  // scrims have zero width at full flight (nothing dimmed, nothing to
  // read as broken) and grow the moment you zoom in on the timeline.
  const right = 100 - left - width;

  function xToTime(clientX: number): number {
    const rect = containerRef.current!.getBoundingClientRect();
    const frac = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
    return frac * total;
  }

  function handleMouseDown(e: React.MouseEvent) {
    if (!onNavigate) return;
    dragRef.current = { startX: e.clientX, startT: xToTime(e.clientX) };

    function handleMouseMove(ev: MouseEvent) {
      if (!dragRef.current) return;
      const endT = xToTime(ev.clientX);
      const a = Math.min(dragRef.current.startT, endT);
      const b = Math.max(dragRef.current.startT, endT);
      // A near-zero-width drag reads as a click: recenter the current
      // window on the clicked point instead of collapsing it to nothing.
      if (Math.abs(ev.clientX - dragRef.current.startX) < 3) return;
      onNavigate!(a, b);
    }
    function handleMouseUp(ev: MouseEvent) {
      if (dragRef.current && Math.abs(ev.clientX - dragRef.current.startX) < 3) {
        const span = windowEnd - windowStart || total;
        const center = dragRef.current.startT;
        let start = center - span / 2;
        let end = center + span / 2;
        if (start < 0) { end -= start; start = 0; }
        if (end > total) { start -= end - total; end = total; }
        onNavigate!(Math.max(0, start), Math.min(total, end));
      }
      dragRef.current = null;
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    }
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
  }

  return (
    <div
      ref={containerRef}
      onMouseDown={handleMouseDown}
      title={onNavigate ? "drag to select a time range, or click to recenter" : undefined}
      style={{ position: "relative", marginBottom: 16, height: 18, cursor: onNavigate ? "pointer" : "default" }}
    >
      <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden" }}>
        {segments.map((seg, i) => (
          <div key={i} style={{ width: `${seg.widthPct}%`, background: phaseColor(seg.phase) }} />
        ))}
        {segments.length === 0 && <div style={{ width: "100%", background: "var(--panel-control)" }} />}
      </div>
      {left > 0 && (
        <div
          style={{
            position: "absolute", top: 0, left: 0, width: `${left}%`, height: 8,
            background: "rgba(15,18,20,0.72)", borderRadius: "4px 0 0 4px", pointerEvents: "none",
          }}
        />
      )}
      {right > 0 && (
        <div
          style={{
            position: "absolute", top: 0, right: 0, width: `${right}%`, height: 8,
            background: "rgba(15,18,20,0.72)", borderRadius: "0 4px 4px 0", pointerEvents: "none",
          }}
        />
      )}
      <div
        title="current zoom window"
        style={{
          position: "absolute",
          top: -3,
          left: `${left}%`,
          width: `${width}%`,
          height: 14,
          border: "1px solid var(--accent)",
          borderRadius: 3,
          pointerEvents: "none",
        }}
      />
    </div>
  );
}
