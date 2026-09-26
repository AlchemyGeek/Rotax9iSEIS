import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChartBase } from "./EChartBase";
import { colors, fontMono, fontSans } from "../theme/colors";
import { CYL_COLORS, CYL_SYMBOLS, CYLINDERS } from "../lib/cylinders";
import type { FleetAnalysis, FleetMetric } from "../types/contract";

// Spec 08 §7 — Trends → EGT → cylinder balance. One chart, two grids on a
// shared engine-hours axis: each cylinder's cruise EGT vs. the mean of the
// others (top), and which cylinder ran hottest on each flight (strip).

function usualLabel(fleet: FleetAnalysis, engineId: string): string {
  const e = fleet.cylinder_balance?.established_hot_cyl;
  if (!e || e.source === "none" || e.cyl == null) return "Usual hottest: not yet established";
  if (e.source === "learned") return `Usual hottest: Cyl ${e.cyl} (${Math.round((e.share ?? 0) * 100)}%, ${e.n} flights, learned)`;
  return `Usual hottest: Cyl ${e.cyl} (prior: ${engineId} profile — ${e.n} usable flights so far)`;
}

interface Props {
  fleet: FleetAnalysis;
  engineId: string;
  focusCyl: number | null;
  onFocus: (cyl: number | null) => void;
  highlightFlight: string | null;
  onOpenFlight: (flightId: string) => void;
}

