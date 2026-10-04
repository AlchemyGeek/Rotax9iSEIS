import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChartBase } from "./EChartBase";
import type { Phase, SeriesFixture } from "../types/contract";
import { clipPhasesToWindow, phaseAtTime, phaseColor, phaseColorAlpha, phaseLabel } from "../lib/phases";
import { colors, fontMono } from "../theme/colors";

// Each channel is now downsampled independently (Spec 07 §11.2) — active
// series no longer share a point at every x, so the readout can't lean on
// ECharts' own per-series axis-trigger matching. Binary search each
// series' own [elapsed_s, pct, real] data for whichever point sits
// nearest the cursor's x instead.
function nearestPoint(data: (number | null)[][], t: number): (number | null)[] | undefined {
  let lo = 0;
  let hi = data.length - 1;
  if (hi < 0) return undefined;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if ((data[mid][0] as number) < t) lo = mid + 1;
    else hi = mid;
  }
  if (lo > 0) {
    const dPrev = Math.abs((data[lo - 1][0] as number) - t);
    const dCurr = Math.abs((data[lo][0] as number) - t);
    if (dPrev <= dCurr) return data[lo - 1];
  }
  return data[lo];
}

interface Props {
  series: SeriesFixture;
  activeChannels: string[];
  colorFor: (id: string) => string;
  phases: Phase[];
  // marker_s: a precise moment within the highlighted window, distinct
  // from start_s/end_s — those are often padded for zoom context (Spec 09
  // §12.1's series_window evidence), which for a brief event (an ENGINE
  // ECU alert can be one row) leaves the outline box mostly padding with
  // nothing marking where the event itself actually was.
  highlight?: { start_s: number; end_s: number; marker_s?: number } | null;
  zoomWindow?: [number, number] | null;
  onZoomChange?: (start: number, end: number) => void;
}

