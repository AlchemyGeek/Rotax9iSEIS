import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { EChartsOption } from "echarts";
import { NavShell } from "../components/NavShell";
import { EChartBase } from "../components/EChartBase";
import { fleetAnalysis as fixtureFleet, flightAnalysis as fixtureFlight } from "../lib/fixtures";
import { getEngineClient } from "../lib/engineClient";
import { CylinderBalance } from "../components/CylinderBalance";
import { cylinderFocusFor, hasCylinderBalance } from "../lib/cylinders";
import { colors, fontMono, fontSans } from "../theme/colors";
import type { FleetAnalysis } from "../types/contract";

const client = getEngineClient();

const GROUPS: { label: string; metrics: string[] }[] = [
  // cylinder_balance is a composite view over egt1..4_deviation (Spec 08 §7),
  // not a fleet metric of its own; egt4_elevation is its deprecated predecessor.
  { label: "EGT", metrics: ["egt_spread", "cylinder_balance"] },
  { label: "FUEL", metrics: ["cruise_efficiency", "cruise_fuel_flow"] },
  { label: "THERMAL", metrics: ["oil_temp_peak", "coolant_temp_peak", "oil_coolant_ratio", "climb_thermal_rate"] },
  { label: "BOOST", metrics: ["overboost_time"] },
  { label: "OTHER", metrics: ["cruise_da_ft", "takeoff_map_inhg"] },
];

function labelFor(id: string) {
  return id.replace(/_/g, " ");
}

// Same cool->warm gradient regardless of band_kind — cold/low both read
// as "the calm end," hot/very_high both as "the extreme end," so the
// color means the same thing whichever band_kind is actually active for
// a given metric (Spec 01 §8.4 v0.10's real band sets, never a mixed
// vocabulary the pilot has to relearn per metric).
const BAND_ORDER: Record<string, number> = { cold: 0, low: 0, mild: 1, moderate: 1, warm: 2, high: 2, hot: 3, very_high: 3 };
const BAND_PALETTE = ["#38BDF8", "#4FC3B0", "#F5A524", "#E5484D"];
function bandColor(name: string): string {
  const idx = BAND_ORDER[name];
  return idx !== undefined ? BAND_PALETTE[idx] : "#94A3B8";
}
function bandLabel(name: string): string {
  return name.replace(/_/g, " ");
}

