import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { MixedAircraftNotice } from "../components/MixedAircraftNotice";
import { CylinderBalance } from "../components/CylinderBalance";
import { TrendsPanelStrip, readinessText } from "../components/TrendsPanelStrip";
import { EventStrip } from "../components/EventStrip";
import { NeverExceededGroup } from "../components/NeverExceededGroup";
import { ChangeSummaryList } from "../components/ChangeSummaryList";
import { PastChanges } from "../components/PastChanges";
import { cylinderFocusFor, hasCylinderBalance } from "../lib/cylinders";
import { metricLabel, panelLabel, unitFor } from "../lib/trendsUnits";
import { computeTiers, panelHasDetailStrips } from "../lib/trendsTiers";
import { fleetAnalysis as fixtureFleet, flightAnalysis as fixtureFlight, trendsPanels as fixturePanels } from "../lib/fixtures";
import { getEngineClient } from "../lib/engineClient";
import { notifyShiftHistoryChanged } from "../lib/shiftHistoryAttention";
import type { FleetAnalysis, TrendsPanel } from "../types/contract";

const client = getEngineClient();

export function Trends() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const highlightFlight = params.get("flight");
  // Legacy evidence-link param (Spec 08 egtN_deviation links): still
  // resolves to the cylinder panel, focused on that cylinder.
  const cylFocusParam = cylinderFocusFor(params.get("metric") ?? "");

  const [fleet, setFleet] = useState<FleetAnalysis>(fixtureFleet);
  const [panels, setPanels] = useState<TrendsPanel[]>(fixturePanels);
  const [engineId, setEngineId] = useState(fixtureFlight.provenance.engine_profile.id);
  const [usingFixture, setUsingFixture] = useState(true);
  // A reachable server with a workspace that has no flights yet: an empty
  // state, never the sample data (that is only for when no server answers).
  const [emptyWorkspace, setEmptyWorkspace] = useState(false);
  const [loading, setLoading] = useState(true);
  const [pinBusy, setPinBusy] = useState<string | null>(null);
  const [deleteBusy, setDeleteBusy] = useState<string | null>(null);
  // Spec 12 §8.4/§8.3 (Session F) — per-panel "Show detail strips",
  // replacing Session C's page-level researcher toggle; loaded from
  // and saved to workspace settings (see report for app- vs.
  // workspace-settings decision), keyed by panel id.
  const [detailStrips, setDetailStrips] = useState<Record<string, boolean>>({});
  // §5.7/R10.1 (Session G) — one zoom range per panel, shared by every
  // strip inside it (so "visible" means the same thing regardless of
  // which strip the pilot actually dragged); null = unzoomed. Not
  // persisted — a zoom is a within-visit selection tool, not settings.
  const [zoomRanges, setZoomRanges] = useState<Record<string, { start: number; end: number } | null>>({});

  // `rebuild`: set_reference/clear_reference/delete_shift_event write
  // straight to the workspace's stored files but don't themselves
  // recompute the fleet — get_fleet reads the last-built cache, which
  // wouldn't yet reflect the edit. Pin/unpin/delete force a rebuild so
  // the pilot sees the effect of what they just did immediately; the
  // initial page load uses the cheap cached read.
  async function load(rebuild = false) {
    setLoading(true);
    try {
      // Sequenced, not Promise.all'd, when rebuilding: get_trends_panels
      // reads the same on-disk fleet cache rebuildFleet() just wrote, so
      // it has to run after that write lands, not race it.
      const liveFleet = rebuild ? await client.rebuildFleet() : await client.getFleet();
      const liveTrends = await client.getTrendsPanels();
      if (liveFleet.flight_ids.length === 0) {
        setFleet(liveFleet);
        setPanels([]);
        setUsingFixture(false);
        setEmptyWorkspace(true);
        return;
      }
      setEmptyWorkspace(false);
      setFleet(liveFleet);
      setPanels(liveTrends.panels);
      setUsingFixture(false);
      try {
        const firstFlight = await client.getFlight(liveFleet.flight_ids[0]);
        setEngineId(firstFlight.flight_analysis.provenance.engine_profile.id);
      } catch {
        // keep whatever engineId was already set
      }
      // Detail-strips state only needs a fresh read on the initial
      // load — a pin/unpin-triggered rebuild() shouldn't stomp on a
      // toggle flipped locally in between.
      if (!rebuild) {
        try {
          const settings = await client.getWorkspaceSettings();
          setDetailStrips(settings.trends_detail_strips ?? {});
        } catch {
          // keep whatever was already set (fixture mode: none)
        }
      }
    } catch {
      setFleet(fixtureFleet);
      setPanels(fixturePanels);
      setUsingFixture(true);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const panelRefs = useRef<Record<string, HTMLDivElement | null>>({});

  // flightIds is part of the callback's shared shape (ChangeSummaryList/
  // PastChanges also pass it) but unused here — the recent-window region
  // is already shaded from the metric's own shift data, not re-derived
  // from the clicked row's flight list.
  function openPanel(panel: string, _flightIds: string[]) {
    setExpanded((prev) => new Set(prev).add(panel));
    // Give the panel a tick to mount/expand before scrolling to it.
    setTimeout(() => panelRefs.current[panel]?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  }

  // Deep links (Spec 12 §9.4): ?panel=X[&flight=Y] opens a panel directly;
  // ?metric=X[&flight=Y] (Spec 03 §5.2's existing evidence-link shape,
  // e.g. baseline_point / FlightView.tsx) resolves to whichever panel
  // contains that metric — egtN_deviation keeps its special cylinder-
  // focus behaviour, everything else is a plain lookup against the
  // engine-built panel list, never a hand-maintained map here.
  useEffect(() => {
    const panel = params.get("panel");
    const metricParam = params.get("metric");
    if (panel) {
      openPanel(panel, []);
    } else if (cylFocusParam !== undefined && hasCylinderBalance(fleet)) {
      openPanel("cylinder_balance", []);
    } else if (metricParam) {
      const owner = panels.find((p) => p.metrics.some((m) => m.metric_id === metricParam));
      if (owner) openPanel(owner.panel, []);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fleet, panels]);

  function openFlights(flightIds: string[]) {
    navigate(`/flights?ids=${flightIds.join(",")}`);
  }

  async function pinReference(metricId: string, flightIds: string[], label?: string) {
    setPinBusy(metricId);
    try {
      await client.setReference(metricId, flightIds, label);
      notifyShiftHistoryChanged();
      await load(true);
    } finally {
      setPinBusy(null);
    }
  }

  async function unpinReference(metricId: string) {
    setPinBusy(metricId);
    try {
      await client.clearReference(metricId);
      notifyShiftHistoryChanged();
      await load(true);
    } finally {
      setPinBusy(null);
    }
  }

  async function deleteEvent(eventId: string) {
    setDeleteBusy(eventId);
    try {
      await client.deleteShiftEvent(eventId);
      notifyShiftHistoryChanged();
      await load(true);
    } finally {
      setDeleteBusy(null);
    }
  }

  async function toggleDetailStrips(panelId: string) {
    const next = { ...detailStrips, [panelId]: !detailStrips[panelId] };
    setDetailStrips(next);
    if (usingFixture) return;
    try {
      const settings = await client.getWorkspaceSettings();
      await client.saveWorkspaceSettings({ ...settings, trends_detail_strips: next });
    } catch {
      // Fixture/offline mode, or no live server — the toggle still
      // works for this session, just doesn't persist.
    }
  }

  const omMarginFraction = fleet.provenance.baseline_config.om_margin_fraction ?? 0.25;
  const takeoffMapModel = fleet.models.find((m) => m.id === "takeoff_map");

  const renderedPanels = useMemo(
    () =>
      panels.filter((p) => p.panel !== "cylinder_balance" || hasCylinderBalance(fleet)),
    [panels, fleet],
  );

  // Spec 12 §9.1 (Session F) — three tiers: qualifying, trendable
  // nothing-to-report, and never-exceeded (collapsed, not panels).
  const { tier1, tier2, tier3 } = useMemo(() => computeTiers(renderedPanels, fleet), [renderedPanels, fleet]);

  // Tier 1 panels open expanded by default ("the panel a summary row
  // links to opens expanded", §9.1) — re-derived whenever the tier 1
  // set changes, but a panel the pilot has since collapsed by hand
  // stays collapsed (expanded is otherwise user-owned state).
  useEffect(() => {
    setExpanded((prev) => {
      const next = new Set(prev);
      for (const p of tier1) next.add(p.panel);
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tier1.map((p) => p.panel).join(",")]);

  return (
    <NavShell
      right={
        <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
          {usingFixture && "sample data — "}
          {fleet.flight_ids.length} flights
          {!emptyWorkspace && (
            <>
              {" "}&middot; {engineId} &middot;{" "}
              {(fleet.provenance?.baseline_config?.membership ?? "leave_one_out").replace(/_/g, "-")} reference
            </>
          )}
          {loading && " · loading…"}
        </span>
      }
    >
      <div style={{ flexGrow: 1, overflowY: "auto", padding: "20px 28px" }}>
        <MixedAircraftNotice usingFixture={usingFixture} />
        <h1 style={{ margin: "0 0 4px", fontSize: 19, fontWeight: 700 }}>Trends</h1>
        <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 16 }}>
          What has changed recently, compared against your own history.
        </div>

        {emptyWorkspace ? (
          <div data-testid="trends-empty" style={{ background: "var(--panel)", borderRadius: 12, padding: "18px 20px", fontSize: 13, color: "var(--text-secondary)" }}>
            No flights in this workspace yet, so there is nothing to trend.{" "}
            <a href="#" onClick={(e) => { e.preventDefault(); navigate("/flights"); }}>Add logs on Flights →</a>
          </div>
        ) : (
          <>
        <ChangeSummaryList fleet={fleet} panels={panels} onOpenPanel={openPanel} onOpenFlights={openFlights} />
        <PastChanges events={fleet.shift_history} onOpenPanel={openPanel} onDelete={deleteEvent} busyId={deleteBusy} />

        <div style={{ display: "flex", flexDirection: "column", gap: 10, marginTop: 20 }}>
          {tier1.map((panel) => renderPanel(panel))}
          {tier2.map((panel) => renderPanel(panel))}
          <NeverExceededGroup
            panels={tier3}
            fleet={fleet}
            highlightFlight={highlightFlight}
            onOpenFlight={(id) => navigate(`/flights/${id}`)}
          />
        </div>
          </>
        )}
      </div>
    </NavShell>
  );

  // Tier 1/2 share one rendering path — a panel's tier only decides
  // *where* it sits in the list, not how it's drawn (§9.1: "the panel
  // a summary row links to opens expanded" is the one tier-1-specific
  // behaviour, handled by the effect above that seeds `expanded`).
  function renderPanel(panel: TrendsPanel) {
    const isOpen = expanded.has(panel.panel);
    // Spec 12 §9.3 (Session C): "a collapsed panel whose every
    // metric carries a badge... shows the panel-level summary" —
    // computed here so it's visible whether the panel is open
    // or collapsed, not just inside each strip.
    const shownMetrics = panel.metrics.filter((m) => panel.panel !== "cylinder_balance" || m.metric_id === "egt_spread");
    const badges = shownMetrics.map((m) => fleet.metrics[m.metric_id]?.readiness).filter((r): r is NonNullable<typeof r> => !!r);
    const allBadged = shownMetrics.length > 0 && badges.length === shownMetrics.length;
    const panelBadgeSummary = allBadged
      ? Array.from(new Set(badges.map((b) => readinessText(b)))).join(" · ")
      : null;
    const showDetailStripsHere = !!detailStrips[panel.panel];
    const hasDetailStrips = panelHasDetailStrips(panel, fleet);
    // §5.7/R10.1 (Session G) — shared across every strip in this panel.
    const zoomRange = zoomRanges[panel.panel] ?? null;
    const onZoomChange = (start: number, end: number) =>
      setZoomRanges((prev) => ({ ...prev, [panel.panel]: { start, end } }));
    return (
      <div key={panel.panel} ref={(el) => { panelRefs.current[panel.panel] = el; }} style={{ background: "var(--panel)", borderRadius: 14, overflow: "hidden" }}>
        <div
          onClick={() => setExpanded((prev) => {
            const next = new Set(prev);
            if (next.has(panel.panel)) next.delete(panel.panel);
            else next.add(panel.panel);
            return next;
          })}
          style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 16px", cursor: "pointer" }}
        >
          <span style={{ fontSize: 14, fontWeight: 700 }}>
            {panelLabel(panel.panel)}
            {panel.panel === "fuel" && (
              <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", border: "1px solid var(--border)", borderRadius: 999, padding: "1px 6px" }}>
                planning
              </span>
            )}
            {panel.filtered && (
              <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 600, color: "var(--accent)" }}>
                {panel.cas_id && panel.filter_max_event_s != null ? `events ≤ ${panel.filter_max_event_s} s filtered` : "filtered"}
              </span>
            )}
            {panelBadgeSummary && (
              <span style={{ marginLeft: 8, fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)", border: "1px solid var(--border)", borderRadius: 999, padding: "1px 6px" }}>
                {panelBadgeSummary}
              </span>
            )}
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {/* §8.3/§8.4 (Session F): per-panel detail-strips affordance,
                replacing the page-level researcher toggle — only where
                there's a fit or time_above_pct to actually show. */}
            {hasDetailStrips && (
              <label
                onClick={(e) => e.stopPropagation()}
                title="Shows the whole-history trend line and, for a limit panel, time-above-limit %"
                style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer", fontSize: 10, color: "var(--text-tertiary)" }}
              >
                <input type="checkbox" checked={showDetailStripsHere} onChange={() => toggleDetailStrips(panel.panel)} />
                Show detail strips
              </label>
            )}
            <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>{isOpen ? "▾" : "▸"}</span>
          </span>
        </div>
        {isOpen && (
          <div style={{ padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 10 }}>
            {panel.panel === "cylinder_balance" && (
              <CylinderBalance
                fleet={fleet}
                engineId={engineId}
                focusCyl={cylFocusParam ?? null}
                onFocus={(cyl) => setParams((prev) => {
                  const next = new URLSearchParams(prev);
                  if (cyl == null) next.delete("metric"); else next.set("metric", `egt${cyl}_deviation`);
                  return next;
                })}
                highlightFlight={highlightFlight}
                onOpenFlight={(id) => navigate(`/flights/${id}`)}
              />
            )}
            {panel.metrics
              .filter((m) => panel.panel !== "cylinder_balance" || m.metric_id === "egt_spread")
              // §8.4 (Session F): time_above_pct is out of the default
              // view, behind this panel's own detail-strips toggle.
              .filter((m) => showDetailStripsHere || !m.metric_id.endsWith("_time_above_pct"))
              .map((m, i) => {
                const metric = fleet.metrics[m.metric_id];
                if (!metric) return null;
                const shift = metric.shift;
                return (
                  <div key={m.metric_id}>
                    {/* §8.4: one event strip per panel, ahead of
                        its first metric — every sibling carries
                        the same frequency/events (Pass 3), so
                        showing it again per metric would repeat
                        it 2-3x. */}
                    {i === 0 && metric.events && metric.frequency && (
                      <EventStrip
                        events={metric.events}
                        frequency={metric.frequency}
                        verb={panel.cas_id ? "occurred" : "exceeded"}
                        highlightFlight={highlightFlight}
                        onOpenFlight={(id) => navigate(`/flights/${id}`)}
                      />
                    )}
                    {/* Spec 12 v0.10 G2: a CAS panel is the event strip
                        and its frequency header only — no magnitude. */}
                    {!panel.cas_id && (
                    <TrendsPanelStrip
                      metricId={m.metric_id}
                      metric={metric}
                      label={metricLabel(m.metric_id)}
                      // Spec 12 §11.7 (Session C): per-limit
                      // metrics (and overboost_time) now carry
                      // their real unit from the engine profile;
                      // unitFor()'s guesses are the fallback for
                      // everything else.
                      unit={metric.unit ?? unitFor(m.metric_id)}
                      omMarginFraction={omMarginFraction}
                      muted={m.metric_id.endsWith("_time_above_pct")}
                      showDetailStrips={showDetailStripsHere}
                      zoomRange={zoomRange}
                      onZoomChange={onZoomChange}
                      highlightFlight={highlightFlight}
                      onOpenFlight={(id) => navigate(`/flights/${id}`)}
                      onOpenFlights={openFlights}
                      onPinReference={shift ? (flightIds, lbl) => pinReference(m.metric_id, flightIds, lbl) : undefined}
                      onUnpinReference={shift?.reference.kind === "pinned" ? () => unpinReference(m.metric_id) : undefined}
                      onPreviewUnpin={() => client.previewClearReference(m.metric_id)}
                      pinBusy={pinBusy === m.metric_id}
                    />
                    )}
                    {panel.panel === "boost_power" && m.metric_id === "takeoff_map_residual_inhg" && takeoffMapModel && (
                      <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4 }}>
                        takeoff-MAP model: n={String(takeoffMapModel.n)} &middot; R&sup2;={String(takeoffMapModel.r_squared)}
                        {takeoffMapModel.note ? ` · ${String(takeoffMapModel.note)}` : ""}
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
        )}
      </div>
    );
  }
}
