import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { InsightCard } from "../components/InsightCard";
import { FilterEditor } from "../components/FilterEditor";
import { notifyFiltersChanged } from "../lib/filterAttention";
import { PhaseFilter } from "../components/PhaseFilter";
import { fixtureFlightById, flightAnalysis as fixtureFlight, insightSet as fixtureInsights, kacvSeries, sourceFilename } from "../lib/fixtures";
import { pickableChannels } from "../lib/channels";
import { getEngineClient } from "../lib/engineClient";
import { useTopicHelp } from "../lib/topicHelp";
import { useAircraftSummary } from "../lib/aircraftSummary";
import { phaseAtTime } from "../lib/phases";
import { ExcludeConfirmDialog } from "../components/ExcludeDialog";
import { InlineHelp } from "../components/InlineHelp";
import { CasEventDetails } from "../components/CasEventDetails";
import { TimelinePanel } from "../components/TimelinePanel";
import { FlightFacts } from "../components/FlightFacts";
import { EventsTable } from "../components/EventsTable";
import { TopicCards } from "../components/TopicCards";
import { RuleEditorPanel } from "../components/RuleEditorPanel";
import { useTimeline } from "../lib/useTimeline";
import { flightFacts } from "../lib/flightFacts";
import { buildEventRows, insightEventId, type EventRow } from "../lib/flightEvents";
import { REFERENCE_DERIVED_TOPICS, topicCardModel } from "../lib/topicRoster";
import { isCasInsightEvent } from "../types/contract";
import type {
  Annotation, CasEvent, FilterTarget, FlightAnalysis, Insight, InsightSeverity, InsightSet,
  ReferenceChangeMarker, ReferenceState, RuleSet,
} from "../types/contract";

// Spec 14 §7.1 — only these trigger kinds compare the flight against the
// reference; a threshold insight (an OM limit, a CAS event) has nothing
// to do with it, so it gets no exclude action.
const REFERENCE_DRIVEN_TRIGGERS = new Set<Insight["trigger"]>(["baseline_deviation", "trend"]);
const SEVERITY_RANK: Record<InsightSeverity, number> = { limit: 0, warning: 1, watch: 2, info: 3 };
const client = getEngineClient();

function refsMatch(a: Annotation["ref"], b: Annotation["ref"]): boolean {
  if (a.kind !== b.kind) return false;
  if (a.kind === "insight" && b.kind === "insight") return a.insight_id === b.insight_id;
  if (a.kind !== "insight" && b.kind !== "insight") return a.ref === b.ref;
  return false;
}