export function Trends() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const selected = params.get("metric") ?? "egt_spread";
  const highlightFlight = params.get("flight");

  const [fleet, setFleet] = useState<FleetAnalysis>(fixtureFleet);
  const [engineId, setEngineId] = useState(fixtureFlight.provenance.engine_profile.id);
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        const liveFleet = await client.getFleet();
        if (cancelled) return;
        if (liveFleet.flight_ids.length === 0) throw new Error("empty workspace");
        setFleet(liveFleet);
        setUsingFixture(false);
        try {
          const firstFlight = await client.getFlight(liveFleet.flight_ids[0]);
          if (!cancelled) setEngineId(firstFlight.flight_analysis.provenance.engine_profile.id);
        } catch {
          // keep whatever engineId was already set
        }
      } catch {
        if (!cancelled) {
          setFleet(fixtureFleet);
          setUsingFixture(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  // egt{n}_deviation / egt4_elevation links (insight evidence, old URLs)
  // land on the cylinder balance view, focused on that cylinder.
  const cylFocusParam = cylinderFocusFor(selected);
  const showCylinderBalance = cylFocusParam !== undefined && hasCylinderBalance(fleet);
  const metric = showCylinderBalance ? undefined : fleet.metrics[selected];

  // Only the x-axis (engine hours) is wheel/pinch-zoomable. An
  // independent y-zoom, anchored wherever the cursor happens to be
  // rather than where the data actually is, kept framing empty space —
  // the y-axis instead auto-refits to whatever points are currently
  // visible on x, so "zooming in" always means "focus on the data."
  const [xWindow, setXWindow] = useState<[number, number] | null>(null);
  // Y has no independent wheel-zoom (that's the bug above), but is still
  // drag-pannable, same as x — once the user manually nudges it, that
  // wins over the auto-fit until they switch metrics.
  const [yWindow, setYWindow] = useState<[number, number] | null>(null);
  // Off by default even for a stratifiable metric (Spec 03 §5.3 v0.10) —
  // a casual pilot reads the unstratified chart first, never required to
  // understand DA/OAT banding to see it.
  const [stratified, setStratified] = useState(false);
  useEffect(() => {
    setXWindow(null);
    setYWindow(null);
    setStratified(false);
  }, [selected]);

  const showStratified = stratified && !!metric?.by_band;

  const option = useMemo<EChartsOption | null>(() => {
    if (!metric) return null;
    const outlierIds = new Set(metric.outliers.map((o) => o.flight_id));
    const band = metric.baseline;
    const points = metric.points.map((p) => [p.x, p.value, p.flight_id, p.date]);

    let yMin: number;
    let yMax: number;
    if (yWindow) {
      // User has manually panned y — that wins over the auto-fit until
      // they switch metrics (see the effect resetting yWindow above).
      [yMin, yMax] = yWindow;
    } else {
      const visiblePoints = xWindow ? points.filter((p) => (p[0] as number) >= xWindow[0] && (p[0] as number) <= xWindow[1]) : points;
      const valuesInView = (visiblePoints.length ? visiblePoints : points).map((p) => p[1] as number);
      yMin = Math.min(...valuesInView);
      yMax = Math.max(...valuesInView);
      const pad = (yMax - yMin) * 0.15 || Math.abs(yMax) * 0.1 || 1;
      yMin -= pad;
      yMax += pad;
    }
    yMin = Number(yMin.toFixed(2));
    yMax = Number(yMax.toFixed(2));

    return {
      animation: false,
      grid: { left: 56, right: 24, top: 24, bottom: 40 },
      // The current x-window is baked back into the option explicitly
      // (startValue/endValue) rather than left implicit — every pan/zoom
      // event triggers a rebuild (since y needs to refit), and setOption
      // replaces the dataZoom component wholesale; without this, each
      // rebuild would silently reset the zoom to full range, fighting
      // the user's own drag (same bug hit and fixed on the Flight view
      // timeline — see EChartBase/ChannelTimeline history).
      //
      // filterMode "none" on both: the axes' own extents stay pinned to
      // the *full* dataset regardless of either window, so there's
      // always slack outside the current view for a drag to pan into —
      // like x already has, since it never sets an explicit min/max
      // either. Without this, the y-axis's auto-scale would shrink to
      // whatever's currently in the x-window (same values the window
      // itself is drawn from), leaving no room for a vertical drag to
      // go anywhere.
      dataZoom: [
        // Explicit, stable ids — EChartBase uses these to tell which
        // axis a given dataZoom event actually moved, so an x-only wheel
        // zoom doesn't get misread as a y-pan (see EChartBase.tsx).
        { id: "dzX", type: "inside", xAxisIndex: 0, filterMode: "none", ...(xWindow ? { startValue: xWindow[0], endValue: xWindow[1] } : {}) },
        // Pan-only: no zoomOnMouseWheel, so wheel/pinch stays x-only (the
        // fix above). Dragging still moves both axes together, same as
        // grabbing and sliding the whole view.
        { id: "dzY", type: "inside", yAxisIndex: 0, filterMode: "none", zoomOnMouseWheel: false, moveOnMouseMove: true, startValue: yMin, endValue: yMax },
      ],
      tooltip: {
        trigger: "item",
        backgroundColor: colors.panelControl,
        borderColor: colors.border,
        textStyle: { color: colors.textPrimary, fontSize: 11, fontFamily: fontSans },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (p: any) => `${p.data[3]} &middot; ${p.data[1]}<br/>engine hrs ${p.data[0]}`,
      },
      xAxis: {
        type: "value",
        name: "engine hours →",
        nameLocation: "end",
        nameTextStyle: { fontSize: 10, color: colors.textTertiary, fontFamily: fontSans },
        axisLabel: { fontSize: 10, color: colors.textTertiary, fontFamily: fontMono },
        axisLine: { lineStyle: { color: colors.border } },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        // No explicit min/max — same as x, the axis auto-scales to the
        // full dataset and the dataZoom window (above) governs what's
        // actually in view. Pinning min/max here to the current window
        // used to make the axis *equal* the view, leaving a pan nowhere
        // to go (and reintroducing the unrounded-float-as-a-literal-tick
        // bug from before, since it forced that exact float as a tick).
        axisLabel: { fontSize: 10, color: colors.textTertiary, fontFamily: fontMono },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: colors.panelControl } },
      },
      series: showStratified
        ? // Stratified (Spec 03 §5.3 v0.10): re-groups the same points and
          // baseline data already fetched — no re-fetch. One baseline
          // region + one scatter per band actually present for this
          // metric (never a fixed 4), plus a neutral series for any point
          // whose own band came back empty (never hidden, just ungrouped).
          [
            ...Object.entries(metric.by_band!.bands).flatMap(([name, stats]) => {
              const c = bandColor(name);
              return [
                {
                  type: "line" as const,
                  data: [],
                  markArea: {
                    silent: true,
                    itemStyle: { color: `${c}1A` },
                    data:
                      stats.mean != null && stats.std != null
                        ? [[{ yAxis: stats.mean - stats.std }, { yAxis: stats.mean + stats.std }]]
                        : [],
                  },
                  markLine: {
                    silent: true,
                    symbol: "none",
                    lineStyle: { color: c, type: "dashed", opacity: 0.7 },
                    label: { show: false },
                    data: stats.mean != null ? [{ yAxis: stats.mean }] : [],
                  },
                },
                {
                  type: "scatter" as const,
                  name: bandLabel(name),
                  symbolSize: (val: [number, number, string]) => {
                    if (val[2] === highlightFlight) return 14;
                    return outlierIds.has(val[2]) ? 9 : 7;
                  },
                  data: metric.points.filter((p) => p.band === name).map((p) => [p.x, p.value, p.flight_id, p.date]),
                  itemStyle: {
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    color: (p: any) => {
                      if (p.data[2] === highlightFlight) return colors.accent;
                      return outlierIds.has(p.data[2]) ? colors.severityLimit : c;
                    },
                  },
                },
              ];
            }),
            {
              type: "scatter",
              name: "unbanded",
              symbolSize: (val: [number, number, string]) => (outlierIds.has(val[2]) ? 9 : 7),
              data: metric.points.filter((p) => !p.band).map((p) => [p.x, p.value, p.flight_id, p.date]),
              itemStyle: {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                color: (p: any) => (outlierIds.has(p.data[2]) ? colors.severityLimit : colors.textTertiary),
                opacity: 0.5,
              },
            },
          ]
        : [
            {
              type: "line",
              data: [],
              markArea: {
                silent: true,
                itemStyle: { color: "rgba(79,195,176,0.10)" },
                data: band.mean != null && band.std != null ? [[{ yAxis: band.mean - band.std }, { yAxis: band.mean + band.std }]] : [],
              },
              markLine: {
                silent: true,
                symbol: "none",
                lineStyle: { color: colors.accent, type: "dashed", opacity: 0.6 },
                label: {
                  formatter: "{c}",
                  color: colors.accent,
                  fontFamily: fontMono,
                  fontSize: 11,
                  fontWeight: 600,
                  backgroundColor: colors.panelControl,
                  padding: [3, 6],
                  borderRadius: 4,
                },
                data: band.mean != null ? [{ yAxis: band.mean }] : [],
              },
            },
            {
              type: "scatter",
              symbolSize: (val: [number, number, string]) => {
                if (val[2] === highlightFlight) return 14;
                return outlierIds.has(val[2]) ? 9 : 7;
              },
              data: points,
              itemStyle: {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                color: (p: any) => {
                  if (p.data[2] === highlightFlight) return colors.accent;
                  return outlierIds.has(p.data[2]) ? colors.severityLimit : colors.textSecondary;
                },
              },
            },
          ],
    } as EChartsOption;
  }, [metric, highlightFlight, xWindow, yWindow, showStratified]);

  const model = fleet.models.find((m) => m.id === "takeoff_map" && selected === "takeoff_map_inhg");

  return (
    <NavShell
      right={
        <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
          {usingFixture && "sample data — "}
          {fleet.flight_ids.length} flights &middot; {engineId} &middot;{" "}
          {fleet.provenance.baseline_config.membership.replace(/_/g, "-")} baseline
          {loading && " · loading…"}
        </span>
      }
    >
      <div style={{ width: 280, flexShrink: 0, borderRight: "1px solid var(--border)", overflowY: "auto", padding: "18px 14px" }}>
        {GROUPS.map((g) => (
          <div key={g.label} style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", padding: "0 8px 8px" }}>
              {g.label}
            </div>
            {g.metrics
              .filter((id) => (id === "cylinder_balance" ? hasCylinderBalance(fleet) : fleet.metrics[id]))
              .map((id) => {
                const active = id === selected || (id === "cylinder_balance" && showCylinderBalance);
                return (
                <div
                  key={id}
                  onClick={() => setParams({ metric: id })}
                  style={{
                    padding: "9px 12px",
                    borderRadius: 8,
                    cursor: "pointer",
                    marginBottom: 2,
                    background: active ? "var(--accent-15)" : "transparent",
                    color: active ? "var(--accent)" : "var(--text-secondary)",
                    fontSize: 13,
                    fontWeight: active ? 600 : 400,
                  }}
                >
                  {labelFor(id)}
                </div>
                );
              })}
          </div>
        ))}
      </div>

      <div style={{ flexGrow: 1, overflowY: "auto", padding: "20px 28px" }}>
        {showCylinderBalance ? (
          <CylinderBalance
            fleet={fleet}
            engineId={engineId}
            focusCyl={cylFocusParam ?? null}
            onFocus={(cyl) => {
              const next: Record<string, string> = { metric: cyl == null ? "cylinder_balance" : `egt${cyl}_deviation` };
              if (highlightFlight) next.flight = highlightFlight;
              setParams(next);
            }}
            highlightFlight={highlightFlight}
            onOpenFlight={(id) => navigate(`/flights/${id}`)}
          />
        ) : !metric ? (
          <div style={{ color: "var(--text-tertiary)" }}>No fleet data for this metric.</div>
        ) : (
          <>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4 }}>
              <h1 style={{ margin: 0, fontSize: 19, fontWeight: 700 }}>{labelFor(selected)}</h1>
              <span className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                n=
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    const ids = metric.points.map((p) => p.flight_id).join(",");
                    navigate(`/flights?ids=${ids}`);
                  }}
                  title="the flights this baseline is built on"
                >
                  {metric.baseline.n}
                </a>
                {" "}&middot; mean {metric.baseline.mean} &middot; std {metric.baseline.std} &middot; confidence:{" "}
                {metric.baseline.confidence.level}
              </span>
            </div>
            <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 18 }}>
              Baseline band is leave-one-out — each flight is compared to the fleet excluding itself.
            </div>

            <div style={{ background: "var(--panel)", borderRadius: 12, padding: "24px 20px 16px" }}>
              {option && (
                <EChartBase
                  option={option}
                  height={380}
                  onZoom={(s, e) => setXWindow([s, e])}
                  onZoomY={(s, e) => setYWindow([s, e])}
                />
              )}
              <div style={{ display: "flex", gap: 18, padding: "4px 4px 0", flexWrap: "wrap" }}>
                {showStratified && metric.by_band ? (
                  <>
                    {Object.keys(metric.by_band.bands).map((name) => (
                      <span key={name} style={{ fontSize: 11, color: bandColor(name) }}>
                        &#9679; {bandLabel(name)}
                      </span>
                    ))}
                    <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>&#9679; unbanded</span>
                    <span style={{ fontSize: 11, color: "var(--severity-limit)" }}>&#9679; outlier</span>
                  </>
                ) : (
                  <>
                    <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>&#9679; fleet flight</span>
                    <span style={{ fontSize: 11, color: "var(--accent)" }}>&#9678; linked flight</span>
                    <span style={{ fontSize: 11, color: "var(--severity-limit)" }}>&#9679; outlier</span>
                    <span
                      style={{ fontSize: 11, color: "var(--accent)", cursor: highlightFlight ? "pointer" : "default" }}
                      onClick={() => highlightFlight && navigate(`/flights/${highlightFlight}`)}
                    >
                      ▨ baseline band (leave-one-out, ±1&sigma;)
                    </span>
                  </>
                )}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: metric.by_band ? "repeat(3, minmax(0,1fr))" : "repeat(2, minmax(0,1fr))", gap: 12, marginTop: 16 }}>
              <div style={{ background: "var(--panel)", borderRadius: 10, padding: "14px 16px" }}>
                <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 4 }}>Trend</div>
                {metric.trend ? (
                  <>
                    <div style={{ fontSize: 14, fontWeight: 600, textTransform: "capitalize" }}>{metric.trend.direction}</div>
                    <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
                      slope {metric.trend.slope} &middot; R&sup2; {metric.trend.r_squared} &middot; confidence: {metric.trend.confidence.level}
                    </div>
                  </>
                ) : (
                  <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>Not enough data yet.</div>
                )}
              </div>
              <div style={{ background: "var(--panel)", borderRadius: 10, padding: "14px 16px" }}>
                <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 4 }}>Outliers this fleet</div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{metric.outliers.length} flight(s)</div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>cross the z-score threshold</div>
              </div>
              {/* Spec 03 §5.3 v0.10: hidden entirely (not grayed out) when
                  this metric has no band_kind at all — nothing to offer,
                  not a disabled control. */}
              {metric.by_band && (
                <div style={{ background: "var(--panel)", borderRadius: 10, padding: "14px 16px" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                    <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Stratify by {bandLabel(metric.by_band.band_kind)}</span>
                    <input
                      type="checkbox"
                      checked={stratified}
                      onChange={(e) => setStratified(e.target.checked)}
                      title={`split the baseline into its ${Object.keys(metric.by_band.bands).length} band(s)`}
                    />
                  </div>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>{stratified ? "on" : "off"}</div>
                  <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
                    {stratified
                      ? `${Object.keys(metric.by_band.bands).length} band(s) shown below`
                      : "single fleet-wide baseline shown"}
                  </div>
                </div>
              )}
            </div>

            {showStratified && metric.by_band && (
              <div style={{ marginTop: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: `repeat(${Math.min(Object.keys(metric.by_band.bands).length, 4)}, minmax(0,1fr))`, gap: 12 }}>
                  {Object.entries(metric.by_band.bands).map(([name, stats]) => (
                    <div key={name} style={{ background: "var(--panel)", borderRadius: 10, padding: "12px 14px", borderTop: `3px solid ${bandColor(name)}` }}>
                      <div style={{ fontSize: 12, fontWeight: 600, textTransform: "capitalize", marginBottom: 6 }}>{bandLabel(name)}</div>
                      <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                        n={stats.n} &middot; mean {stats.mean ?? "—"} &middot; std {stats.std ?? "—"}
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2 }}>confidence: {stats.confidence.level}</div>
                      {stats.trend && (
                        <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4, textTransform: "capitalize" }}>
                          trend: {stats.trend.direction}
                          {stats.trend.slope != null ? ` (R² ${stats.trend.r_squared})` : ""}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {model && (
              <div style={{ background: "var(--panel)", borderRadius: 10, padding: "14px 16px", marginTop: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Model: {model.id}</div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                  n={String(model.n)} &middot; R&sup2;={String(model.r_squared)}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </NavShell>
  );
}
