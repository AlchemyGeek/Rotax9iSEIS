import { useEffect, useMemo, useRef, useState } from "react";
import { getEngineClient, type SeriesResult, type SeriesWindowRange } from "./engineClient";
import { useChartSession } from "./chartSession";
import { toSeriesFixture } from "./series";
import { assignChannelColors } from "./channels";
import { colors as themeColors } from "../theme/colors";
import type { AppSettings, ChannelRegistryEntry, ChartPreset, Evidence, Phase, SeriesFixture, SlotGroupEntry } from "../types/contract";

const client = getEngineClient();

// Spec 07 / Spec 03 §5.2 and §5.9 — the timeline chart's state (channel
// picker, presets, lazy series loading, zoom, evidence highlight), shared
// by Flight view and Log preview. Lifted out of FlightView unchanged; the
// caller supplies where series come from (a flight id or a skipped log).

const FALLBACK_OVERVIEW_IDS = ["rpm", "ias_kt", "oil_temp_f", "egt_spread_f"];

// Spec 07 §11.3: the whole-flight series is a min/max envelope (one high
// and one low point per 1/400th of the flight — 10–20 s apart on a long
// flight). Zoomed to this span or less, the chart fetches the visible
// stretch (plus a margin) in full and draws every second of it.
export const DETAIL_SPAN_S = 600;
const DETAIL_DEBOUNCE_MS = 300;

type Points = SeriesFixture["channels"][string]["points"];

/** The overview's points outside `[s, e]` with the detail's points inside it. */
export function spliceDetail(overview: Points, detail: Points, [s, e]: [number, number]): Points {
  return [...overview.filter((p) => (p[0] ?? 0) < s), ...detail, ...overview.filter((p) => (p[0] ?? 0) > e)];
}

/**
 * Where in `[start_s, start_s + duration_s]` a limit event reached its
 * reported worst value (Spec 07 §11.4), from that stretch in full detail:
 * the time of the highest (MAX) or lowest (MIN) reading, if it matches the
 * reported value — otherwise null (a limit whose "value" isn't a reading).
 */
export function worstMoment(points: Points, limitType: "MIN" | "MAX", observed: number): number | null {
  let best: [number, number] | null = null;
  for (const [t, v] of points) {
    if (t === null || v === null) continue;
    if (!best || (limitType === "MAX" ? v > best[1] : v < best[1])) best = [t, v];
  }
  return best && Math.abs(best[1] - observed) <= 0.051 ? best[0] : null;
}

function sameSlotSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const s = new Set(b);
  return a.every((id) => s.has(id));
}

export function expandSlotsWith(slots: string[], groups: SlotGroupEntry[]): string[] {
  return slots.flatMap((id) => groups.find((sg) => sg.id === id)?.members ?? [id]);
}

type SeriesWindow = Extract<Evidence, { kind: "series_window" }>;
export type CarriedState = { activeSlots: string[]; presetId: string | null; chartState: "preset" | "modified" };

