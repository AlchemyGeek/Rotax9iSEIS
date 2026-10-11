import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { EChartBase } from "./EChartBase";
import { PinConfirmDialog, UnpinConfirmDialog, SMALL_BASELINE_THRESHOLD } from "./PinDialogs";
import type { Selection } from "./PinDialogs";
import { bandColor, bandLabel } from "../lib/bands";
import { colors, fontMono, fontSans } from "../theme/colors";
import type { FleetMetric, Readiness, UnpinPreview } from "../types/contract";

// Spec 12 §9.3 (Session C) — the fixed badge text, keyed by the
// engine's own `readiness.kind`; the one place this copy lives, so
// every caller (this strip, ChangeSummaryList, the collapsed panel
// list, Baselines & Models) renders identical wording.
export function readinessText(r: Readiness): string {
  switch (r.kind) {
    case "filtered": return "filtered";
    case "building": return `building reference · ${r.count ?? 0} more flight${r.count === 1 ? "" : "s"}`;
    case "no_recent": return "too few flights";
    case "no_events": return "never exceeded";
    case "rare": return `${r.count ?? 0} exceedance${r.count === 1 ? "" : "s"}`;
    case "insufficient": return "conditions not comparable yet";
    case "pinned": return `reference pinned · ${r.label ?? "pinned reference"}`;
    default: return r.kind;
  }
}

// Spec 12 §8.3 — the one chart shape every Trends panel strip shares:
// points linked to Flight view with outlier rings; the reference region
// (±1σ band, shaded, span-bounded) with its mean extended as a dashed
// line across the recent window; the recent window shaded differently;
// the OM limit and filter-band-edge lines where they exist; the OM
// margin line (dashed, fainter, labelled with the fraction); a stratify
// toggle; "Pin reference to these flights"/"Unpin reference". Generalizes
// FilterHealthCharts.tsx's reference-shading approach (Spec 09 §12.2)
// to every fleet metric, not just filtered limits.

function withUnit(v: number, unit: string): string {
  if (!unit) return `${v}`;
  return unit === "%" || unit.startsWith("°") ? `${v}${unit}` : `${v} ${unit}`;
}

const RECENT_WINDOW_FILL = "rgba(79,195,176,0.07)";
const REFERENCE_FILL = "rgba(174,183,191,0.10)";
// Spec 12 §5.7.1 item 1 (v0.9, Session G — R10.4): one "not used" fill
// for every eligible flight outside the pinned reference, on either
// side — older than it, or between it and the recent window once the
// window has moved past (D-1, retained). Session E/F's separate "gap"
// style is retired; both cases read the same now.
const NOT_USED_FILL = "rgba(174,183,191,0.015)";

// "reference pinned · 40 flights · 12 Oct" (item 1's own example) — the
// pin marker's date, short like the rest of this chart's axis labels;
// client-side formatting of Shift.reference.set_at, same precedent as
// PastChanges.tsx's own date slicing.
function formatPinDate(setAt: string): string {
  const d = new Date(setAt);
  if (Number.isNaN(d.getTime())) return setAt.slice(0, 10);
  // timeZone: "UTC" — set_at is a calendar date (Spec 12 §5.7.1), not a
  // precise instant; formatting in the browser's local zone could shift
  // it a day either way near midnight UTC.
  return d.toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
}

interface Props {
  metricId: string;
  metric: FleetMetric;
  label: string;
  unit?: string;
  omMarginFraction: number;
  // §8.4 (Session C): time_above_pct's strip, behind the researcher
  // toggle, rendered dimmer than the default view.
  muted?: boolean;
  highlightFlight: string | null;
  onOpenFlight: (flightId: string) => void;
  onOpenFlights: (flightIds: string[]) => void;
  // §5.7.1 items 2/5 (Session D, selection reworked Session G): both
  // actions fire only from their confirmation dialog — onPinReference
  // now takes whichever flight_ids the dialog's chosen selection
  // resolved to (zoomed-in-view, or the recent-window alternative),
  // not a fixed closure-captured list; onPreviewUnpin fetches the
  // engine's prediction for the unpin dialog.
  onPinReference?: (flightIds: string[], label?: string) => void;
  onUnpinReference?: () => void;
  onPreviewUnpin?: () => Promise<UnpinPreview>;
  pinBusy?: boolean;
  // §8.3/§8.4 (Session F) — the whole-history fit line, drawn only
  // when the panel's own "Show detail strips" affordance is on
  // (Trends.tsx owns that state and the checkbox; this is just the
  // gate for whether to draw it on this one strip).
  showDetailStrips?: boolean;
  // §5.7 (v0.8/v0.9, Session G — R10.1): the strip's current zoomed
  // x-range, shared across every strip in the same panel (Trends.tsx
  // owns the state, keyed by panel id) so "visible" means the same
  // thing on every strip a pilot could pin from. null = unzoomed
  // (the full history is in view).
  zoomRange?: { start: number; end: number } | null;
  onZoomChange?: (start: number, end: number) => void;
}