// Spec 03 v0.16 §5.2 — Flight view. Layout, top to bottom: header (date,
// facts row, reference state, change markers); insight list (left) and the
// main column — timeline, Events, topic cards. The rule editor is a side
// panel over all of it (Spec 14 v0.9 §7.3). A log the loader skipped is
// not a flight and is not shown here (Log preview, §5.9).
export function FlightView() {
  const { flightId } = useParams();
  const navigate = useNavigate();

  const [flightAnalysis, setFlightAnalysis] = useState<FlightAnalysis>(fixtureFlight);
  const [insightSet, setInsightSet] = useState<InsightSet>(fixtureInsights);
  const [filename, setFilename] = useState(sourceFilename(fixtureFlight.source_keys[0]));
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(false);
  // First load only: the sample flight must not flash before the real one.
  const [loaded, setLoaded] = useState(false);
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  // Spec 14 §7.1 — reference contribution and open change markers.
  const [referenceState, setReferenceState] = useState<ReferenceState | null>(null);
  const [referenceChanges, setReferenceChanges] = useState<ReferenceChangeMarker[]>([]);
  const [excludeDialogFor, setExcludeDialogFor] = useState<string | null>(null); // insight id, or "header"
  const [includeDialogOpen, setIncludeDialogOpen] = useState(false);
  const [excludeBusy, setExcludeBusy] = useState(false);
  const [unitsSystem, setUnitsSystem] = useState<"imperial" | "metric">("imperial");
  const [resolvedRules, setResolvedRules] = useState<RuleSet | null>(null);
  const [shippedRules, setShippedRules] = useState<RuleSet | null>(null);
  // filter_id -> its band in words ("up to +1.5 psi"), for the Events
  // section's collapsed "within your filter" lines.
  const [filterSummaryById, setFilterSummaryById] = useState<Record<string, string>>({});
  // Insight list phase filter (null = every phase), persisted globally.
  const [phaseFilter, setPhaseFilter] = useState<string[] | null>(null);
  // The event a clicked insight or Events row points at — its row and
  // chart marker are emphasised.
  const [activeEventId, setActiveEventId] = useState<string | null>(null);

  const tl = useTimeline({ phases: flightAnalysis.phases, usingFixture });

  useEffect(() => {
    let cancelled = false;
    const carried = tl.beginFlight();
    setActiveEventId(null);

    async function load() {
      if (!flightId) {
        // No id in the URL: send to a real flight if one exists, otherwise
        // stay on the bundled sample.
        try {
          const flights = await client.listFlights();
          if (!cancelled && flights.length > 0) {
            navigate(`/flights/${flights[0].flight_id}`, { replace: true });
            return;
          }
        } catch {
          // server unreachable — the fixture is already the current state
        }
        if (!cancelled) setUsingFixture(true);
        return;
      }
      setLoading(true);
      try {
        const [got, registryResult, presetsResult, appSettings, rulesResult] = await Promise.all([
          client.getFlight(flightId),
          client.getChannelRegistry(),
          client.getChartPresets(),
          client.getAppSettings(),
          client.getWorkspaceRules(),
        ]);
        if (cancelled) return;
        setFlightAnalysis(got.flight_analysis);
        setInsightSet(got.insight_set);
        setReferenceState(got.reference_state);
        setReferenceChanges(got.reference_changes);
        setResolvedRules(rulesResult.rules);
        setShippedRules(rulesResult.shipped_rules);
        // A raw content-hash source_key is not a filename — say so plainly.
        setFilename(got.source_filename ?? "unknown source file");
        setUsingFixture(false);
        setPhaseFilter(appSettings.flight_chart?.phase_filter ?? null);
        setUnitsSystem(appSettings.units ?? "imperial");
        void loadFilterSummaries();
        await tl.setupLive({
          key: flightId,
          fetch: (ids) => client.getFlightSeries(flightId, ids),
          registry: registryResult,
          presets: presetsResult.presets,
          appSettings,
          carried,
          isCancelled: () => cancelled,
        });
        try {
          const annRes = await client.listAnnotations(flightId);
          if (!cancelled) setAnnotations(annRes.annotations);
        } catch {
          if (!cancelled) setAnnotations([]);
        }
      } catch {
        if (!cancelled) {
          // No live server, or this id doesn't exist there — a fixture
          // flight matching the id wins over the generic KACV default.
          const known = fixtureFlightById(flightId);
          const fa = known?.analysis ?? fixtureFlight;
          setFlightAnalysis(fa);
          setInsightSet(known?.insightSet ?? fixtureInsights);
          setFilename(sourceFilename(fa.source_keys[0]));
          setAnnotations([]);
          setUsingFixture(true);
          tl.setupFixture(flightId, known ? known.series : kacvSeries, carried);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setLoaded(true);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flightId, navigate]);

  async function loadFilterSummaries() {
    try {
      const res = await client.listFilters();
      setFilterSummaryById(Object.fromEntries(res.filters.map((e) => [e.filter.id, e.summary])));
    } catch {
      setFilterSummaryById({});
    }
  }

  async function refreshAnnotations() {
    if (!flightId || usingFixture) return;
    try {
      setAnnotations((await client.listAnnotations(flightId)).annotations);
    } catch {
      // keep what's loaded
    }
  }

  async function handleSaveNote(ref: Annotation["ref"], text: string) {
    if (!flightId) return;
    const existing = annotations.find((a) => refsMatch(a.ref, ref));
    try {
      await client.saveAnnotation({ id: existing?.id, flightId, ref, note: text });
      await refreshAnnotations();
    } catch {
      // server unreachable — nothing persisted
    }
  }

  async function handleDeleteNote(annotationId: string) {
    try {
      await client.deleteAnnotation(annotationId);
      await refreshAnnotations();
    } catch {
      // server unreachable — nothing persisted
    }
  }

  async function reloadInsights() {
    if (!flightId) return;
    try {
      const got = await client.getFlight(flightId);
      setInsightSet(got.insight_set);
      setReferenceState(got.reference_state);
      setReferenceChanges(got.reference_changes);
    } catch {
      // server unreachable — leave the current state
    }
  }

  function afterFilterSaved() {
    notifyFiltersChanged();
    void loadFilterSummaries();
    void reloadInsights();
  }

  const limitFor = (insight: Insight) =>
    insight.limit_id ? flightAnalysis.limits?.find((l) => l.id === insight.limit_id) : undefined;

  // Spec 09 §12.1: the insight card's filter action — a limit card filters
  // its limit, a CAS card its alert, the overboost threshold the profile's
  // overboost limit.
  const [filterEditorFor, setFilterEditorFor] = useState<string | null>(null);
  const filterTargetFor = (insight: Insight, topicId: string): FilterTarget | undefined => {
    if (insight.source === "cas" && insight.cas_id) return { kind: "cas", cas_id: insight.cas_id };
    const limitId = insight.limit_id ?? (topicId === "overboost_time" && insight.trigger === "threshold" ? "overboost" : undefined);
    return limitId ? { kind: "limit", limit_id: limitId } : undefined;
  };

  // ── Rule editor panel (Spec 14 v0.9 §7.3) ────────────────────────────────
  // The main column is the scroll container; its position is kept when the
  // panel opens and put back when it closes (an Apply reloads the insights
  // and can reflow the page under the panel).
  const mainRef = useRef<HTMLDivElement>(null);
  const savedScroll = useRef(0);
  const [editor, setEditor] = useState<{ topicId: string; enable: boolean } | null>(null);
  const canEditRules = (topicId: string) =>
    !usingFixture && Boolean(resolvedRules?.rules[topicId] && shippedRules) && insightSet.topics.some((t) => t.topic_id === topicId);

  function openEditor(topicId: string, opts?: { enable?: boolean }) {
    savedScroll.current = mainRef.current?.scrollTop ?? 0;
    setEditor({ topicId, enable: Boolean(opts?.enable) });
  }

  function closeEditor() {
    setEditor(null);
    const top = savedScroll.current;
    requestAnimationFrame(() => {
      if (mainRef.current) mainRef.current.scrollTop = top;
    });
  }

  // Journal's Edit on a rule entry (Spec 14 v0.10 §6.1) lands here with
  // ?edit=<topic>: open the panel for it once the rules are loaded.
  const [searchParams, setSearchParams] = useSearchParams();
  const editParam = searchParams.get("edit");
  useEffect(() => {
    if (!editParam || !canEditRules(editParam)) return;
    openEditor(editParam);
    const next = new URLSearchParams(searchParams);
    next.delete("edit");
    setSearchParams(next, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editParam, resolvedRules, shippedRules, insightSet, usingFixture]);

  function handleRuleApplied(newRules: RuleSet) {
    setResolvedRules(newRules);
    void reloadInsights();
  }

  async function handleExcludeFromReference(reason: string) {
    if (!flightId) return;
    setExcludeBusy(true);
    try {
      await client.excludeFlight(flightId, reason);
      setExcludeDialogFor(null);
      await reloadInsights();
    } catch {
      // server unreachable — dialog stays open
    } finally {
      setExcludeBusy(false);
    }
  }

  async function handleIncludeInReference() {
    if (!flightId) return;
    setExcludeBusy(true);
    try {
      await client.includeFlight(flightId);
      setIncludeDialogOpen(false);
      await reloadInsights();
    } catch {
      // server unreachable — dialog stays open
    } finally {
      setExcludeBusy(false);
    }
  }

  async function handleRevertMarker(m: ReferenceChangeMarker) {
    try {
      if (m.cause_kind === "rule_edit") {
        const res = await client.revertRuleEdit(m.cause_journal_entry_id);
        setResolvedRules(res.rules);
      } else if (m.cause_flight_id) {
        await client.includeFlight(m.cause_flight_id);
      }
      await reloadInsights();
    } catch {
      // server unreachable
    }
  }

  // ── Insights ─────────────────────────────────────────────────────────────
  const insightsById = useMemo(() => {
    const map = new Map<string, Insight>();
    for (const topic of insightSet.topics) for (const ins of topic.insights) map.set(ins.id, ins);
    return map;
  }, [insightSet]);

  const flatInsights = useMemo(() => {
    const items: { insight: Insight; topicId: string }[] = [];
    for (const topic of insightSet.topics) for (const insight of topic.insights) items.push({ insight, topicId: topic.topic_id });
    return items.sort((a, b) => SEVERITY_RANK[a.insight.severity] - SEVERITY_RANK[b.insight.severity]);
  }, [insightSet]);

  // An insight's phase(s), from whichever of its events/evidence carry a
  // time; null = nothing time-locatable (never hidden by the phase filter).
  function phasesForInsight(insight: Insight): Set<string> | null {
    const times: number[] = [];
    for (const e of insight.events ?? []) if (e.elapsed_s !== null) times.push(e.elapsed_s);
    for (const ev of insight.evidence) if (ev.kind === "series_window") times.push((ev.start_s + ev.end_s) / 2);
    if (times.length === 0) return null;
    const set = new Set<string>();
    for (const t of times) {
      const p = phaseAtTime(flightAnalysis.phases, t);
      if (p) set.add(p);
    }
    return set.size > 0 ? set : null;
  }

  // Original indices into insight.events that match the phase filter.
  function visibleEventIndices(insight: Insight): number[] | null {
    if (phaseFilter === null) return null;
    const events = insight.events ?? [];
    return events
      .map((_, i) => i)
      .filter((i) => {
        const elapsed = events[i].elapsed_s;
        if (elapsed === null) return true;
        const p = phaseAtTime(flightAnalysis.phases, elapsed);
        return p === undefined || phaseFilter.includes(p);
      });
  }

  const filteredFlatInsights = useMemo(() => {
    if (phaseFilter === null) return flatInsights;
    return flatInsights.filter(({ insight }) => {
      const phases = phasesForInsight(insight);
      return phases === null || [...phases].some((p) => phaseFilter.includes(p));
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flatInsights, phaseFilter, flightAnalysis.phases]);

  function handlePhaseFilterChange(next: string[] | null) {
    setPhaseFilter(next);
    if (usingFixture) return;
    client
      .getAppSettings()
      .then((s) => client.saveAppSettings({ ...s, flight_chart: { ...(s.flight_chart ?? {}), phase_filter: next } }))
      .catch(() => {
        // persisting the selection is a convenience
      });
  }

  const annotationByInsightId = useMemo(() => {
    const map = new Map<string, Annotation>();
    for (const a of annotations) if (a.ref.kind === "insight") map.set(a.ref.insight_id, a);
    return map;
  }, [annotations]);

  // evidenceIndex: a limit card's event row zooms to that event's own
  // window. exceedance / cas_event evidence highlights the Events row and
  // the chart marker (Spec 03 v0.16 §5.2).
  function handleEvidenceClick(insight: Insight, evidenceIndex = 0) {
    setActiveEventId(insightEventId(insight, evidenceIndex));
    for (const ev of insight.evidence.slice(evidenceIndex)) {
      if (ev.kind === "series_window") {
        tl.focusEvidence(ev, insight.message.text);
        return;
      }
      if (ev.kind === "baseline_point") {
        navigate(`/trends?metric=${ev.metric_id}&flight=${ev.flight_id}`);
        return;
      }
      if (ev.kind === "metric") {
        navigate(`/trends?metric=${ev.metric_id}&flight=${flightAnalysis.flight_id}`);
        return;
      }
      if (ev.kind === "exceedance" || ev.kind === "cas_event") {
        const row = eventRows.find((r) => r.key === ev.ref);
        if (row) openEventOnChart(row);
        return;
      }
    }
  }

  // ── Events ───────────────────────────────────────────────────────────────
  const eventRows = useMemo(() => buildEventRows(flightAnalysis, insightSet), [flightAnalysis, insightSet]);
  const markers = useMemo(
    () => eventRows
      .filter((r) => r.elapsed_s !== null)
      .map((r) => ({ id: r.key, n: r.n, x_s: r.elapsed_s as number, source: r.source, muted: r.filterState === "suppressed", active: r.key === activeEventId })),
    [eventRows, activeEventId],
  );
  const casEvents = useMemo(
    () => flightAnalysis.exceedances.filter((e): e is CasEvent => (e as CasEvent).source === "cas"),
    [flightAnalysis],
  );

  function openEventOnChart(row: EventRow) {
    setActiveEventId(row.key);
    const ev = row.insight?.evidence[row.eventIndex];
    if (ev?.kind === "series_window") tl.focusEvidence(ev, row.insight!.message.text);
    else if (row.elapsed_s !== null) tl.focusMoment(row.elapsed_s, row.duration_s);
  }

  // ── Header, help, topic cards ────────────────────────────────────────────
  const h = flightAnalysis.header;
  const durationMin = flightAnalysis.metrics.duration_min?.value;
  const durationStr = typeof durationMin === "number" ? `${Math.floor(durationMin / 60)}h ${Math.round(durationMin % 60)}m` : "—";
  const hasPhaseWarning = flightAnalysis.quality.some((q) => q.code === "PHASE_TAKEOFF_NOT_DETECTED");
  const engineProfileId = flightAnalysis.provenance.engine_profile.id;
  const topicHelpKey = `${flightAnalysis.provenance.engine_profile.hash}:${insightSet.rules_hash}`;
  const topicHelpById = useTopicHelp(topicHelpKey, usingFixture);
  const aircraftSummary = useAircraftSummary(usingFixture);
  const mixedAircraftCount = aircraftSummary ? aircraftSummary.idents.length : null;

  const cardModels = useMemo(
    () => insightSet.topics.map((t) => topicCardModel(t, {
      insightsById, markers: referenceChanges, help: topicHelpById[t.topic_id], metrics: flightAnalysis.metrics,
    })),
    [insightSet, insightsById, referenceChanges, topicHelpById, flightAnalysis.metrics],
  );
  const editorTopic = editor ? insightSet.topics.find((t) => t.topic_id === editor.topicId) : undefined;

  const badge = (text: string, dot?: string) => (
    <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 20, background: "var(--panel)", border: "1px solid var(--border)" }}>
      {dot && <div style={{ width: 6, height: 6, borderRadius: "50%", background: dot }} />}
      <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{text}</span>
    </div>
  );

  if (!loaded) {
    return (
      <NavShell>
        <div style={{ flexGrow: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ color: "var(--text-tertiary)", fontSize: 13 }}>Loading…</span>
        </div>
      </NavShell>
    );
  }

  return (
    <NavShell
      right={usingFixture ? badge("Sample flight — import your own logs to replace it") : badge(loading ? "Loading…" : "Up to date", "var(--success)")}
    >
      <div style={{ display: "flex", flexDirection: "column", width: "100%", minHeight: 0 }}>
        {/* Header */}
        <div style={{ flexShrink: 0, padding: "18px 24px 14px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>{h.date}</h1>
            <span className="mono" style={{ fontSize: 13, color: "var(--text-secondary)" }}>
              {durationStr} &middot; {h.engine_hours_start ?? "—"} engine hrs &middot; {h.airport_hint ?? "—"}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, flexWrap: "wrap" }}>
            <span className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>{filename}</span>
            {!usingFixture && referenceState && (
              referenceState.excluded ? (
                <span style={{ fontSize: 11 }}>
                  <a href="#" onClick={(e) => { e.preventDefault(); setIncludeDialogOpen(true); }} style={{ color: "var(--text-tertiary)" }} title="click to include again">
                    Excluded from reference ({referenceState.reason})
                  </a>
                  <InlineHelp id="flight.excluded_from_reference" />
                </span>
              ) : (
                <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Contributes to reference</span>
              )
            )}
          </div>
          {referenceChanges.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 10 }}>
              {referenceChanges.map((m) => (
                <div
                  key={m.id}
                  style={{
                    background: "rgba(245,165,36,0.08)", border: "1px solid rgba(245,165,36,0.3)", borderRadius: 8,
                    padding: "8px 12px", fontSize: 12, display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10,
                  }}
                >
                  <span>
                    <strong style={{ color: "var(--severity-warning)" }}>{m.cause_kind === "rule_edit" ? "Rule changed" : "Reference changed"}</strong>
                    {m.cause_kind === "rule_edit"
                      ? ` — ${m.cause_topic_id}'s rule changed (${m.reason}); this flight's verdict may have moved.`
                      : ` — a flight was excluded from the reference (${m.reason}); this flight's verdict may have moved.`}
                  </span>
                  <a href="#" onClick={(e) => { e.preventDefault(); void handleRevertMarker(m); }} style={{ fontSize: 11, flexShrink: 0 }}>Revert →</a>
                </div>
              ))}
            </div>
          )}
          <FlightFacts facts={flightFacts(flightAnalysis)} help={topicHelpById["flight_summary"]} engine={engineProfileId} units={unitsSystem} />
        </div>

        {/* Body */}
        <div style={{ flexGrow: 1, display: "flex", minHeight: 0 }}>
          {/* Insight list */}
          <div style={{ width: 376, flexShrink: 0, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{ padding: "16px 20px 10px", flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                Insights{" "}
                <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>
                  ({filteredFlatInsights.length}{phaseFilter !== null && filteredFlatInsights.length !== flatInsights.length ? ` of ${flatInsights.length}` : ""})
                </span>
              </div>
              {!usingFixture && <PhaseFilter selected={phaseFilter} onChange={handlePhaseFilterChange} />}
            </div>
            <div style={{ flexGrow: 1, overflowY: "auto", padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
              {filteredFlatInsights.map(({ insight, topicId }) => {
                const existing = annotationByInsightId.get(insight.id);
                const target = usingFixture ? undefined : filterTargetFor(insight, topicId);
                const isCas = insight.source === "cas";
                const peak = !isCas && insight.events?.length
                  ? Math.max(...insight.events.map((e) => (isCasInsightEvent(e) ? 0 : e.excess ?? 0)))
                  : null;
                return (
                  <div key={insight.id} style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                    <InsightCard
                      insight={insight}
                      topicId={topicId}
                      onClick={() => handleEvidenceClick(insight)}
                      onEventClick={(i) => handleEvidenceClick(insight, i)}
                      visibleEventIndices={visibleEventIndices(insight)}
                      unit={limitFor(insight)?.unit}
                      limitType={limitFor(insight)?.limit_type}
                      filterAction={
                        target
                          ? {
                              label: insight.filter
                                ? "Edit filter…"
                                : insight.filterable === false
                                  ? "Why can't I filter this?"
                                  : isCas ? "Filter this alert…" : "Filter this limit…",
                              onClick: () => setFilterEditorFor(filterEditorFor === insight.id ? null : insight.id),
                            }
                          : undefined
                      }
                      secondaryAction={
                        !usingFixture && REFERENCE_DRIVEN_TRIGGERS.has(insight.trigger) && !referenceState?.excluded
                          ? { label: "Exclude this flight from reference →", onClick: () => setExcludeDialogFor(insight.id) }
                          : undefined
                      }
                      editAction={canEditRules(topicId) ? { label: "Edit trigger ↓", onClick: () => openEditor(topicId) } : undefined}
                      note={existing?.note ?? insight.note}
                      notesEnabled={!usingFixture}
                      onSaveNote={(text) => handleSaveNote({ kind: "insight", insight_id: insight.id }, text)}
                      onDeleteNote={existing ? () => handleDeleteNote(existing.id) : undefined}
                    />
                    {isCas && (
                      <CasEventDetails
                        events={casEvents.filter((e) => e.cas_id === insight.cas_id)}
                        ecuRuns={flightAnalysis.ecu_runs ?? []}
                      />
                    )}
                    {target && filterEditorFor === insight.id && (
                      <FilterEditor
                        target={target}
                        flightPeak={peak}
                        createdFrom={{ flight_id: flightAnalysis.flight_id, insight_id: insight.id }}
                        onSaved={() => { setFilterEditorFor(null); afterFilterSaved(); }}
                        onCancel={() => setFilterEditorFor(null)}
                      />
                    )}
                  </div>
                );
              })}
              {flatInsights.length === 0 && (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No insights fired for this flight.</div>
              )}
              {flatInsights.length > 0 && filteredFlatInsights.length === 0 && (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                  No insights in the selected phase{phaseFilter && phaseFilter.length === 1 ? "" : "s"}.{" "}
                  <a href="#" onClick={(e) => { e.preventDefault(); handlePhaseFilterChange(null); }} style={{ color: "var(--accent)" }}>Show all phases</a>
                </div>
              )}
            </div>
          </div>

          {/* Main column */}
          <div ref={mainRef} data-testid="flight-main" style={{ flexGrow: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16, minHeight: 0, minWidth: 0 }}>
            <TimelinePanel
              tl={tl}
              phases={flightAnalysis.phases}
              availableChannels={pickableChannels(flightAnalysis.available_channels, flightAnalysis.provenance.channel_assignments)}
              startUtc={h.start_utc}
              hasPhaseWarning={hasPhaseWarning}
              markers={markers}
              emptyText="No timeline available for this flight (its source log wasn't retained by the server)."
            />

            <section id="events" style={{ flexShrink: 0, background: "var(--panel)", borderRadius: 12, padding: "14px 16px" }}>
              <h2 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 10px" }}>Events</h2>
              <EventsTable
                rows={eventRows}
                flightId={flightAnalysis.flight_id}
                activeEventId={activeEventId}
                interactive={!usingFixture}
                annotations={annotations}
                filterSummaryById={filterSummaryById}
                ecuRuns={flightAnalysis.ecu_runs ?? []}
                casEvents={casEvents}
                onOpen={openEventOnChart}
                onSaveNote={handleSaveNote}
                onDeleteNote={handleDeleteNote}
                onFilterSaved={afterFilterSaved}
              />
            </section>

            <section style={{ flexShrink: 0 }}>
              <h2 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 10px" }}>Analysis</h2>
              <TopicCards
                cards={cardModels}
                helpById={topicHelpById}
                engineId={engineProfileId}
                units={unitsSystem}
                mixedAircraftCount={mixedAircraftCount}
                historyDerived={REFERENCE_DERIVED_TOPICS}
                ruleFor={(id) => resolvedRules?.rules[id] ?? null}
                canEditRules={canEditRules}
                onEditRules={openEditor}
                onOpenInsight={(ins) => handleEvidenceClick(ins)}
                onRevertMarker={(m) => void handleRevertMarker(m)}
                onOpenFlights={() => navigate("/flights")}
              />
            </section>
          </div>
        </div>
      </div>
      {editor && editorTopic && resolvedRules && shippedRules && (
        <RuleEditorPanel
          topicId={editor.topicId}
          topic={editorTopic}
          title={topicHelpById[editor.topicId]?.title ?? editor.topicId.replace(/_/g, " ")}
          originFlightId={flightAnalysis.flight_id}
          originFlightLabel={h.date}
          resolvedRules={resolvedRules}
          shippedRules={shippedRules}
          enable={editor.enable}
          onApplied={handleRuleApplied}
          onClose={closeEditor}
          onNavigateFlight={(fid) => navigate(`/flights/${fid}`)}
        />
      )}
      {includeDialogOpen && flightId && (
        <ExcludeConfirmDialog
          mode="include"
          flightId={flightId}
          flightLabel={h.date}
          busy={excludeBusy}
          onCancel={() => setIncludeDialogOpen(false)}
          onConfirm={() => void handleIncludeInReference()}
        />
      )}
      {excludeDialogFor && flightId && (
        <ExcludeConfirmDialog
          flightId={flightId}
          flightLabel={h.date}
          busy={excludeBusy}
          onCancel={() => setExcludeDialogFor(null)}
          onConfirm={handleExcludeFromReference}
        />
      )}
    </NavShell>
  );
}
