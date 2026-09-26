import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { InsightCard } from "../components/InsightCard";
import { SeverityBadge } from "../components/SeverityBadge";
import { ChannelTimeline } from "../components/ChannelTimeline";
import { ChannelPicker } from "../components/ChannelPicker";
import { PresetBar } from "../components/PresetBar";
import { PhaseCaption } from "../components/PhaseCaption";
import { PhaseMinimap } from "../components/PhaseMinimap";
import { fixtureFlightById, flightAnalysis as fixtureFlight, insightSet as fixtureInsights, kacvSeries, sourceFilename } from "../lib/fixtures";
import { getEngineClient } from "../lib/engineClient";
import { toSeriesFixture } from "../lib/series";
import { assignChannelColors } from "../lib/channels";
import { useChartSession } from "../lib/chartSession";
import { colors as themeColors } from "../theme/colors";
import type {
  Annotation, ChannelRegistryEntry, ChartPreset, FlightAnalysis,
  Insight, InsightSeverity, InsightSet, SeriesFixture, SlotGroupEntry, TopicResult,
} from "../types/contract";

const SEVERITY_RANK: Record<InsightSeverity, number> = { limit: 0, warning: 1, watch: 2, info: 3 };
const client = getEngineClient();

// Spec 03 v0.3 §5.2: when a topic has more than one fired insight, the
// card (Analysis) and the list use the same one — its most severe.
function topTopicInsight(topic: TopicResult): Insight | null {
  if (!topic.insights.length) return null;
  return [...topic.insights].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])[0];
}

function noInsightSummaryText(topics: TopicResult[]): string {
  const names = topics.slice(0, 2).map((t) => t.topic_id.replace(/_/g, " "));
  const remaining = topics.length - names.length;
  const namesStr = remaining > 0 ? `${names.join(", ")}, and ${remaining} other${remaining === 1 ? "" : "s"}` : names.join(" and ");
  return `${topics.length} topic${topics.length === 1 ? "" : "s"} ${topics.length === 1 ? "was" : "were"} analyzed with nothing to flag — ${namesStr}. See Analysis section for the full picture.`;
}

function refsMatch(a: Annotation["ref"], b: Annotation["ref"]): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "insight" && b.kind === "insight") return a.insight_id === b.insight_id;
  if (a.kind !== "insight" && b.kind !== "insight") return a.ref === b.ref;
  return false;
}

// Order-independent — a preset's channels and the active slot list are
// both "one entry per slot" (Spec 07 D3), just not necessarily in the
// same order once channels have been added/removed by hand.
function sameSlotSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const setB = new Set(b);
  return a.every((id) => setB.has(id));
}

const FALLBACK_OVERVIEW_IDS = ["rpm", "ias_kt", "oil_temp_f", "egt_spread_f"];

function expandSlotsWith(slots: string[], groups: SlotGroupEntry[]): string[] {
  return slots.flatMap((id) => groups.find((sg) => sg.id === id)?.members ?? [id]);
}