export function TrendsPanelStrip({
  metricId: _metricId,
  metric,
  label,
  unit = "",
  omMarginFraction,
  muted,
  highlightFlight,
  onOpenFlight,
  onOpenFlights,
  onPinReference,
  onUnpinReference,
  onPreviewUnpin,
  pinBusy,
  showDetailStrips,
  zoomRange,
  onZoomChange,
}: Props) {
  const [stratified, setStratified] = useState(false);
  const [dialog, setDialog] = useState<"pin" | "unpin" | null>(null);
  const [unpinPreview, setUnpinPreview] = useState<UnpinPreview | null>(null);
  const shift = metric.shift;
  const bandKind = metric.by_band?.band_kind;
  const showStratified = stratified && !!metric.by_band;

  const outlierIds = useMemo(() => {
    const source = showStratified && metric.by_band
      ? Object.values(metric.by_band.bands).flatMap((s) => s.outliers ?? [])
      : metric.outliers;
    return new Set(source.map((o) => o.flight_id));
  }, [metric, showStratified]);

  const option = useMemo<EChartsOption>(() => {
    const points = metric.points.map((p) => [p.x, p.value, p.flight_id, p.date]);
    const level = shift?.level;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const markAreas: any[] = [];
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const markLines: any[] = [];

    if (shift) {
      const ref = shift.reference;
      const recent = shift.recent;
      // Recent window: shaded full-height, distinct from the reference tint.
      markAreas.push({
        silent: true,
        itemStyle: { color: RECENT_WINDOW_FILL },
        data: [[{ xAxis: recent.hours_from }, { xAxis: recent.hours_to }]],
      });
      const pinned = ref.kind === "pinned";
      if (ref.hours_from != null && ref.hours_to != null) {
        // Reference span: shaded ±1σ band, bounded to the reference's own
        // x-extent (not drawn under the recent window or before it).
        // Pinned (§5.7.1 item 1): fixed, hard edges — a solid border, so
        // the region visibly doesn't move with the rest of the fleet,
        // unlike a rolling reference's plain, borderless fill.
        if (ref.mean != null && ref.std != null) {
          markAreas.push({
            silent: true,
            itemStyle: pinned
              ? { color: REFERENCE_FILL, borderColor: colors.accent, borderWidth: 1.5, borderType: "solid" }
              : { color: REFERENCE_FILL },
            data: [[
              { xAxis: ref.hours_from, yAxis: ref.mean - ref.std },
              { xAxis: ref.hours_to, yAxis: ref.mean + ref.std },
            ]],
          });
        }
        // The reference mean, dashed, extended across the recent window
        // too — so the eye sees exactly what the shift statistic compared.
        if (ref.mean != null) {
          markLines.push({
            silent: true, symbol: "none",
            lineStyle: { color: colors.accent, type: "dashed", opacity: 0.7 },
            label: { show: false },
            data: [[{ coord: [ref.hours_from, ref.mean] }, { coord: [recent.hours_to, ref.mean] }]],
          });
        }
        if (pinned) {
          // Not used (R10.4, v0.9): one fill for every eligible flight
          // outside the pinned span, on either side — older than it,
          // or between it and the recent window once the window has
          // moved past (D-1, retained; only drawn when that gap is
          // actually positive in hours — a pin ending right where the
          // window begins has nothing to shade there).
          const eligibleXs = metric.points.map((p) => p.x).filter((x): x is number => x != null);
          const earliestX = Math.min(...eligibleXs);
          if (Number.isFinite(earliestX) && earliestX < ref.hours_from) {
            markAreas.push({
              silent: true,
              itemStyle: { color: NOT_USED_FILL },
              data: [[{ xAxis: earliestX }, { xAxis: ref.hours_from }]],
            });
          }
          if (recent.hours_from > ref.hours_to) {
            markAreas.push({
              silent: true,
              itemStyle: { color: NOT_USED_FILL },
              data: [[{ xAxis: ref.hours_to }, { xAxis: recent.hours_from }]],
            });
          }
          // The pin marker, at the reference's right boundary — n,
          // hours span and the label/date (item 1's own example text).
          const hours = (ref.hours_to - ref.hours_from).toFixed(1);
          const when = ref.label ?? (ref.set_at ? formatPinDate(ref.set_at) : "pinned");
          markLines.push({
            silent: true, symbol: "none",
            lineStyle: { color: colors.accent, type: "solid", width: 1.5 },
            label: {
              formatter: `reference pinned · ${ref.n} flight${ref.n === 1 ? "" : "s"} (${hours} h) · ${when}`,
              position: "insideStartTop", color: colors.accent, fontFamily: fontSans, fontSize: 10,
            },
            data: [{ xAxis: ref.hours_to }],
          });
        }
      }
      if (level?.limit != null) {
        markLines.push({
          silent: true, symbol: "none",
          lineStyle: { color: colors.severityLimit, type: "solid", width: 1.5 },
          label: {
            formatter: `OM limit (${withUnit(level.limit, unit)})`, position: "insideEndTop",
            color: colors.severityLimit, fontFamily: fontSans, fontSize: 10,
          },
          data: [{ yAxis: level.limit }],
        });
      }
      if (level?.margin_line != null) {
        const usedPct = Math.round((1 - omMarginFraction) * 100);
        markLines.push({
          silent: true, symbol: "none",
          lineStyle: { color: colors.severityWarning, type: "dashed", opacity: 0.6 },
          label: {
            formatter: `${usedPct}% of headroom`, position: "insideEndBottom",
            color: colors.severityWarning, fontFamily: fontSans, fontSize: 10,
          },
          data: [{ yAxis: level.margin_line }],
        });
      }
      if (level?.filter_edge_value != null) {
        markLines.push({
          silent: true, symbol: "none",
          lineStyle: { color: colors.severityWatch, type: "dashed" },
          label: {
            formatter: "filter band", position: "insideEndTop",
            color: colors.severityWatch, fontFamily: fontSans, fontSize: 10,
          },
          data: [{ yAxis: level.filter_edge_value }],
        });
      }
    }

    // §8.3/§8.4 (Session F) — the whole-history fit, a detail strip:
    // off by default, shown only with the panel's own affordance on.
    // FleetMetric.trend carries only a slope (Spec 01 §8.4), no
    // intercept, so the line is anchored at the all-flights mean
    // (baseline.mean, at the mean of the plotted x values) rather than
    // refit here — the same line `trend.slope` already describes.
    if (showDetailStrips && metric.trend?.slope != null && metric.baseline.mean != null) {
      const xs = metric.points.map((p) => p.x).filter((x): x is number => x != null);
      if (xs.length >= 2) {
        const meanX = xs.reduce((a, b) => a + b, 0) / xs.length;
        const minX = Math.min(...xs);
        const maxX = Math.max(...xs);
        const slope = metric.trend.slope;
        const intercept = metric.baseline.mean - slope * meanX;
        markLines.push({
          silent: true, symbol: "none",
          lineStyle: { color: colors.textTertiary, type: "dotted", opacity: 0.8 },
          label: { show: false },
          data: [[
            { coord: [minX, slope * minX + intercept] },
            { coord: [maxX, slope * maxX + intercept] },
          ]],
        });
      }
    }

    const baseSeries = { type: "line" as const, data: [] };
    // Each distinct markArea needs its own silent series, same ECharts
    // quirk as markLine below — one series' markArea.data entries all
    // share a single itemStyle, so cramming the recent window, the
    // reference band and (now, pinned) the gap region into one would
    // have silently painted all three with whichever was pushed first.
    const markAreaSeries = markAreas.filter(Boolean).map((a) => ({ type: "line" as const, data: [], markArea: a }));

    const pointSeries = showStratified && metric.by_band
      ? Object.entries(metric.by_band.bands).flatMap(([name]) => {
          const c = bandColor(name);
          return [
            {
              type: "scatter" as const,
              name: bandLabel(name),
              symbolSize: (val: [number, number, string]) => (val[2] === highlightFlight ? 14 : outlierIds.has(val[2]) ? 9 : 7),
              data: metric.points.filter((p) => p.band === name).map((p) => [p.x, p.value, p.flight_id, p.date]),
              itemStyle: {
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                color: (p: any) => (p.data[2] === highlightFlight ? colors.accent : outlierIds.has(p.data[2]) ? colors.severityLimit : c),
              },
            },
          ];
        })
      : [
          {
            type: "scatter" as const,
            symbolSize: (val: [number, number, string]) => (val[2] === highlightFlight ? 14 : outlierIds.has(val[2]) ? 9 : 7),
            data: points,
            itemStyle: {
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              color: (p: any) => (p.data[2] === highlightFlight ? colors.accent : outlierIds.has(p.data[2]) ? colors.severityLimit : colors.textSecondary),
            },
          },
        ];

    // Each distinct markLine needs its own silent series — ECharts merges
    // a single series' markLine.data into one shared style otherwise.
    const markLineSeries = markLines.filter(Boolean).map((ml) => ({ type: "line" as const, data: [], markLine: ml }));

    return {
      animation: false,
      grid: { left: 58, right: 12, top: 10, bottom: 26 },
      tooltip: {
        trigger: "item",
        backgroundColor: colors.panelControl,
        borderColor: colors.border,
        textStyle: { color: colors.textPrimary, fontSize: 11, fontFamily: fontMono },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (p: any) => (Array.isArray(p.data) ? `${p.data[3]} &middot; ${withUnit(p.data[1], unit)}<br/>engine hrs ${p.data[0]}` : ""),
      },
      xAxis: {
        type: "value", scale: true,
        axisLabel: { color: colors.textTertiary, fontSize: 10, fontFamily: fontMono, formatter: (v: number) => `${v.toFixed(0)}h` },
        axisLine: { lineStyle: { color: colors.border } },
        splitLine: { show: false },
      },
      yAxis: {
        type: "value", scale: false,
        axisLabel: { color: colors.textTertiary, fontSize: 10, fontFamily: fontMono, formatter: (v: number) => withUnit(v, unit) },
        splitLine: { lineStyle: { color: colors.borderSubtle } },
      },
      // §5.7/R10.1 (Session G) — controlled zoom: baked into the option
      // (per EChartBase's own convention) rather than driven by
      // imperative dispatchAction, so every strip in the panel can be
      // handed the same startValue/endValue and stay in sync.
      dataZoom: [{
        type: "inside", xAxisIndex: 0, filterMode: "none",
        ...(zoomRange ? { startValue: zoomRange.start, endValue: zoomRange.end } : {}),
      }],
      series: [baseSeries, ...markAreaSeries, ...markLineSeries, ...pointSeries],
    } as EChartsOption;
  }, [metric, shift, unit, omMarginFraction, highlightFlight, outlierIds, showStratified, showDetailStrips, zoomRange]);

  const bend = shift?.bend;
  const level = shift?.level;
  const pinned = shift?.reference.kind === "pinned";
  // Same conditions the chart itself uses to decide whether to draw a
  // not-used region (R10.4/D-1) — recomputed here only for the
  // legend, so it names exactly what's on screen. Both the "older
  // than the reference" and "between the reference and the window"
  // cases share one legend entry now (v0.9).
  const hasNotUsed = pinned && shift != null && (
    Math.min(...metric.points.map((p) => p.x).filter((x): x is number => x != null)) < shift.reference.hours_from
    || shift.recent.hours_from > shift.reference.hours_to
  );

  // §5.7/R10.1 (Session G) — the eligible flights currently in view:
  // every point inside the shared zoom range, or every eligible point
  // at all when unzoomed (zoomRange is null, i.e. the full history).
  const eligiblePoints = metric.points.filter((p) => p.x != null);
  const visiblePoints = zoomRange
    ? eligiblePoints.filter((p) => p.x! >= zoomRange.start && p.x! <= zoomRange.end)
    : eligiblePoints;
  const isFullHistory = visiblePoints.length === eligiblePoints.length;
  const zoomSelection = selectionFor(metric, visiblePoints.map((p) => p.flight_id));
  const windowSelection = shift ? selectionFor(metric, shift.recent.flight_ids) : null;

  return (
    <div style={{ background: "var(--panel)", borderRadius: 12, padding: "16px 16px 12px", display: "grid", gridTemplateColumns: "1fr 260px", gap: 16, opacity: muted ? 0.65 : 1 }}>
      <div>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 6 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>
            {label}
            {/* §9.3: a badge next to the metric name wherever it's
                named — the strip header is one of those places, not
                just the detail panel to the right. */}
            {metric.readiness && (
              <span style={{
                marginLeft: 8, fontSize: 10, fontWeight: 600, color: "var(--text-tertiary)",
                border: "1px solid var(--border)", borderRadius: 999, padding: "1px 6px",
              }}>
                {readinessText(metric.readiness)}
              </span>
            )}
          </span>
          <span className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>
            n=
            <a href="#" onClick={(e) => { e.preventDefault(); onOpenFlights(metric.points.map((p) => p.flight_id)); }}>
              {metric.baseline.n}
            </a>
          </span>
        </div>
        <EChartBase
          option={option}
          height={160}
          onPointClick={(data) => { if (Array.isArray(data) && typeof data[2] === "string") onOpenFlight(data[2]); }}
          onZoom={onZoomChange}
        />
        <div style={{ display: "flex", gap: 14, padding: "4px 2px 0", flexWrap: "wrap", alignItems: "center" }}>
          <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>&#9679; flight</span>
          <span style={{ fontSize: 10, color: "var(--severity-limit)" }}>&#9679; outlier</span>
          <span style={{ fontSize: 10, color: "var(--accent)" }}>▦ {pinned ? "reference pinned (±1σ)" : "reference (±1σ)"}</span>
          <span style={{ fontSize: 10, color: "var(--text-secondary)" }}>▦ recent window</span>
          {/* §5.7.1 item 1 (v0.6): the legend/caption names every
              region actually on screen, not just the two rolling ones. */}
          {hasNotUsed && <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>▦ not used</span>}
          {showDetailStrips && metric.trend?.slope != null && (
            <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>┄ whole-history fit</span>
          )}
          {metric.by_band && (
            <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 5, cursor: "pointer", fontSize: 10, color: "var(--text-tertiary)" }}>
              <input type="checkbox" checked={stratified} onChange={(e) => setStratified(e.target.checked)} />
              Stratify by {bandKind ? bandLabel(bandKind.replace("_band", "")) : "band"}
            </label>
          )}
        </div>
      </div>

      <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
        {metric.readiness && metric.readiness.kind !== "pinned" ? (
          // Spec 12 §9.3 (Session C): a badged metric shows the badge
          // here instead of its normal shift read — engine-computed,
          // never inferred from baseline.n/shift here in the web.
          // *pinned* is the exception (v0.5 §9.3/§5.7.1): it still
          // needs its normal shift read, qualifiers and Unpin control,
          // so it falls through to the branch below instead.
          <div style={{ color: "var(--text-tertiary)" }}>
            <span style={{
              display: "inline-block", fontSize: 11, fontWeight: 600, padding: "2px 8px",
              borderRadius: 999, border: "1px solid var(--border)", color: "var(--text-secondary)",
            }}>
              {readinessText(metric.readiness)}
            </span>
          </div>
        ) : !shift ? (
          <div style={{ color: "var(--text-tertiary)" }}>
            Building your reference — {Math.max(0, 5 - metric.baseline.n)} more flight(s) before change detection starts.
          </div>
        ) : (
          <>
            <div style={{ fontWeight: 600, marginBottom: 6, color: shift.qualifies ? "var(--text-primary)" : "var(--text-secondary)" }}>
              {shift.direction === "none" ? "No notable change." : `shift_z ${shift.shift_z?.toFixed(2) ?? "—"} (${shift.direction})`}
            </div>
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 6 }}>
              last {shift.recent.n} flight(s) ({(shift.recent.hours_to - shift.recent.hours_from).toFixed(1)} h) vs.{" "}
              {shift.reference.n} earlier flight(s)
              {shift.comparison.scope === "band" ? ", compared within band" : shift.comparison.scope === "mixed" ? ", mixed comparison" : shift.comparison.scope === "insufficient" ? " — insufficient comparison" : ""}
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 3, fontSize: 11 }}>
              {bend?.fires && <span>⟲ rate of change has shifted (bend)</span>}
              {level?.om_margin && <span style={{ color: "var(--severity-warning)" }}>⚠ within {Math.round((1 - omMarginFraction) * 100)}% of the OM limit</span>}
              {level?.filter_edge && <span style={{ color: "var(--severity-watch)" }}>⚠ at the edge of your filter band</span>}
              {pinned && <span>📌 since {shift.reference.label ?? (shift.reference.set_at ? formatPinDate(shift.reference.set_at) : "pinned reference")}</span>}
            </div>
            {(onPinReference || onUnpinReference) && (
              <div style={{ marginTop: 10 }}>
                {pinned ? (
                  <button
                    onClick={() => {
                      setDialog("unpin");
                      setUnpinPreview(null);
                      onPreviewUnpin?.().then(setUnpinPreview);
                    }}
                    disabled={pinBusy}
                    style={pinButtonStyle}
                  >
                    Unpin reference
                  </button>
                ) : (
                  <button
                    onClick={() => setDialog("pin")}
                    disabled={pinBusy || zoomSelection.n < SMALL_BASELINE_THRESHOLD}
                    style={pinButtonStyle}
                    title={
                      zoomSelection.n < SMALL_BASELINE_THRESHOLD
                        ? `Zoom to at least ${SMALL_BASELINE_THRESHOLD} flights to pin (${zoomSelection.n} in view)`
                        : `Pin the ${zoomSelection.n} flight${zoomSelection.n === 1 ? "" : "s"} in view`
                    }
                  >
                    Pin reference to these flights
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </div>
      {dialog === "pin" && shift && windowSelection && (
        <PinConfirmDialog
          metricLabel={label}
          zoomSelection={zoomSelection}
          windowSelection={windowSelection}
          isFullHistory={isFullHistory}
          onConfirm={(selection, lbl) => { onPinReference?.(selection.flightIds, lbl); setDialog(null); }}
          onCancel={() => setDialog(null)}
        />
      )}
      {dialog === "unpin" && (
        <UnpinConfirmDialog
          metricLabel={label}
          preview={unpinPreview}
          onConfirm={() => { onUnpinReference?.(); setDialog(null); }}
          onCancel={() => setDialog(null)}
        />
      )}
    </div>
  );
}

// §5.7/R10.1-R10.2 (Session G) — a flight-id list's full selection
// stats (n, hours span, calendar dates), needed for both the zoomed-
// in-view selection and the recent-window alternative — Shift doesn't
// carry calendar dates at all, and the zoom selection isn't a Shift
// field to begin with, so both go through the same points lookup.
function selectionFor(metric: FleetMetric, flightIds: string[]): Selection {
  const ids = new Set(flightIds);
  const pts = metric.points.filter((p) => ids.has(p.flight_id) && p.x != null);
  const xs = pts.map((p) => p.x as number);
  const dates = pts.map((p) => p.date).sort();
  return {
    flightIds,
    n: flightIds.length,
    hours: xs.length ? Math.max(...xs) - Math.min(...xs) : 0,
    dateFrom: dates[0] ?? null,
    dateTo: dates[dates.length - 1] ?? null,
  };
}

const pinButtonStyle: React.CSSProperties = {
  fontSize: 11, padding: "5px 10px", borderRadius: 999, border: "1px solid var(--border)",
  background: "var(--panel-control)", color: "var(--text-secondary)", cursor: "pointer",
};
