import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChartBase } from "./EChartBase";
import { bandColor, bandLabel } from "../lib/bands";
import { colors, fontMono, fontSans } from "../theme/colors";
import type { FilterHealth } from "../types/contract";

type Series = FilterHealth["series"];

function chartOption({
  series,
  field,
  unit,
  band,
  stratified,
}: {
  series: Series;
  field: "peak_excess" | "block_s" | "time_above_pct";
  unit: string;
  band?: number | null;
  stratified: boolean;
}): EChartsOption {
  const pts = series.filter((s) => s[field] !== null && s[field] !== undefined && s.engine_hours !== null);
  const ref = pts.filter((s) => s.in_reference).map((s) => s.engine_hours as number);
  const pointColor = (s: Series[number]) =>
    s.breaches > 0 ? colors.severityLimit : stratified && s.band ? bandColor(s.band) : s.in_reference ? colors.textTertiary : colors.accent;
  return {
    animation: false,
    grid: { left: 44, right: 12, top: 10, bottom: 26 },
    tooltip: {
      trigger: "item",
      backgroundColor: colors.panelControl,
      borderColor: colors.border,
      textStyle: { color: colors.textPrimary, fontSize: 11, fontFamily: fontMono },
      formatter: (p: unknown) => {
        const s = pts[(p as { dataIndex: number }).dataIndex];
        if (!s) return "";
        const v = s[field] as number;
        return [
          `${s.date ?? ""} · ${s.engine_hours?.toFixed(1)} h`,
          `${v.toFixed(field === "time_above_pct" ? 1 : 2)} ${unit}`,
          s.band ? `band: ${bandLabel(s.band)}` : "",
          s.in_reference ? "reference flight" : "",
          s.breaches ? `${s.breaches} beyond the filter` : s.events ? `${s.events} event(s), all within the filter` : "",
        ].filter(Boolean).join("<br/>");
      },
    },
    xAxis: {
      type: "value",
      scale: true,
      axisLabel: { color: colors.textTertiary, fontSize: 10, fontFamily: fontMono, formatter: (v: number) => `${v.toFixed(0)}h` },
      axisLine: { lineStyle: { color: colors.border } },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      scale: false,
      axisLabel: { color: colors.textTertiary, fontSize: 10, fontFamily: fontMono },
      splitLine: { lineStyle: { color: colors.borderSubtle } },
    },
    series: [
      {
        type: "scatter",
        symbolSize: 6,
        data: pts.map((s) => ({ value: [s.engine_hours as number, s[field] as number], itemStyle: { color: pointColor(s) } })),
        markArea: ref.length
          ? { silent: true, itemStyle: { color: "rgba(174,183,191,0.08)" }, data: [[{ xAxis: Math.min(...ref) - 0.5 }, { xAxis: Math.max(...ref) + 0.5 }]] }
          : undefined,
        markLine:
          band !== undefined && band !== null
            ? {
                silent: true,
                symbol: "none",
                lineStyle: { color: colors.severityWatch, type: "dashed" },
                label: { formatter: "filter band", position: "insideEndTop", color: colors.severityWatch, fontSize: 10, fontFamily: fontSans },
                data: [{ yAxis: band }],
              }
            : undefined,
      },
    ],
  };
}

// Spec 09 §12.2: a filter's two small charts over flights — the limit's
// excess (with the band drawn) and its time past the limit — reference
// flights shaded, breaching flights in red, stratified limits coloured by
// weather band (the Trends view's stratified colours).
function ChartTitle({ children }: { children: string }) {
  return <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 2 }}>{children}</div>;
}

export function FilterHealthCharts({
  health,
  unit,
  limitValue,
  stratified,
}: {
  health: FilterHealth;
  unit: string;
  limitValue: number;
  stratified: boolean;
}) {
  const isOverboost = health.limit_id === "overboost";
  const magField = isOverboost ? "block_s" : "peak_excess";
  const band = health.resolved_band?.value;
  const magOption = useMemo(
    () =>
      chartOption({
        series: health.series,
        field: magField,
        unit: isOverboost ? "s" : unit,
        band: isOverboost && band !== null && band !== undefined ? limitValue + band : band,
        stratified,
      }),
    [health, magField, isOverboost, unit, band, limitValue, stratified],
  );
  const pctOption = useMemo(
    () => chartOption({ series: health.series, field: "time_above_pct", unit: "%", stratified }),
    [health, stratified],
  );
  return (
    <div style={{ display: "grid", gridTemplateColumns: isOverboost ? "1fr" : "1fr 1fr", gap: 12 }}>
      <div>
        <ChartTitle>{isOverboost ? "Longest overboost block (s)" : `Peak excess (${unit})`}</ChartTitle>
        <EChartBase option={magOption} height={140} />
      </div>
      {!isOverboost && (
        <div>
          <ChartTitle>Time past the limit (% of engine time)</ChartTitle>
          <EChartBase option={pctOption} height={140} />
        </div>
      )}
    </div>
  );
}
