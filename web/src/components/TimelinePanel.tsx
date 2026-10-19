import type { Phase } from "../types/contract";
import type { Timeline } from "../lib/useTimeline";
import { ChannelTimeline, type EventMarker } from "./ChannelTimeline";
import { ChannelPicker } from "./ChannelPicker";
import { PresetBar } from "./PresetBar";
import { PhaseCaption } from "./PhaseCaption";
import { PhaseMinimap } from "./PhaseMinimap";

const ZOOM_BUTTON: React.CSSProperties = {
  width: 24, height: 24, borderRadius: 6, background: "var(--panel-control)", border: "1px solid var(--border)",
  color: "var(--text-primary)", fontSize: 14, lineHeight: 1, cursor: "pointer",
};

// Spec 03 §5.2 / §5.9 — the timeline chart: minimap, preset bar, channel
// picker, the chart with phase tint (and, on a flight, event markers) and
// the phase caption. Shared by Flight view and Log preview.
export function TimelinePanel({
  tl, phases, availableChannels, startUtc, hasPhaseWarning, markers, emptyText,
}: {
  tl: Timeline;
  phases: Phase[];
  availableChannels: string[] | null | undefined;
  startUtc: string | null;
  hasPhaseWarning: boolean;
  markers?: EventMarker[];
  emptyText: string;
}) {
  const { visibleWindow } = tl;

  function formatTimeRange(startS: number, endS: number): string {
    if (!startUtc) return "—";
    const base = new Date(startUtc);
    const fmt = (s: number) => new Date(base.getTime() + s * 1000).toISOString().slice(11, 16);
    return `${fmt(startS)}–${fmt(endS)} (${Math.round((endS - startS) / 60)} min)`;
  }

  // Spec 07 §5: an unavailable channel in the current selection applies
  // the rest and shows a quiet note rather than being silently dropped.
  const availableSet = availableChannels ? new Set(availableChannels) : null;
  const unavailableActiveLabels = availableSet
    ? tl.activeSlots
        .filter((id) => {
          const sg = tl.slotGroups.find((s) => s.id === id);
          return !(sg ? sg.members : [id]).some((cid) => availableSet.has(cid));
        })
        .map((id) => tl.slotGroups.find((s) => s.id === id)?.label ?? tl.channelRegistry.find((c) => c.id === id)?.label ?? id)
    : [];

  return (
    <div id="timeline" style={{ background: "var(--panel)", borderRadius: 12, padding: "18px 20px", flexShrink: 0 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>Timeline</span>
        {tl.hasTimeline && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="mono" style={{ fontSize: 11, color: "var(--text-secondary)", marginRight: 4 }}>
              {formatTimeRange(visibleWindow[0], visibleWindow[1])}
            </span>
            <button type="button" onClick={() => tl.stepZoom("out")} style={ZOOM_BUTTON}>&minus;</button>
            <button type="button" onClick={() => tl.stepZoom("in")} style={ZOOM_BUTTON}>+</button>
            <button
              type="button"
              onClick={tl.resetZoom}
              style={{ fontSize: 11, background: "none", border: "none", color: "var(--link)", textDecoration: "underline", textDecorationColor: "var(--link-underline)", textUnderlineOffset: 2, cursor: "pointer", marginLeft: 6 }}
            >
              Full flight
            </button>
          </div>
        )}
      </div>

      {hasPhaseWarning && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, background: "rgba(234,179,8,0.1)", border: "1px solid rgba(234,179,8,0.3)", borderRadius: 8, padding: "8px 12px", marginBottom: 10 }}>
          <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--severity-watch)", flexShrink: 0 }} />
          <span style={{ fontSize: 12 }}>
            Phase detection didn't find a clear climb or cruise for this flight — shown below as one continuous segment.
          </span>
        </div>
      )}

      {/* Spec 03 v0.7 §5.2: one navigational bar, not two — the minimap;
          the phases in view are a tint on the chart itself. */}
      <PhaseMinimap
        phases={phases}
        fullEnd={tl.fullEnd}
        windowStart={visibleWindow[0]}
        windowEnd={visibleWindow[1]}
        onNavigate={tl.navigateTo}
      />

      {tl.hasTimeline ? (
        <>
          <PresetBar
            presets={tl.presets}
            chartState={tl.chartState}
            activePresetId={tl.presetId}
            insightLabel={tl.insightLabel}
            previousLabel={tl.previousStateLabel}
            onSelectPreset={tl.selectPreset}
            onRevert={tl.revert}
            onSaveAsPreset={() => tl.setSavePresetDraft("")}
            onBack={tl.backFromInsight}
          />
          {tl.savePresetDraft !== null && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
              <input
                autoFocus
                type="text"
                placeholder="Preset name…"
                value={tl.savePresetDraft}
                onChange={(e) => tl.setSavePresetDraft(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && tl.confirmSaveAsPreset()}
                style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 9px", color: "var(--text-primary)", fontSize: 12 }}
              />
              <button
                type="button"
                onClick={tl.confirmSaveAsPreset}
                disabled={!tl.savePresetDraft.trim()}
                style={{ padding: "4px 10px", borderRadius: 6, background: "var(--brand)", border: "none", color: "var(--on-brand)", fontSize: 11, fontWeight: 600, cursor: tl.savePresetDraft.trim() ? "pointer" : "default" }}
              >
                Save
              </button>
              <button
                type="button"
                onClick={() => tl.setSavePresetDraft(null)}
                style={{ padding: "4px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: "pointer" }}
              >
                Cancel
              </button>
            </div>
          )}
          <ChannelPicker
            registry={tl.channelRegistry}
            slotGroups={tl.slotGroups}
            maxSlots={tl.maxSlots}
            activeSlots={tl.activeSlots}
            availableChannels={availableChannels ?? null}
            colorFor={tl.colorFor}
            onToggle={tl.togglePickerChannel}
            expandGroups={tl.expandGroups}
          />
          {unavailableActiveLabels.length > 0 && (
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10, marginTop: -6 }}>
              {unavailableActiveLabels.join(", ")} not recorded in this log.
            </div>
          )}
          <ChannelTimeline
            series={tl.seriesCache}
            activeChannels={tl.activeChannelIds}
            colorFor={tl.colorFor}
            phases={phases}
            highlight={tl.highlight}
            zoomWindow={tl.zoomWindow}
            onZoomChange={(s, e) => tl.setVisibleWindow([s, e])}
            markers={markers}
          />
        </>
      ) : (
        <div style={{ fontSize: 12, color: "var(--text-tertiary)", padding: "16px 0" }}>{emptyText}</div>
      )}

      <PhaseCaption
        phases={phases}
        windowStart={visibleWindow[0]}
        windowEnd={visibleWindow[1]}
        undifferentiatedNote={hasPhaseWarning ? "undifferentiated" : undefined}
      />
    </div>
  );
}