export function CylinderBalance({ fleet, engineId, focusCyl, onFocus, highlightFlight, onOpenFlight }: Props) {
  const cb = fleet.cylinder_balance;
  const usual = cb?.established_hot_cyl.source !== "none" ? cb?.established_hot_cyl.cyl ?? null : null;
  const marginMin = cb?.margin_min_f ?? 15;
  const focus = focusCyl ?? usual;

  const byCyl = useMemo(() => {
    const out: Record<number, FleetMetric | undefined> = {};
    for (const n of CYLINDERS) out[n] = fleet.metrics[`egt${n}_deviation`];
    return out;
  }, [fleet]);

  const strip = useMemo(() => cb?.points ?? [], [cb]);
  const offPattern = useMemo(
    () =>
      new Set(
        strip.filter((p) => usual != null && p.hottest_cyl !== usual && (p.margin_f ?? 0) >= marginMin).map((p) => p.flight_id),
      ),
    [strip, usual, marginMin],
  );

  const option = useMemo<EChartsOption>(() => {
    const devSeries = CYLINDERS.filter((n) => byCyl[n]).map((n, i) => {
      const m = byCyl[n]!;
      const isFocus = focus === n;
      const pts = [...m.points].sort((a, b) => a.x - b.x);
      return {
        type: "line" as const,
        name: `Cyl ${n}`,
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: pts.map((p) => [p.x, p.value, p.flight_id, p.date]),
        showSymbol: false,
        symbolSize: 8,
        lineStyle: { width: isFocus ? 2.5 : 2, color: CYL_COLORS[n], opacity: focus == null || isFocus ? 1 : 0.55 },
        itemStyle: { color: CYL_COLORS[n] },
        emphasis: { focus: "none" as const },
        endLabel: {
          show: true,
          formatter: `Cyl ${n}`,
          color: colors.textSecondary,
          fontFamily: fontSans,
          fontSize: 11,
        },
        markArea:
          isFocus && m.baseline.mean != null && m.baseline.std != null
            ? {
                silent: true,
                itemStyle: { color: `${CYL_COLORS[n]}33` },
                data: [[{ yAxis: m.baseline.mean - m.baseline.std }, { yAxis: m.baseline.mean + m.baseline.std }]],
              }
            : undefined,
        markLine:
          i === 0
          ? {
              silent: true,
              symbol: "none",
              lineStyle: { color: colors.textTertiary, type: "solid" as const, width: 1 },
              label: { show: false },
              data: [{ yAxis: 0 }],
            }
          : undefined,
      };
    });

    // Flight picked up from an insight or the Flights table: a vertical
    // rule on both panels.
    const highlightX = strip.find((p) => p.flight_id === highlightFlight)?.x;

    // Both panels share one engine-hours extent so a flight's strip mark
    // sits directly under its line points.
    const xs = [
      ...strip.map((p) => p.x),
      ...CYLINDERS.flatMap((n) => byCyl[n]?.points.map((p) => p.x) ?? []),
    ].filter((x): x is number => x != null);
    const xMin = xs.length ? Math.floor(Math.min(...xs)) : undefined;
    const xMax = xs.length ? Math.ceil(Math.max(...xs)) : undefined;

    return {
      animation: false,
      grid: [
        { left: 56, right: 64, top: 20, height: 250 },
        { left: 56, right: 64, top: 296, height: 40 },
      ],
      dataZoom: [{ type: "inside", xAxisIndex: [0, 1], filterMode: "none" }],
      tooltip: {
        trigger: "axis",
        backgroundColor: colors.panelControl,
        borderColor: colors.border,
        textStyle: { color: colors.textPrimary, fontSize: 11, fontFamily: fontSans },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (raw: any) => {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const params: any[] = Array.isArray(raw) ? raw : [raw];
          const lines: string[] = [];
          const hot = params.find((p) => p.seriesName === "hottest cylinder")?.data;
          const first = params.find((p) => p.seriesName !== "hottest cylinder")?.data;
          const date = hot?.date ?? first?.[3];
          const hrs = hot?.value?.[0] ?? first?.[0];
          if (date) lines.push(`${date} &middot; ${hrs} hrs`);
          for (const p of params) {
            if (p.seriesName === "hottest cylinder" || !Array.isArray(p.data)) continue;
            const v = p.data[1] as number;
            lines.push(`${p.marker}${p.seriesName}: ${v > 0 ? "+" : ""}${v.toFixed(1)}°F`);
          }
          if (hot) {
            const margin = hot.margin == null ? "—" : `+${Math.round(hot.margin)}°F over next`;
            const note = hot.margin != null && hot.margin < marginMin ? " (too close to call)" : "";
            lines.push(`hottest: Cyl ${hot.hottest}, ${margin}${note}`);
            if (hot.rank) lines.push(`order ${hot.rank.join(" > ")}`);
            if (offPattern.has(hot.value[2])) lines.push(`differs from usual (Cyl ${usual})`);
          }
          return lines.join("<br/>");
        },
      },
      axisPointer: { link: [{ xAxisIndex: [0, 1] }], lineStyle: { color: colors.textTertiary } },
      xAxis: [
        {
          type: "value",
          gridIndex: 0,
          min: xMin,
          max: xMax,
          axisLabel: { show: false },
          axisLine: { lineStyle: { color: colors.border } },
          splitLine: { show: false },
        },
        {
          type: "value",
          gridIndex: 1,
          min: xMin,
          max: xMax,
          name: "engine hours →",
          nameLocation: "end",
          nameGap: 8,
          nameTextStyle: { fontSize: 10, color: colors.textTertiary, fontFamily: fontSans },
          axisLabel: { fontSize: 10, color: colors.textTertiary, fontFamily: fontMono },
          axisLine: { lineStyle: { color: colors.border } },
          splitLine: { show: false },
        },
      ],
      yAxis: [
        {
          type: "value",
          gridIndex: 0,
          name: "°F vs. other cylinders",
          nameTextStyle: { fontSize: 10, color: colors.textTertiary, fontFamily: fontSans, align: "left" },
          axisLabel: { fontSize: 10, color: colors.textTertiary, fontFamily: fontMono, formatter: (v: number) => (v > 0 ? `+${v}` : `${v}`) },
          axisLine: { show: false },
          splitLine: { lineStyle: { color: colors.panelControl } },
        },
        {
          type: "value",
          gridIndex: 1,
          min: -1,
          max: 1,
          show: true,
          name: "hottest",
          nameLocation: "middle",
          nameRotate: 0,
          nameGap: 34,
          nameTextStyle: { fontSize: 10, color: colors.textTertiary, fontFamily: fontSans },
          axisLabel: { show: false },
          axisTick: { show: false },
          axisLine: { show: false },
          splitLine: { show: false },
        },
      ],
      series: [
        ...devSeries,
        {
          type: "scatter",
          name: "hottest cylinder",
          xAxisIndex: 1,
          yAxisIndex: 1,
          symbolSize: 12,
          data: strip.map((p) => ({
            value: [p.x, 0, p.flight_id],
            hottest: p.hottest_cyl,
            margin: p.margin_f,
            rank: p.rank_order,
            date: p.date,
            symbol: CYL_SYMBOLS[p.hottest_cyl]?.echarts ?? "circle",
            itemStyle:
              p.margin_f != null && p.margin_f >= marginMin
                ? { color: CYL_COLORS[p.hottest_cyl], borderColor: offPattern.has(p.flight_id) ? colors.textPrimary : colors.panel, borderWidth: 2 }
                : { color: colors.panel, borderColor: CYL_COLORS[p.hottest_cyl], borderWidth: 2 },
          })),
        },
        ...(highlightX != null
          ? [0, 1].map((idx) => ({
              type: "line" as const,
              xAxisIndex: idx,
              yAxisIndex: idx,
              data: [],
              markLine: {
                silent: true,
                symbol: "none",
                lineStyle: { color: colors.accent, type: "dashed" as const, width: 1 },
                label: { show: false },
                data: [{ xAxis: highlightX }],
              },
            }))
          : []),
      ],
    } as EChartsOption;
  }, [byCyl, focus, strip, marginMin, highlightFlight, usual, offPattern]);

  const focusMetric = focus != null ? byCyl[focus] : undefined;

  return (
    <>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 4, gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ margin: 0, fontSize: 19, fontWeight: 700 }}>cylinder balance</h1>
        <span
          className="mono"
          style={{ fontSize: 12, color: "var(--text-secondary)", background: "var(--panel)", borderRadius: 999, padding: "4px 10px" }}
        >
          {usualLabel(fleet, engineId)}
        </span>
      </div>
      <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 18 }}>
        Each cylinder's cruise EGT minus the mean of the other three. A healthy engine draws four roughly flat, parallel lines.
      </div>

      <div style={{ background: "var(--panel)", borderRadius: 12, padding: "20px 20px 14px" }}>
        {!cb && (
          <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 8 }}>
            This fleet was built before cylinder balance existed — rebuild the fleet to see the hottest-cylinder strip.
          </div>
        )}
        <EChartBase option={option} height={360} />
        <div style={{ display: "flex", gap: 14, padding: "6px 4px 0", flexWrap: "wrap", alignItems: "center" }}>
          {CYLINDERS.filter((n) => byCyl[n]).map((n) => (
            <button
              key={n}
              onClick={() => onFocus(focus === n ? null : n)}
              title="show this cylinder's baseline band"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                fontSize: 11,
                background: focus === n ? "var(--panel-control)" : "transparent",
                border: "1px solid var(--border)",
                borderRadius: 999,
                padding: "3px 10px",
                color: "var(--text-secondary)",
                cursor: "pointer",
              }}
            >
              <span style={{ color: CYL_COLORS[n], fontSize: 12, lineHeight: 1 }}>{CYL_SYMBOLS[n].glyph}</span>
              Cyl {n}
            </button>
          ))}
          <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
            strip: filled = hottest by ≥ {marginMin}°F &middot; hollow = too close to call &middot; white ring = differs from usual
          </span>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: 12, marginTop: 16 }}>
        {CYLINDERS.filter((n) => byCyl[n]).map((n) => {
          const m = byCyl[n]!;
          const fmt = (v: number | null) => (v == null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(1)}`);
          return (
            <div
              key={n}
              onClick={() => onFocus(n)}
              style={{
                background: "var(--panel)",
                borderRadius: 10,
                padding: "12px 14px",
                borderTop: `3px solid ${CYL_COLORS[n]}`,
                cursor: "pointer",
                outline: focus === n ? "1px solid var(--border)" : undefined,
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 6 }}>Cyl {n}</div>
              <div className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>
                mean {fmt(m.baseline.mean)}°F &middot; σ {m.baseline.std ?? "—"}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2, textTransform: "capitalize" }}>
                trend: {m.trend?.direction.replace(/_/g, " ") ?? "—"}
                {m.trend?.r_squared != null ? ` (R² ${m.trend.r_squared})` : ""}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2 }}>
                {m.outliers.length} outlier flight(s) &middot; n={m.baseline.n}
              </div>
            </div>
          );
        })}
      </div>

      {offPattern.size > 0 && (
        <div style={{ background: "var(--panel)", borderRadius: 10, padding: "12px 14px", marginTop: 12, fontSize: 12, color: "var(--text-secondary)" }}>
          Hottest cylinder differed from the usual Cyl {usual} (by ≥ {marginMin}°F) on:{" "}
          {strip
            .filter((p) => offPattern.has(p.flight_id))
            .map((p, i) => (
              <span key={p.flight_id}>
                {i > 0 && ", "}
                <a
                  href="#"
                  onClick={(e) => {
                    e.preventDefault();
                    onOpenFlight(p.flight_id);
                  }}
                >
                  {p.date} (Cyl {p.hottest_cyl})
                </a>
              </span>
            ))}
        </div>
      )}

      {focusMetric && (
        <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 10 }}>
          Shaded band: Cyl {focus}'s fleet mean ± 1σ. Click a cylinder to change which band is shown.
        </div>
      )}
    </>
  );
}