export function FlightView() {
  const { flightId } = useParams();
  const navigate = useNavigate();
  const [zoomWindow, setZoomWindow] = useState<[number, number] | null>(null);
  const [visibleWindow, setVisibleWindow] = useState<[number, number]>([0, 0]);
  const [highlight, setHighlight] = useState<{ start_s: number; end_s: number } | null>(null);

  // Spec 07 §4/§6/§7 chart state — the picker/preset bar/timeline all
  // read from this rather than each other, so there is exactly one
  // source of truth for "what's on the chart right now." Held in a
  // context above the router (D7), not local state, so it survives
  // navigating away from and back to Flight view within a session.
  const {
    initialized: chartInitialized, setInitialized: setChartInitialized,
    activeSlots, setActiveSlots, presetId, setPresetId, chartState, setChartState,
    channelColors, setChannelColors,
    insightSnapshot, setInsightSnapshot, insightLabel, setInsightLabel,
  } = useChartSession();
  const [channelRegistry, setChannelRegistry] = useState<ChannelRegistryEntry[]>([]);
  const [slotGroups, setSlotGroups] = useState<SlotGroupEntry[]>([]);
  const [maxSlots, setMaxSlots] = useState(6);
  const [presets, setPresets] = useState<ChartPreset[]>([]);
  const [seriesCache, setSeriesCache] = useState<SeriesFixture>({ flight_id: "", channels: {} });
  const [hasTimeline, setHasTimeline] = useState(true);
  const [savePresetDraft, setSavePresetDraft] = useState<string | null>(null);

  const [flightAnalysis, setFlightAnalysis] = useState<FlightAnalysis>(fixtureFlight);
  const [insightSet, setInsightSet] = useState<InsightSet>(fixtureInsights);
  const [filename, setFilename] = useState(sourceFilename(fixtureFlight.source_keys[0]));
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(false);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);

  function expandSlots(slots: string[]): string[] {
    return expandSlotsWith(slots, slotGroups);
  }

  function channelMetaFor(id: string, registry: ChannelRegistryEntry[]): { label: string; unit: string } | undefined {
    const c = registry.find((r) => r.id === id);
    return c ? { label: c.label, unit: c.unit ?? "" } : undefined;
  }

  // Spec 07 D7: chart state (a preset or a Modified set) carries across
  // flights within a session — only resolved from
  // AppSettings.flight_chart.last_preset_id the first time Flight view
  // opens this session (chartInitialized, from the session context —
  // survives this component unmounting/remounting via the Flights list).

  useEffect(() => {
    let cancelled = false;
    setZoomWindow(null);
    setHighlight(null);

    // D7's Insight exception: an insight belongs to one flight, so
    // moving to another leaves Insight and restores the state before it
    // — computed as a plain local value (not read back from state) since
    // the setState calls below don't apply until next render.
    const carriedState =
      chartState === "insight" && insightSnapshot
        ? insightSnapshot
        : { activeSlots, presetId, chartState: chartState as "preset" | "modified" };
    if (chartState === "insight") {
      setActiveSlots(carriedState.activeSlots);
      setPresetId(carriedState.presetId);
      setChartState(carriedState.chartState);
    }
    setInsightSnapshot(null);
    setInsightLabel(undefined);
    setSavePresetDraft(null);

    async function load() {
      if (!flightId) {
        // No id in the URL: send to a real flight if one exists in this
        // workspace, otherwise fall through to the bundled fixture below.
        try {
          const flights = await client.listFlights();
          if (!cancelled && flights.length > 0) {
            navigate(`/flights/${flights[0].flight_id}`, { replace: true });
            return;
          }
        } catch {
          // server unreachable — fixture is already the current state, nothing to do
        }
        if (!cancelled) setUsingFixture(true);
        return;
      }
      setLoading(true);
      try {
        const [got, registryResult, presetsResult, appSettings] = await Promise.all([
          client.getFlight(flightId),
          client.getChannelRegistry(),
          client.getChartPresets(),
          client.getAppSettings(),
        ]);
        if (cancelled) return;
        setFlightAnalysis(got.flight_analysis);
        setInsightSet(got.insight_set);
        // A raw content-hash source_key is not a filename — if the server
        // genuinely has no recorded filename for this flight (no import
        // history at all, not just no persisted copy — that gap is
        // server.py's _source_filename's job to close), say so plainly
        // rather than showing what looks like a broken/garbled name.
        setFilename(got.source_filename ?? "unknown source file");
        setUsingFixture(false);

        setChannelRegistry(registryResult.channels);
        setSlotGroups(registryResult.slot_groups);
        setMaxSlots(registryResult.max_chart_slots);
        setPresets(presetsResult.presets);

        let slotsToLoad: string[];
        if (!chartInitialized) {
          const lastPresetId = appSettings.flight_chart?.last_preset_id as string | undefined;
          const initialPreset =
            presetsResult.presets.find((p) => p.id === lastPresetId) ??
            presetsResult.presets.find((p) => p.id === "overview") ??
            presetsResult.presets[0] ?? null;
          slotsToLoad = initialPreset?.channels ?? [];
          setActiveSlots(slotsToLoad);
          setPresetId(initialPreset?.id ?? null);
          setChartState("preset");
          setChartInitialized(true);
        } else {
          // Already had a selection this session (D7) — carry it into
          // this flight unchanged; only the underlying series data (and
          // per-flight availability) is flight-specific.
          slotsToLoad = carriedState.activeSlots;
        }
        setSeriesCache({ flight_id: flightId, channels: {} });

        try {
          const idsToFetch = expandSlotsWith(slotsToLoad, registryResult.slot_groups);
          const raw = await client.getFlightSeries(flightId, idsToFetch);
          if (!cancelled) {
            const fixture = toSeriesFixture(flightId, raw, (id) => channelMetaFor(id, registryResult.channels));
            setSeriesCache({ flight_id: flightId, channels: fixture.channels });
            setHasTimeline(true);
          }
        } catch {
          if (!cancelled) setHasTimeline(false);
        }

        try {
          const annRes = await client.listAnnotations(flightId);
          if (!cancelled) setAnnotations(annRes.annotations);
        } catch {
          if (!cancelled) setAnnotations([]);
        }
      } catch {
        if (!cancelled) {
          // No live server, or this id doesn't exist there — a fixture
          // flight matching the requested id (e.g. an ECU event card
          // linking to the real KSFF flight, Spec 03 v0.9 §5.4) wins over
          // the generic KACV default, so every event card lands on its
          // own actual flight instead of a stand-in that can't show it.
          const known = fixtureFlightById(flightId);
          const fa = known?.analysis ?? fixtureFlight;
          const series = known ? known.series : kacvSeries;
          setFlightAnalysis(fa);
          setInsightSet(known?.insightSet ?? fixtureInsights);
          setFilename(sourceFilename(fa.source_keys[0]));
          setAnnotations([]); // fixture mode has no server to persist notes through
          setUsingFixture(true);

          // No live registry/presets endpoint to fall back to either — a
          // small registry synthesized from whatever this fixture's own
          // series actually carries keeps the picker functional, just
          // limited to that fixture's channels rather than the full 36.
          const syntheticRegistry: ChannelRegistryEntry[] = series
            ? Object.entries(series.channels).map(([id, ch]) => ({
                id, unit: ch.unit, description: ch.label, label: ch.label,
                group: "flight", slot_group: null, companions: [], unit_variant_of: null,
              }))
            : [];
          const overviewIds = FALLBACK_OVERVIEW_IDS.filter((id) => series?.channels[id]);
          const syntheticPreset: ChartPreset = { id: "overview", label: "Overview", description: "", channels: overviewIds };
          setChannelRegistry(syntheticRegistry);
          setSlotGroups([]);
          setMaxSlots(6);
          setPresets(overviewIds.length ? [syntheticPreset] : []);

          if (!chartInitialized) {
            setActiveSlots(overviewIds);
            setPresetId(overviewIds.length ? "overview" : null);
            setChartState("preset");
            setChartInitialized(true);
          } else {
            // D7 still applies in fixture mode: carry the selection over,
            // restricted to whatever this particular fixture actually has.
            const carried = carriedState.activeSlots.filter((id) => series?.channels[id]);
            setActiveSlots(carried.length ? carried : overviewIds);
          }
          setSeriesCache(series ?? { flight_id: flightId, channels: {} });
          setHasTimeline(series !== null);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flightId, navigate]);

  // Slot colors are assigned by identity, not position (Spec 07 §9) — a
  // channel keeps its color for as long as it stays active, so this has
  // to carry the previous assignment forward rather than recompute from
  // nothing on every render.
  const activeChannelIds = useMemo(() => expandSlots(activeSlots), [activeSlots, slotGroups]);
  useEffect(() => {
    setChannelColors((prev) => assignChannelColors(activeChannelIds, prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChannelIds]);
  const colorFor = useMemo(() => (id: string) => channelColors[id] ?? themeColors.textSecondary, [channelColors]);

  function ensureLoaded(ids: string[]) {
    if (usingFixture || !flightId) return; // fixture series is already fully present in the cache
    const missing = ids.filter((id) => !seriesCache.channels[id]);
    if (missing.length === 0) return;
    client
      .getFlightSeries(flightId, missing)
      .then((raw) => {
        const fixture = toSeriesFixture(flightId, raw, (id) => channelMetaFor(id, channelRegistry));
        setSeriesCache((prev) => ({ flight_id: flightId, channels: { ...prev.channels, ...fixture.channels } }));
      })
      .catch(() => {
        // leave the cache as-is — ChannelTimeline already skips channels it has no data for
      });
  }

  function handleTogglePickerChannel(slotId: string) {
    const isActive = activeSlots.includes(slotId);
    let next: string[];
    if (isActive) {
      next = activeSlots.filter((id) => id !== slotId);
    } else {
      // Spec 07 §7.1: the EGT group and its own members are mutually
      // exclusive on the chart — picking one swaps out the other rather
      // than just adding a slot, so this can free a slot as often as it
      // uses one (never blocked by a full chart either way).
      const asGroup = slotGroups.find((sg) => sg.id === slotId);
      const parentGroup = slotGroups.find((sg) => sg.members.includes(slotId) && activeSlots.includes(sg.id));
      const base = asGroup
        ? activeSlots.filter((id) => !asGroup.members.includes(id))
        : parentGroup
          ? activeSlots.filter((id) => id !== parentGroup.id)
          : activeSlots;
      if (base.length >= maxSlots) return; // picker already disables this; a no-op guard either way
      next = [...base, slotId];
    }
    setActiveSlots(next);
    ensureLoaded(expandSlots(next));
    const basePreset = presets.find((p) => p.id === presetId);
    setChartState(basePreset && sameSlotSet(basePreset.channels, next) ? "preset" : "modified");
  }

  function handleSelectPreset(id: string) {
    const preset = presets.find((p) => p.id === id);
    if (!preset) return;
    setActiveSlots(preset.channels);
    setPresetId(id);
    setChartState("preset");
    ensureLoaded(expandSlots(preset.channels));
    if (!usingFixture) {
      client
        .getAppSettings()
        .then((s) => client.saveAppSettings({ ...s, flight_chart: { ...(s.flight_chart ?? {}), last_preset_id: id } }))
        .catch(() => {
          // remembering the last preset is a convenience, not required for this session to work
        });
    }
  }

  function handleRevert() {
    const basePreset = presets.find((p) => p.id === presetId);
    if (!basePreset) return;
    setActiveSlots(basePreset.channels);
    setChartState("preset");
    ensureLoaded(expandSlots(basePreset.channels));
  }

  async function handleConfirmSaveAsPreset() {
    if (!savePresetDraft?.trim() || usingFixture) return;
    try {
      const saved = await client.saveUserPreset({ label: savePresetDraft.trim(), channels: activeSlots });
      const presetsRes = await client.getChartPresets();
      setPresets(presetsRes.presets);
      setPresetId(saved.id);
      setChartState("preset");
      setSavePresetDraft(null);
    } catch {
      // leave the draft open so the pilot can see the field still has their text and retry
    }
  }

  function handleBackFromInsight() {
    if (!insightSnapshot) return;
    setActiveSlots(insightSnapshot.activeSlots);
    setPresetId(insightSnapshot.presetId);
    setChartState(insightSnapshot.chartState);
    ensureLoaded(expandSlots(insightSnapshot.activeSlots));
    setInsightSnapshot(null);
    setInsightLabel(undefined);
  }

  async function refreshAnnotations() {
    if (!flightId || usingFixture) return;
    try {
      const res = await client.listAnnotations(flightId);
      setAnnotations(res.annotations);
    } catch {
      // leave whatever was already loaded — a save/delete that reached
      // the server but couldn't refresh isn't worth losing the list over
    }
  }

  async function handleSaveNote(ref: Annotation["ref"], text: string) {
    if (!flightId) return;
    const existing = annotations.find((a) => refsMatch(a.ref, ref));
    try {
      await client.saveAnnotation({ id: existing?.id, flightId, ref, note: text });
      await refreshAnnotations();
    } catch {
      // server unreachable — nothing persisted, leave state as-is
    }
  }

  async function handleDeleteNote(annotationId: string) {
    try {
      await client.deleteAnnotation(annotationId);
      await refreshAnnotations();
    } catch {
      // server unreachable — nothing persisted, leave state as-is
    }
  }

  const flatInsights = useMemo(() => {
    const items: { insight: Insight; topicId: string }[] = [];
    for (const topic of insightSet.topics) {
      for (const insight of topic.insights) items.push({ insight, topicId: topic.topic_id });
    }
    return items.sort((a, b) => SEVERITY_RANK[a.insight.severity] - SEVERITY_RANK[b.insight.severity]);
  }, [insightSet]);

  const noInsightTopics = useMemo(() => insightSet.topics.filter((t) => t.insights.length === 0), [insightSet]);

  const annotationByInsightId = useMemo(() => {
    const map = new Map<string, Annotation>();
    for (const a of annotations) if (a.ref.kind === "insight") map.set(a.ref.insight_id, a);
    return map;
  }, [annotations]);

  const h = flightAnalysis.header;
  const durationMin = flightAnalysis.metrics.duration_min?.value;
  const durationStr = typeof durationMin === "number" ? `${Math.floor(durationMin / 60)}h ${Math.round(durationMin % 60)}m` : "—";
  const hasPhaseWarning = flightAnalysis.quality.some((q) => q.code === "PHASE_TAKEOFF_NOT_DETECTED");
  const fullEnd = flightAnalysis.phases.at(-1)?.end_s ?? 0;

  useEffect(() => {
    setVisibleWindow([0, flightAnalysis.phases.at(-1)?.end_s ?? 0]);
  }, [flightAnalysis]);

  function formatTimeRange(startS: number, endS: number): string {
    if (!h.start_utc) return "—";
    const base = new Date(h.start_utc);
    const fmt = (s: number) => new Date(base.getTime() + s * 1000).toISOString().slice(11, 16);
    const durMin = Math.round((endS - startS) / 60);
    return `${fmt(startS)}–${fmt(endS)} (${durMin} min)`;
  }

  function stepZoom(direction: "in" | "out") {
    const [s, e] = visibleWindow;
    const span = e - s || fullEnd;
    const center = (s + e) / 2;
    let newSpan = direction === "in" ? span * 0.5 : span * 2;
    newSpan = Math.min(Math.max(newSpan, 10), fullEnd);
    let newStart = center - newSpan / 2;
    let newEnd = center + newSpan / 2;
    if (newStart < 0) {
      newEnd -= newStart;
      newStart = 0;
    }
    if (newEnd > fullEnd) {
      newStart -= newEnd - fullEnd;
      newEnd = fullEnd;
    }
    newStart = Math.max(0, newStart);
    setZoomWindow([newStart, newEnd]);
    setVisibleWindow([newStart, newEnd]);
  }

  function handleEvidenceClick(insight: Insight) {
    for (const ev of insight.evidence) {
      if (ev.kind === "series_window") {
        setZoomWindow([ev.start_s, ev.end_s]);
        setVisibleWindow([ev.start_s, ev.end_s]);
        setHighlight({ start_s: ev.start_s, end_s: ev.end_s });
        document.getElementById("timeline")?.scrollIntoView({ behavior: "smooth", block: "center" });

        // Spec 07 §10/D8: enter the Insight chart state and show the
        // evidence's subject channels plus each subject's registry
        // companions (not a display hint carried on the evidence itself
        // — resolved here so editing companions never touches the rules
        // hash) — but only if evidence actually names channels; some
        // evidence is zoom-only and shouldn't touch the chart's channel
        // selection at all.
        if (ev.channels.length > 0) {
          const companionsFor = (id: string) => channelRegistry.find((c) => c.id === id)?.companions ?? [];
          const combined = [...new Set([...ev.channels, ...ev.channels.flatMap(companionsFor)])];
          const capped = combined.slice(0, maxSlots);
          if (chartState !== "insight") {
            setInsightSnapshot({ activeSlots, presetId, chartState: chartState as "preset" | "modified" });
          }
          setActiveSlots(capped);
          setChartState("insight");
          setInsightLabel(insight.message.text);
          ensureLoaded(expandSlots(capped));
        }
        return;
      }
      if (ev.kind === "baseline_point") {
        navigate(`/trends?metric=${ev.metric_id}&flight=${ev.flight_id}`);
        return;
      }
      if (ev.kind === "metric") {
        // No specific flight point to highlight (unlike baseline_point) —
        // just the metric's trend, in the context of this flight.
        navigate(`/trends?metric=${ev.metric_id}&flight=${flightAnalysis.flight_id}`);
        return;
      }
    }
  }

  const previousStateLabel = insightSnapshot ? presets.find((p) => p.id === insightSnapshot.presetId)?.label : undefined;

  // Spec 07 §5: an unavailable channel in the current selection applies
  // the rest and shows a quiet note rather than being silently dropped —
  // the selection itself stays exactly as-is (D7) even for a flight that
  // doesn't record it.
  const unavailableActiveLabels = useMemo(() => {
    const available = flightAnalysis.available_channels;
    if (!available) return [];
    const availableSet = new Set(available);
    return activeSlots
      .filter((id) => {
        const sg = slotGroups.find((s) => s.id === id);
        const ids = sg ? sg.members : [id];
        return !ids.some((cid) => availableSet.has(cid));
      })
      .map((id) => slotGroups.find((s) => s.id === id)?.label ?? channelRegistry.find((c) => c.id === id)?.label ?? id);
  }, [activeSlots, flightAnalysis.available_channels, slotGroups, channelRegistry]);

  // A deselected channel from the current (non-Overview) preset's own
  // topic should stay visible as an inactive tag, not disappear into the
  // "+ Add channel" popover — every chartable channel sharing a group
  // with the preset's own channels shows as a tag either way. Overview
  // stays minimal on purpose (null here keeps ChannelPicker's old
  // active-only row).
  const expandGroups = useMemo<Set<string> | null>(() => {
    if (!presetId || presetId === "overview") return null;
    const basePreset = presets.find((p) => p.id === presetId);
    if (!basePreset) return null;
    const groups = new Set<string>();
    for (const id of basePreset.channels) {
      const sg = slotGroups.find((s) => s.id === id);
      const group = sg
        ? channelRegistry.find((c) => sg.members.includes(c.id))?.group
        : channelRegistry.find((c) => c.id === id)?.group;
      if (group) groups.add(group);
    }
    return groups.size > 0 ? groups : null;
  }, [presetId, presets, slotGroups, channelRegistry]);

  return (
    <NavShell
      right={
        usingFixture ? (
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 20, background: "var(--panel)", border: "1px solid var(--border)" }}>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Sample flight — import your own logs to replace it</span>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 20, background: "var(--panel)", border: "1px solid var(--border)" }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--success)" }} />
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{loading ? "Loading…" : "Up to date"}</span>
          </div>
        )
      }
    >
      <div style={{ display: "flex", flexDirection: "column", width: "100%", minHeight: 0 }}>
        {/* Flight header */}
        <div style={{ flexShrink: 0, padding: "18px 24px 14px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>{h.date}</h1>
            <span className="mono" style={{ fontSize: 13, color: "var(--text-secondary)" }}>
              {durationStr} &middot; {h.engine_hours_start ?? "—"} engine hrs &middot; {h.airport_hint ?? "—"}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
            <span className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>
              {filename}
            </span>
          </div>
        </div>

        {/* Body */}
        <div style={{ flexGrow: 1, display: "flex", minHeight: 0 }}>
          {/* Insight list */}
          <div style={{ width: 376, flexShrink: 0, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{ padding: "16px 20px 10px", flexShrink: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                Insights <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>({flatInsights.length})</span>
              </div>
            </div>
            <div style={{ flexGrow: 1, overflowY: "auto", padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
              {flatInsights.map(({ insight, topicId }) => {
                const existing = annotationByInsightId.get(insight.id);
                return (
                  <InsightCard
                    key={insight.id}
                    insight={insight}
                    topicId={topicId}
                    onClick={() => handleEvidenceClick(insight)}
                    note={existing?.note}
                    notesEnabled={!usingFixture}
                    onSaveNote={(text) => handleSaveNote({ kind: "insight", insight_id: insight.id }, text)}
                    onDeleteNote={existing ? () => handleDeleteNote(existing.id) : undefined}
                  />
                );
              })}
              {flatInsights.length === 0 && noInsightTopics.length === 0 && (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No insights fired for this flight.</div>
              )}
              {noInsightTopics.length > 0 && (
                <div style={{ background: "var(--panel)", borderRadius: 10, padding: "13px 14px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                    <div style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--severity-info)", flexShrink: 0 }} />
                    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.5, color: "var(--severity-info-text)" }}>
                      no fired insights
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4 }}>
                    {noInsightSummaryText(noInsightTopics)}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Main column */}
          <div style={{ flexGrow: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16, minHeight: 0 }}>
            <div id="timeline" style={{ background: "var(--panel)", borderRadius: 12, padding: "18px 20px", flexShrink: 0 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Timeline</span>
                {hasTimeline && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="mono" style={{ fontSize: 11, color: "var(--text-secondary)", marginRight: 4 }}>
                      {formatTimeRange(visibleWindow[0], visibleWindow[1])}
                    </span>
                    <button
                      onClick={() => stepZoom("out")}
                      style={{ width: 24, height: 24, borderRadius: 6, background: "var(--panel-control)", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 14, lineHeight: 1, cursor: "pointer" }}
                    >
                      &minus;
                    </button>
                    <button
                      onClick={() => stepZoom("in")}
                      style={{ width: 24, height: 24, borderRadius: 6, background: "var(--panel-control)", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 14, lineHeight: 1, cursor: "pointer" }}
                    >
                      +
                    </button>
                    <button
                      onClick={() => {
                        setZoomWindow([0, fullEnd]);
                        setVisibleWindow([0, fullEnd]);
                        setHighlight(null);
                      }}
                      style={{ fontSize: 11, background: "none", border: "none", color: "var(--accent)", cursor: "pointer", marginLeft: 6 }}
                    >
                      Full flight
                    </button>
                  </div>
                )}
              </div>

              {hasPhaseWarning && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    background: "rgba(234,179,8,0.1)",
                    border: "1px solid rgba(234,179,8,0.3)",
                    borderRadius: 8,
                    padding: "8px 12px",
                    marginBottom: 10,
                  }}
                >
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--severity-watch)", flexShrink: 0 }} />
                  <span style={{ fontSize: 12 }}>
                    Phase detection didn't find a clear climb or cruise for this flight — shown below as one continuous segment.
                  </span>
                </div>
              )}

              {/* Spec 03 v0.7 §5.2: one navigational bar, not two. The
                  minimap keeps its original job (full-flight orientation,
                  drag-to-navigate); what the old standalone phase band
                  showed now lives as a tint on the chart itself, below. */}
              <PhaseMinimap
                phases={flightAnalysis.phases}
                fullEnd={fullEnd}
                windowStart={visibleWindow[0]}
                windowEnd={visibleWindow[1]}
                onNavigate={(s, e) => {
                  setZoomWindow([s, e]);
                  setVisibleWindow([s, e]);
                }}
              />

              {hasTimeline ? (
                <>
                  <PresetBar
                    presets={presets}
                    chartState={chartState}
                    activePresetId={presetId}
                    insightLabel={insightLabel}
                    previousLabel={previousStateLabel}
                    onSelectPreset={handleSelectPreset}
                    onRevert={handleRevert}
                    onSaveAsPreset={() => setSavePresetDraft("")}
                    onBack={handleBackFromInsight}
                  />
                  {savePresetDraft !== null && (
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                      <input
                        autoFocus
                        type="text"
                        placeholder="Preset name…"
                        value={savePresetDraft}
                        onChange={(e) => setSavePresetDraft(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && handleConfirmSaveAsPreset()}
                        style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 9px", color: "var(--text-primary)", fontSize: 12 }}
                      />
                      <button
                        onClick={handleConfirmSaveAsPreset}
                        disabled={!savePresetDraft.trim()}
                        style={{ padding: "4px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontSize: 11, fontWeight: 600, cursor: savePresetDraft.trim() ? "pointer" : "default" }}
                      >
                        Save
                      </button>
                      <button
                        onClick={() => setSavePresetDraft(null)}
                        style={{ padding: "4px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: "pointer" }}
                      >
                        Cancel
                      </button>
                    </div>
                  )}
                  <ChannelPicker
                    registry={channelRegistry}
                    slotGroups={slotGroups}
                    maxSlots={maxSlots}
                    activeSlots={activeSlots}
                    availableChannels={flightAnalysis.available_channels ?? null}
                    colorFor={colorFor}
                    onToggle={handleTogglePickerChannel}
                    expandGroups={expandGroups}
                  />
                  {unavailableActiveLabels.length > 0 && (
                    <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10, marginTop: -6 }}>
                      {unavailableActiveLabels.join(", ")} not recorded in this log.
                    </div>
                  )}
                  <ChannelTimeline
                    series={seriesCache}
                    activeChannels={activeChannelIds}
                    colorFor={colorFor}
                    phases={flightAnalysis.phases}
                    highlight={highlight}
                    zoomWindow={zoomWindow}
                    onZoomChange={(s, e) => setVisibleWindow([s, e])}
                  />
                </>
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)", padding: "16px 0" }}>
                  No timeline available for this flight (its source log wasn't retained by the server).
                </div>
              )}

              <PhaseCaption
                phases={flightAnalysis.phases}
                windowStart={visibleWindow[0]}
                windowEnd={visibleWindow[1]}
                undifferentiatedNote={hasPhaseWarning ? "undifferentiated" : undefined}
              />
            </div>

            <div style={{ flexShrink: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Analysis</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                {insightSet.topics.map((t) => {
                  const topInsight = topTopicInsight(t);
                  const clickable = Boolean(topInsight && topInsight.evidence.length > 0);
                  const Wrapper = clickable ? "a" : "div";
                  return (
                    <Wrapper
                      key={t.topic_id}
                      href={clickable ? "#timeline" : undefined}
                      onClick={
                        clickable
                          ? (e: React.MouseEvent) => {
                              e.preventDefault();
                              if (topInsight) handleEvidenceClick(topInsight);
                            }
                          : undefined
                      }
                      style={{ display: "block", background: "var(--panel)", borderRadius: 10, padding: "13px 15px", cursor: clickable ? "pointer" : "default" }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>{t.topic_id.replace(/_/g, " ")}</span>
                        {topInsight && <SeverityBadge severity={topInsight.severity} size="sm" />}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.45 }}>{t.analysis.text}</div>
                    </Wrapper>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </NavShell>
  );
}