// One overlaid chart, each channel indexed to 0-100% of its own
// full-flight min/max (Spec 05 v0.2 §4) — not a shared literal-value
// axis, not stacked small multiples (both tried and superseded). Real
// values/units live in the synced-cursor tooltip, never the axis, so the
// y-axis stays honest about being an index rather than a value scale.
// The active-channel chip row / picker lives one level up (Spec 07 §8) —
// this component only draws what's already been decided active.
export function ChannelTimeline({ series, activeChannels, colorFor, phases, highlight, zoomWindow, onZoomChange }: Props) {
  // Must be memoized, not a plain .filter() — it's a dependency of the
  // option useMemo below, and an unmemoized array is a *new reference on
  // every render*. Dragging to pan fires 'dataZoom' events continuously,
  // each bubbling up through onZoom -> FlightView state -> a re-render
  // here; if `active` were unstable, that re-render would look like a
  // real dependency change, rebuild `option`, and setOption() would reset
  // the chart's zoom mid-drag — which is exactly the "doesn't
  // consistently move" symptom.
  const active = useMemo(() => activeChannels.filter((id) => series.channels[id]), [activeChannels, series]);

  const option = useMemo<EChartsOption>(() => {
    const seriesDefs = active.map((id) => {
      const ch = series.channels[id];
      const color = colorFor(id);
      const points = ch.points;
      const values = points.map((p) => p[1]).filter((v): v is number => v !== null);
      const min = values.length ? Math.min(...values) : 0;
      const max = values.length ? Math.max(...values) : 1;
      const range = max - min || 1;
      const data = points.map(([t, v]) => [t, v === null ? null : ((v - min) / range) * 100, v]);
      return { id, unit: ch.unit, color, data };
    });

    // The zoom range is baked into the option itself (start/end percentages
    // on the dataZoom component), rather than imperatively pushed via
    // dispatchAction after the fact — dispatchAction proved unreliable
    // here (targeting/timing issues that were hard to pin down), whereas
    // this goes through the same setOption() path that already renders
    // the chart correctly on every other change.
    const dataEnd = Math.max(0, ...seriesDefs.flatMap(({ data }) => (data.length ? [data[data.length - 1][0] as number] : [])));
    // An evidence window/marker can sit past a channel's last plotted
    // sample — e.g. an ENGINE ECU event right at SHUTDOWN, where RPM/oil
    // pressure have already gone to 0 or NaN and stopped being plotted a
    // few seconds earlier. The axis has to extend to cover it, or a
    // dataZoom percentage computed against dataEnd alone clips both the
    // zoom window and the marker's coordinate off the renderable domain
    // (ECharts doesn't draw a markPoint outside axis min/max).
    const axisEnd = Math.max(dataEnd, zoomWindow?.[1] ?? 0, highlight?.end_s ?? 0, highlight?.marker_s ?? 0);
    let dzStart = 0;
    let dzEnd = 100;
    if (zoomWindow && axisEnd > 0) {
      dzStart = Math.max(0, Math.min(100, (zoomWindow[0] / axisEnd) * 100));
      dzEnd = Math.max(0, Math.min(100, (zoomWindow[1] / axisEnd) * 100));
    }

    // The chart's own background tint (Spec 03 v0.7 §5.2/§6.1) — what the
    // now-removed standalone phase band used to show. Segments are built
    // from the *full* flight (same clipPhasesToWindow call the minimap's
    // base strip uses, one shared source of truth) in absolute elapsed_s,
    // not window-relative percentages; the chart's own dataZoom already
    // shows only whatever's in the current window, so there's no separate
    // "clip to visible range" step to keep in sync on every zoom/pan —
    // it's the same mechanism that already draws the data correctly.
    const phaseTintAreas = clipPhasesToWindow(phases, 0, dataEnd || 1).map((seg) => [
      { xAxis: seg.start_s, itemStyle: { color: phaseColorAlpha(seg.phase, 0.1) } },
      { xAxis: seg.end_s },
    ]);
    // Evidence-jump highlight — an outline, not a fill. A filled overlay
    // at any visible opacity sits on the same visual channel as the phase
    // tint right under it and swamps it completely (confirmed by sampling
    // actual rendered pixels: a flight's pre-start/engine-start/warmup/
    // taxi stretch read as one uniform red wash, phase unreadable, even
    // though the right colors were technically still composited in). A
    // border marks the same window without ever competing with the tint.
    //
    // marker_s (a precise moment within the window, e.g. an ENGINE ECU
    // alert) replaces the box with a single dot instead — a padded zoom
    // window drawn as a box around a one-row event reads as "something
    // happened somewhere in here," when a dot at the exact point reads as
    // "here."  Only the box OR the dot shows for one insight, never both.
    const highlightArea = highlight && highlight.marker_s === undefined
      ? [
          { xAxis: highlight.start_s, itemStyle: { color: "transparent", borderColor: "rgba(229,72,77,0.9)", borderWidth: 1.5 } },
          { xAxis: highlight.end_s },
        ]
      : null;
    const markAreaData = [...phaseTintAreas, ...(highlightArea ? [highlightArea] : [])];
    const markPointData = highlight?.marker_s !== undefined
      ? [{ coord: [highlight.marker_s, 94] }]
      : [];

    return {
      animation: false,
      grid: { left: 32, right: 24, top: 16, bottom: 40 },
      axisPointer: { type: "line", lineStyle: { color: colors.textTertiary } },
      tooltip: {
        trigger: "axis",
        backgroundColor: colors.panelControl,
        borderColor: colors.border,
        padding: 10,
        textStyle: { color: colors.textPrimary, fontSize: 11, fontFamily: fontMono },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (params: any) => {
          const list = Array.isArray(params) ? params : [params];
          if (!list.length) return "";
          const t = Number(list[0].axisValue);
          const mm = String(Math.floor(t / 60)).padStart(2, "0");
          const ss = String(Math.round(t % 60)).padStart(2, "0");
          const phase = phaseAtTime(phases, t);
          const phaseTag = phase
            ? ` <span style="color:${phaseColor(phase)};">&#9679;</span> ${phaseLabel(phase)}`
            : "";
          const lines = [`<div style="font-family:${fontMono};font-size:10px;color:${colors.textSecondary};margin-bottom:4px;">${mm}:${ss} elapsed${phaseTag}</div>`];
          for (const { unit, color, data } of seriesDefs) {
            const point = nearestPoint(data, t);
            const real = point?.[2];
            if (real === null || real === undefined) continue;
            lines.push(
              `<div style="font-family:${fontMono};font-size:11px;color:${color};">${real.toFixed(1)} ${unit}</div>`
            );
          }
          return lines.join("");
        },
      },
      dataZoom: [{ type: "inside", xAxisIndex: 0, filterMode: "none", start: dzStart, end: dzEnd }],
      xAxis: {
        type: "value",
        min: 0,
        max: axisEnd > 0 ? axisEnd : undefined,
        axisLabel: { formatter: (v: number) => `${Math.round(v / 60)}m`, color: colors.textTertiary, fontSize: 10, fontFamily: fontMono },
        axisLine: { lineStyle: { color: colors.border } },
        axisTick: { show: false },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        interval: 100,
        axisLabel: {
          formatter: (v: number) => (v === 100 ? "100%" : v === 0 ? "0%" : ""),
          color: colors.textTertiary,
          fontSize: 9,
          fontFamily: fontMono,
        },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: colors.panelControl, type: "dashed" } },
      },
      series: seriesDefs.map(({ color, data }, i) => ({
        type: "line",
        data,
        // data rows are [elapsed_s, normalized%, real value] — without an
        // explicit encode, ECharts' dimension auto-detection for a 3-column
        // dataset doesn't reliably treat column 0 as x, which silently
        // breaks dataZoom's startValue/endValue targeting.
        encode: { x: 0, y: 1 },
        showSymbol: false,
        lineStyle: { width: 1.8, color },
        color,
        markArea: i === 0 ? { silent: true, data: markAreaData } : undefined,
        markPoint: i === 0 && markPointData.length
          ? {
              silent: true,
              // Diamond, not circle — showSymbol on the line series below
              // is off (no per-point markers), but zoomed charts elsewhere
              // (Trends) do use circular points, so a different shape here
              // reads as "this is a flagged moment," not just another data
              // point that happened to get drawn bigger.
              symbol: "diamond",
              symbolSize: 12,
              // A channel line can be this same red (e.g. Oil Temp's
              // #e5484d is pixel-identical) and sit at the same normalized
              // height the marker does — a fill-only shape vanishes into
              // it. A white ring holds up regardless of what's underneath.
              itemStyle: { color: "rgba(229,72,77,0.95)", borderColor: "#fff", borderWidth: 2 },
              label: { show: false },
              data: markPointData,
            }
          : undefined,
      })),
    } as EChartsOption;
  }, [active, series, colorFor, phases, highlight, zoomWindow]);

  return (
    <div>
      <EChartBase option={option} height={260} onZoom={onZoomChange} />
      <div style={{ fontSize: 11, color: colors.textTertiary, marginTop: 8 }}>
        Each line is indexed to 0–100% of its own flight range so shapes line up — real values with units are at the cursor.
      </div>
    </div>
  );
}
