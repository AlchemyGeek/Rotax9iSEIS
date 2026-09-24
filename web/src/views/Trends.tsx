import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { EChartsOption } from "echarts";
import { NavShell } from "../components/NavShell";
import { EChartBase } from "../components/EChartBase";
import { fleetAnalysis as fixtureFleet, flightAnalysis as fixtureFlight } from "../lib/fixtures";
import { getEngineClient } from "../lib/engineClient";
import { colors, fontMono, fontSans } from "../theme/colors";
import type { FleetAnalysis } from "../types/contract";

const client = getEngineClient();

const GROUPS: { label: string; metrics: string[] }[] = [
  { label: "EGT", metrics: ["egt_spread", "egt4_elevation"] },
  { label: "FUEL", metrics: ["cruise_efficiency", "cruise_fuel_flow"] },
  { label: "THERMAL", metrics: ["oil_temp_peak", "coolant_temp_peak", "oil_coolant_ratio", "climb_thermal_rate"] },
  { label: "BOOST", metrics: ["overboost_time"] },
  { label: "OTHER", metrics: ["cruise_da_ft", "takeoff_map_inhg"] },
];

function labelFor(id: string) {
  return id.replace(/_/g, " ");
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

  const metric = fleet.metrics[selected];

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
  useEffect(() => {
    setXWindow(null);
    setYWindow(null);
  }, [selected]);

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
      series: [
        {
          type: "line",
          data: [],
          markArea: {
            silent: true,
            itemStyle: { color: "rgba(79,195,176,0.10)" },
            data: [[{ yAxis: band.mean - band.std }, { yAxis: band.mean + band.std }]],
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
            data: [{ yAxis: band.mean }],
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
  }, [metric, highlightFlight, xWindow, yWindow]);

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
              .filter((id) => fleet.metrics[id])
              .map((id) => (
                <div
                  key={id}
                  onClick={() => setParams({ metric: id })}
                  style={{
                    padding: "9px 12px",
                    borderRadius: 8,
                    cursor: "pointer",
                    marginBottom: 2,
                    background: id === selected ? "var(--accent-15)" : "transparent",
                    color: id === selected ? "var(--accent)" : "var(--text-secondary)",
                    fontSize: 13,
                    fontWeight: id === selected ? 600 : 400,
                  }}
                >
                  {labelFor(id)}
                </div>
              ))}
          </div>
        ))}
      </div>

      <div style={{ flexGrow: 1, overflowY: "auto", padding: "20px 28px" }}>
        {!metric ? (
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
              <div style={{ display: "flex", gap: 18, padding: "4px 4px 0" }}>
                <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>&#9679; fleet flight</span>
                <span style={{ fontSize: 11, color: "var(--accent)" }}>&#9678; linked flight</span>
                <span style={{ fontSize: 11, color: "var(--severity-limit)" }}>&#9679; outlier</span>
                <span
                  style={{ fontSize: 11, color: "var(--accent)", cursor: highlightFlight ? "pointer" : "default" }}
                  onClick={() => highlightFlight && navigate(`/flights/${highlightFlight}`)}
                >
                  ▨ baseline band (leave-one-out, ±1&sigma;)
                </span>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0,1fr))", gap: 12, marginTop: 16 }}>
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
              <div style={{ background: "var(--panel)", borderRadius: 10, padding: "14px 16px" }}>
                <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 4 }}>Stratify by</div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>{metric.by_band?.band_kind ?? "—"}</div>
                <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2 }}>
                  {metric.by_band ? "not applied — toggle to split the band" : "no stratification for this metric"}
                </div>
              </div>
            </div>

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