export function useTimeline({ phases, usingFixture }: { phases: Phase[]; usingFixture: boolean }) {
  const [zoomWindow, setZoomWindow] = useState<[number, number] | null>(null);
  const [visibleWindow, setVisibleWindow] = useState<[number, number]>([0, 0]);
  const [highlight, setHighlight] = useState<{ start_s: number; end_s: number; marker_s?: number } | null>(null);

  // Spec 07 §4/§6/§7 chart state — held in a context above the router
  // (D7), so it survives navigating away from and back to a flight.
  const session = useChartSession();
  const {
    initialized: chartInitialized, setInitialized: setChartInitialized,
    activeSlots, setActiveSlots, presetId, setPresetId, chartState, setChartState,
    channelColors, setChannelColors,
    insightSnapshot, setInsightSnapshot, insightLabel, setInsightLabel,
  } = session;
  const [channelRegistry, setChannelRegistry] = useState<ChannelRegistryEntry[]>([]);
  const [slotGroups, setSlotGroups] = useState<SlotGroupEntry[]>([]);
  const [maxSlots, setMaxSlots] = useState(6);
  const [presets, setPresets] = useState<ChartPreset[]>([]);
  const [seriesCache, setSeriesCache] = useState<SeriesFixture>({ flight_id: "", channels: {} });
  const [hasTimeline, setHasTimeline] = useState(true);
  const [savePresetDraft, setSavePresetDraft] = useState<string | null>(null);
  // Where more channels come from once the chart is set up; fetchWindow,
  // where the host can answer a stretch in full (a flight, not a skipped log).
  const source = useRef<{
    key: string;
    fetch: (ids: string[]) => Promise<SeriesResult>;
    fetchWindow?: (ids: string[], w: SeriesWindowRange) => Promise<SeriesResult>;
  } | null>(null);
  const [detail, setDetail] = useState<{ key: string; window: [number, number]; channels: SeriesFixture["channels"] } | null>(null);

  const fullEnd = phases.at(-1)?.end_s ?? 0;
  useEffect(() => {
    setVisibleWindow([0, phases.at(-1)?.end_s ?? 0]);
  }, [phases]);

  function expandSlots(slots: string[]): string[] {
    return expandSlotsWith(slots, slotGroups);
  }

  function channelMetaFor(id: string, registry: ChannelRegistryEntry[]) {
    const c = registry.find((r) => r.id === id);
    return c ? { label: c.label, unit: c.unit ?? "" } : undefined;
  }

  // D7's Insight exception: an insight belongs to one flight, so moving
  // to another leaves Insight and restores the state before it. Returns
  // the selection to carry into the new flight.
  function beginFlight(): CarriedState {
    setZoomWindow(null);
    setHighlight(null);
    const carried: CarriedState =
      chartState === "insight" && insightSnapshot
        ? insightSnapshot
        : { activeSlots, presetId, chartState: chartState as "preset" | "modified" };
    if (chartState === "insight") {
      setActiveSlots(carried.activeSlots);
      setPresetId(carried.presetId);
      setChartState(carried.chartState);
    }
    setInsightSnapshot(null);
    setInsightLabel(undefined);
    setSavePresetDraft(null);
    return carried;
  }

  async function setupLive(args: {
    key: string;
    fetch: (ids: string[]) => Promise<SeriesResult>;
    fetchWindow?: (ids: string[], w: SeriesWindowRange) => Promise<SeriesResult>;
    registry: { channels: ChannelRegistryEntry[]; slot_groups: SlotGroupEntry[]; max_chart_slots: number };
    presets: ChartPreset[];
    appSettings: AppSettings;
    carried: CarriedState;
    isCancelled: () => boolean;
  }) {
    const { key, registry, carried, isCancelled } = args;
    source.current = { key, fetch: args.fetch, fetchWindow: args.fetchWindow };
    setDetail(null);
    setChannelRegistry(registry.channels);
    setSlotGroups(registry.slot_groups);
    setMaxSlots(registry.max_chart_slots);
    setPresets(args.presets);
    let slotsToLoad: string[];
    if (!chartInitialized) {
      const lastPresetId = args.appSettings.flight_chart?.last_preset_id as string | undefined;
      const initialPreset =
        args.presets.find((p) => p.id === lastPresetId) ??
        args.presets.find((p) => p.id === "overview") ??
        args.presets[0] ?? null;
      slotsToLoad = initialPreset?.channels ?? [];
      setActiveSlots(slotsToLoad);
      setPresetId(initialPreset?.id ?? null);
      setChartState("preset");
      setChartInitialized(true);
    } else {
      // Already had a selection this session (D7) — carry it over.
      slotsToLoad = carried.activeSlots;
    }
    setSeriesCache({ flight_id: key, channels: {} });
    try {
      const raw = await args.fetch(expandSlotsWith(slotsToLoad, registry.slot_groups));
      if (!isCancelled()) {
        const fixture = toSeriesFixture(key, raw, (id) => channelMetaFor(id, registry.channels));
        setSeriesCache({ flight_id: key, channels: fixture.channels });
        setHasTimeline(true);
      }
    } catch {
      if (!isCancelled()) setHasTimeline(false);
    }
  }

  // No live server: a small registry synthesized from the fixture's own
  // series keeps the picker functional, limited to that fixture's channels.
  function setupFixture(key: string, series: SeriesFixture | null, carried: CarriedState) {
    source.current = null;
    setDetail(null);
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
      const kept = carried.activeSlots.filter((id) => series?.channels[id]);
      setActiveSlots(kept.length ? kept : overviewIds);
    }
    setSeriesCache(series ?? { flight_id: key, channels: {} });
    setHasTimeline(series !== null);
  }

  // Slot colors are assigned by identity, not position (Spec 07 §9).
  const activeChannelIds = useMemo(() => expandSlots(activeSlots), [activeSlots, slotGroups]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    setChannelColors((prev) => assignChannelColors(activeChannelIds, prev));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeChannelIds]);
  const colorFor = useMemo(() => (id: string) => channelColors[id] ?? themeColors.textSecondary, [channelColors]);

  // §11.3: zoomed to DETAIL_SPAN_S or less, fetch the visible stretch in full.
  useEffect(() => {
    const src = source.current;
    const [s, e] = visibleWindow;
    const span = e - s;
    if (usingFixture || !src?.fetchWindow || span <= 0 || span > DETAIL_SPAN_S || activeChannelIds.length === 0) {
      setDetail(null);
      return;
    }
    if (detail && detail.key === src.key && detail.window[0] <= s && detail.window[1] >= e
        && activeChannelIds.every((id) => detail.channels[id] || !seriesCache.channels[id])) return;   // already covered
    const margin = span * 0.25;
    const w: [number, number] = [Math.max(0, s - margin), e + margin];
    const timer = setTimeout(() => {
      src.fetchWindow!(activeChannelIds, { start_s: w[0], end_s: w[1] })
        .then((raw) => {
          if (source.current?.key !== src.key) return;
          const fixture = toSeriesFixture(src.key, raw, (id) => channelMetaFor(id, channelRegistry));
          setDetail({ key: src.key, window: w, channels: fixture.channels });
        })
        .catch(() => {
          // keep the overview — it is still correct, only coarser
        });
    }, DETAIL_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleWindow, activeChannelIds, usingFixture, seriesCache]);

  // What the chart draws: the overview, with the detailed stretch spliced in.
  const series = useMemo<SeriesFixture>(() => {
    if (!detail || detail.key !== seriesCache.flight_id) return seriesCache;
    const channels = { ...seriesCache.channels };
    for (const [id, ch] of Object.entries(detail.channels)) {
      const base = channels[id];
      if (base) channels[id] = { ...base, points: spliceDetail(base.points, ch.points, detail.window) };
    }
    return { ...seriesCache, channels };
  }, [seriesCache, detail]);

  /** §11.4: when a limit event reached its worst value, from its stretch in full. */
  async function findWorstMoment(param: string, limitType: "MIN" | "MAX", observed: number, start_s: number, duration_s: number): Promise<number | null> {
    const src = source.current;
    if (usingFixture || !src?.fetchWindow) return null;
    try {
      const raw = await src.fetchWindow([param], { start_s, end_s: start_s + Math.max(duration_s, 1) });
      const points = raw[param];
      return points ? worstMoment(points as Points, limitType, observed) : null;
    } catch {
      return null;
    }
  }

  function ensureLoaded(ids: string[]) {
    if (usingFixture || !source.current) return;
    const missing = ids.filter((id) => !seriesCache.channels[id]);
    if (missing.length === 0) return;
    const { key, fetch } = source.current;
    fetch(missing)
      .then((raw) => {
        const fixture = toSeriesFixture(key, raw, (id) => channelMetaFor(id, channelRegistry));
        setSeriesCache((prev) => ({ flight_id: key, channels: { ...prev.channels, ...fixture.channels } }));
      })
      .catch(() => {
        // leave the cache as-is — ChannelTimeline skips channels it has no data for
      });
  }

  function togglePickerChannel(slotId: string) {
    const isActive = activeSlots.includes(slotId);
    let next: string[];
    if (isActive) {
      next = activeSlots.filter((id) => id !== slotId);
    } else {
      // Spec 07 §7.1: the EGT group and its own members are mutually exclusive.
      const asGroup = slotGroups.find((sg) => sg.id === slotId);
      const parentGroup = slotGroups.find((sg) => sg.members.includes(slotId) && activeSlots.includes(sg.id));
      const base = asGroup
        ? activeSlots.filter((id) => !asGroup.members.includes(id))
        : parentGroup
          ? activeSlots.filter((id) => id !== parentGroup.id)
          : activeSlots;
      if (base.length >= maxSlots) return;
      next = [...base, slotId];
    }
    setActiveSlots(next);
    ensureLoaded(expandSlots(next));
    const basePreset = presets.find((p) => p.id === presetId);
    setChartState(basePreset && sameSlotSet(basePreset.channels, next) ? "preset" : "modified");
  }

  function selectPreset(id: string) {
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
          // remembering the last preset is a convenience
        });
    }
  }

  function revert() {
    const basePreset = presets.find((p) => p.id === presetId);
    if (!basePreset) return;
    setActiveSlots(basePreset.channels);
    setChartState("preset");
    ensureLoaded(expandSlots(basePreset.channels));
  }

  async function confirmSaveAsPreset() {
    if (!savePresetDraft?.trim() || usingFixture) return;
    try {
      const saved = await client.saveUserPreset({ label: savePresetDraft.trim(), channels: activeSlots });
      const presetsRes = await client.getChartPresets();
      setPresets(presetsRes.presets);
      setPresetId(saved.id);
      setChartState("preset");
      setSavePresetDraft(null);
    } catch {
      // leave the draft open so the pilot can retry
    }
  }

  function resetZoom() {
    setZoomWindow([0, fullEnd]);
    setVisibleWindow([0, fullEnd]);
    setHighlight(null);
  }

  function backFromInsight() {
    if (!insightSnapshot) return;
    setActiveSlots(insightSnapshot.activeSlots);
    setPresetId(insightSnapshot.presetId);
    setChartState(insightSnapshot.chartState);
    ensureLoaded(expandSlots(insightSnapshot.activeSlots));
    setInsightSnapshot(null);
    setInsightLabel(undefined);
    resetZoom();
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

  function navigateTo(s: number, e: number) {
    setZoomWindow([s, e]);
    setVisibleWindow([s, e]);
  }

  // A series_window evidence: zoom to it, mark it, and (Spec 07 §10/D8)
  // enter the Insight chart state with its channels plus companions.
  function focusEvidence(ev: SeriesWindow, label: string) {
    navigateTo(ev.start_s, ev.end_s);
    // marker_start_s/end_s: the event's own, unpadded bounds when the
    // window is widened for context — a brief alert gets a dot, not a box.
    const markerS = ev.marker_start_s !== undefined && ev.marker_end_s !== undefined
      ? (ev.marker_start_s + ev.marker_end_s) / 2
      : undefined;
    setHighlight({ start_s: ev.start_s, end_s: ev.end_s, marker_s: markerS });
    document.getElementById("timeline")?.scrollIntoView?.({ behavior: "smooth", block: "center" });
    if (ev.channels.length > 0) {
      const companionsFor = (id: string) => channelRegistry.find((c) => c.id === id)?.companions ?? [];
      const combined = [...new Set([...ev.channels, ...ev.channels.flatMap(companionsFor)])];
      const capped = combined.slice(0, maxSlots);
      if (chartState !== "insight") {
        setInsightSnapshot({ activeSlots, presetId, chartState: chartState as "preset" | "modified" });
      }
      setActiveSlots(capped);
      setChartState("insight");
      setInsightLabel(label);
      ensureLoaded(expandSlots(capped));
    }
  }

  // An event with no evidence window of its own (no insight carries it):
  // zoom around it and mark it.
  function focusMoment(start_s: number, duration_s: number) {
    const pad = Math.max(duration_s * 0.5, 15);
    const s = Math.max(0, start_s - pad);
    const e = Math.min(fullEnd || start_s + duration_s + pad, start_s + duration_s + pad);
    navigateTo(s, e);
    setHighlight({ start_s: s, end_s: e, marker_s: start_s + duration_s / 2 });
    document.getElementById("timeline")?.scrollIntoView?.({ behavior: "smooth", block: "center" });
  }

  const previousStateLabel = insightSnapshot ? presets.find((p) => p.id === insightSnapshot.presetId)?.label : undefined;

  // A deselected channel from the current (non-Overview) preset's own
  // topic stays visible as an inactive tag; Overview stays minimal.
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

  return {
    // state
    zoomWindow, visibleWindow, setVisibleWindow, highlight, fullEnd,
    channelRegistry, slotGroups, maxSlots, presets, seriesCache, series, hasTimeline,
    savePresetDraft, setSavePresetDraft, activeSlots, activeChannelIds, presetId, chartState, insightLabel,
    previousStateLabel, expandGroups, colorFor,
    // setup
    beginFlight, setupLive, setupFixture,
    // actions
    togglePickerChannel, selectPreset, revert, confirmSaveAsPreset, backFromInsight, stepZoom, resetZoom,
    navigateTo, focusEvidence, focusMoment, findWorstMoment,
  };
}

export type Timeline = ReturnType<typeof useTimeline>;
