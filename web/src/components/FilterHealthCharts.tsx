import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { EChartBase } from "./EChartBase";
import { BAND_ORDER, bandColor, bandLabel } from "../lib/bands";
import { colors, fontMono, fontSans } from "../theme/colors";
import type { FilterHealth } from "../types/contract";

type Series = FilterHealth["series"];

// Y-axis tick with its unit: "12°F", "5%", "40 rpm".
function withUnit(v: number, unit: string): string {
  if (!unit) return `${v}`;
  return unit === "%" || unit.startsWith("\u00b0") ? `${v}${unit}` : `${v} ${unit}`;
}

function chartOption({
  series,
  field,
  unit,
  band,
  byWeather,
}: {
  series: Series;
  field: "peak_excess" | "block_s" | "time_above_pct";
  unit: string;
  band?: number | null;
  byWeather: boolean;
}): EChartsOption {
  const pts = series.filter((s) => s[field] !== null && s[field] !== undefined && s.engine_hours !== null);
  const ref = pts.filter((s) => s.in_reference).map((s) => s.engine_hours as number);
  // Default: grey = reference, teal = flights since, red = beyond the
  // filter. Coloured by weather, breaches keep a red ring instead.
  const pointStyle = (s: Series[number]) => {
    if (byWeather) {
      const fill = s.band ? bandColor(s.band) : colors.textTertiary;
      return s.breaches > 0 ? { color: fill, borderColor: colors.severityLimit, borderWidth: 2 } : { color: fill };
    }
    return { color: s.breaches > 0 ? colors.severityLimit : s.in_reference ? colors.textTertiary : colors.accent };
  };
  return {
    animation: false,
    grid: { left: 58, right: 12, top: 10, bottom: 26 },
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
      axisLabel: { color: colors.textTertiary, fontSize: 10, fontFamily: fontMono, formatter: (v: number) => withUnit(v, unit) },
      splitLine: { lineStyle: { color: colors.borderSubtle } },
    },
    series: [
      {
        type: "scatter",
        symbolSize: 6,
        data: pts.map((s) => ({ value: [s.engine_hours as number, s[field] as number], itemStyle: pointStyle(s) })),
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

function ChartTitle({ children }: { children: string }) {
  return <div style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)", marginBottom: 2 }}>{children}</div>;
}

function Dot({ color, ring }: { color: string; ring?: string }) {
  return (
    <span
      style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%", background: color, border: ring ? `2px solid ${ring}` : undefined, marginRight: 5, verticalAlign: "middle" }}
    />
  );
}

const WEATHER_TOGGLE_LABEL: Record<string, string> = {
  oat_band: "Colour by outside temperature",
  da_band: "Colour by density altitude",
};

// Spec 09 §12.2: a filter's two small charts over flights — how far past
// the limit each flight went (with the filter band drawn) and how much of
// it was spent past the limit. Grey: the reference flights the filter
// compares against (shaded); teal: flights since; red: beyond the filter.
// For a weather-sensitive limit, an optional colouring by weather band
// (the Trends view's stratified colours) shows why a flight that looks
// high can still be normal for its conditions.
export function FilterHealthCharts({
  health,
  unit,
  limitValue,
  stratifyKind,
}: {
  health: FilterHealth;
  unit: string;
  limitValue: number;
  stratifyKind?: string | null;
}) {
  const [byWeather, setByWeather] = useState(false);
  const isOverboost = health.limit_id === "overboost";
  const magField = isOverboost ? "block_s" : "peak_excess";
  const band = health.resolved_band?.value;
  const bands = useMemo(
    () =>
      [...new Set(health.series.map((s) => s.band).filter((b): b is string => Boolean(b)))].sort(
        (a, b) => (BAND_ORDER[a] ?? 9) - (BAND_ORDER[b] ?? 9),
      ),
    [health],
  );
  const magOption = useMemo(
    () =>
      chartOption({
        series: health.series,
        field: magField,
        unit: isOverboost ? "s" : unit,
        band: isOverboost && band !== null && band !== undefined ? limitValue + band : band,
        byWeather,
      }),
    [health, magField, isOverboost, unit, band, limitValue, byWeather],
  );
  const pctOption = useMemo(
    () => chartOption({ series: health.series, field: "time_above_pct", unit: "%", byWeather }),
    [health, byWeather],
  );
  const legendStyle: React.CSSProperties = { fontSize: 11, color: "var(--text-tertiary)", display: "flex", gap: 14, flexWrap: "wrap", alignItems: "center" };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "grid", gridTemplateColumns: isOverboost ? "1fr" : "1fr 1fr", gap: 12 }}>
        <div>
          <ChartTitle>{isOverboost ? "Longest overboost block (s)" : `How far past the limit (${unit})`}</ChartTitle>
          <EChartBase option={magOption} height={140} />
        </div>
        {!isOverboost && (
          <div>
            <ChartTitle>Time past the limit (% of engine time)</ChartTitle>
            <EChartBase option={pctOption} height={140} />
          </div>
        )}
      </div>
      <div style={legendStyle}>
        {byWeather ? (
          <>
            {bands.map((b) => (
              <span key={b}>
                <Dot color={bandColor(b)} />
                {bandLabel(b)}
              </span>
            ))}
            <span>
              <Dot color="transparent" ring={colors.severityLimit} />
              beyond your filter
            </span>
          </>
        ) : (
          <>
            <span>
              <Dot color={colors.textTertiary} />
              reference flights (shaded)
            </span>
            <span>
              <Dot color={colors.accent} />
              flights since
            </span>
            <span>
              <Dot color={colors.severityLimit} />
              beyond your filter
            </span>
          </>
        )}
        {band !== null && band !== undefined && <span style={{ color: "var(--severity-watch)" }}>- - filter band</span>}
        {stratifyKind && bands.length > 1 && (
          <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 5, cursor: "pointer" }}>
            <input type="checkbox" checked={byWeather} onChange={(e) => setByWeather(e.target.checked)} />
            {WEATHER_TOGGLE_LABEL[stratifyKind] ?? "Colour by weather"}
          </label>
        )}
      </div>
    </div>
  );
}
