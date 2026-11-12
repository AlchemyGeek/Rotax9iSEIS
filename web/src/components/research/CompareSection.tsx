import { Fragment, useEffect, useMemo, useState, type ReactNode } from "react";
import type { EChartsOption } from "echarts";
import { EChartBase } from "../EChartBase";
import { InlineHelp } from "../InlineHelp";
import { EngineRpcError, getEngineClient, type SliceBuildArgs } from "../../lib/engineClient";
import type { CompareChartX, CompareResult, CompareRow, SignalWindow, StudyCompare } from "../../types/contract";
import { channelLabel, downloadText, fmtClock, fmtNum } from "../../lib/research";
import { BODY, BUTTON, LINK, MUTED, SELECT, TD, TH } from "./ui";

const client = getEngineClient();

// Spec 06 §9.2 Compare: one row per slice, grouped by flight, read straight
// from the slice set's descriptors by compare_rows (the same numbers a
// question summarises). Groups collapse to one row per flight; any row can
// be pinned as the reference row (Δ columns, chart marker; saved with the
// study); a chart puts any value against date, engine hours, DA or OAT; the
// diagnostics panel shows §9.1's window diagnostics for the pinned and
// selected rows as aligned small multiples. The v1 aligned view is a tab.

const PALETTE = ["#38BDF8", "#34D399", "#A78BFA", "#F472B6", "#22D3EE", "#818CF8", "#FBBF24", "#F87171", "#2DD4BF", "#C084FC"];
const SOURCE_COLOURS: Record<string, string> = { g3x: "#38BDF8", axis: "#F472B6" };
const DIAG_MAX_ROWS = 4;

export const VALUE_LABELS: Record<string, string> = {
  period_s: "period", period_prominence: "prominence", swing: "swing", median: "level", corr0: "corr. at 0", lag_s: "best lag",
};
const VALUE_COLS = ["period_s", "period_prominence", "swing", "median", "corr0", "lag_s"] as const;
const DELTA_COLS = ["period_s", "swing", "corr0"] as const;
const X_LABELS: Record<CompareChartX, string> = { date: "date", engine_hours: "engine hours", da_ft: "density altitude", oat_c: "OAT" };

function rowTime(r: CompareRow): string {
  return r.start_time ? r.start_time.replace("T", " ").slice(0, 16) : r.date ?? "";
}

function phasesText(p: CompareRow["phases"]): string {
  return Array.isArray(p) ? p.map((x) => x.toLowerCase().replace(/_/g, " ")).join(", ") : (p ?? "");
}

/** The rows as CSV, as `research compare --csv` writes them (§8 Evidence). */
export function compareCsv(res: CompareResult): string {
  const conds = ["source", "da_ft", "oat_c", "pa_ft", "engine_hours", "phases"] as const;
  const vals = ["period_s", "period_prominence", "period_prominent", "swing", "median", "corr0", "lag_s"] as const;
  const deltas = ["period_s", "swing", "median", "corr0", "lag_s"] as const;
  const head = ["flight", "start_time", "duration_s", "count", ...conds, ...res.channels.flatMap((c) => vals.map((k) => `${c}.${k}`))];
  if (res.pinned) head.push("pinned", ...res.channels.flatMap((c) => deltas.map((k) => `${c}.delta_${k}`)));
  const cell = (x: unknown) => {
    if (x === null || x === undefined) return "";
    const s = Array.isArray(x) ? x.join("; ") : String(x === true ? "True" : x === false ? "False" : x);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lines = [head.join(",")];
  for (const r of res.rows) {
    const line: unknown[] = [r.flight, r.start_time, r.duration_s, r.count ?? 1, ...conds.map((k) => r[k])];
    for (const c of res.channels) for (const k of vals) line.push(r.values[c]?.[k]);
    if (res.pinned) {
      line.push(!!r.pinned);
      for (const c of res.channels) for (const k of deltas) line.push(r.delta?.[c]?.[k]);
    }
    lines.push(line.map(cell).join(","));
  }
  return lines.join("\n") + "\n";
}

function chartOption(res: CompareResult, x: CompareChartX, y: string, colour: "flight" | "source"): EChartsOption {
  const [ch, key] = y.split(".");
  const flights = [...new Set(res.rows.map((r) => r.flight))];
  const xv = (r: CompareRow): number | null => {
    if (x === "date") { const t = Date.parse((r.start_time ?? r.date ?? "").replace(" ", "T")); return isNaN(t) ? null : t; }
    const v = r[x];
    return typeof v === "number" ? v : null;
  };
  const pts = res.rows.map((r) => ({ r, x: xv(r), y: r.values[ch]?.[key as keyof CompareRow["values"][string]] as number | null | undefined }))
    .filter((p) => p.x != null && typeof p.y === "number");
  const groups = new Map<string, typeof pts>();
  for (const p of pts) {
    const k = colour === "source" ? (p.r.source ?? "unknown") : p.r.flight;
    groups.set(k, [...(groups.get(k) ?? []), p]);
  }
  const colourOf = (k: string) => (colour === "source" ? SOURCE_COLOURS[k] ?? "#94A3B8" : PALETTE[flights.indexOf(k) % PALETTE.length]);
  const om = key === "median" ? (res.om_limits[ch] ?? []).filter((l) => l.limit_type === "MAX" || l.limit_type === "MIN") : [];
  const pinned = pts.find((p) => p.r.pinned);
  return {
    animation: false,
    grid: { left: 56, right: 24, top: 16, bottom: 36 },
    xAxis: { type: x === "date" ? "time" : "value", scale: true, name: X_LABELS[x], nameLocation: "middle", nameGap: 22, nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 9 } },
    yAxis: { type: "value", scale: true, name: `${channelLabel(ch)} ${VALUE_LABELS[key] ?? key}`, nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 9 } },
    tooltip: { trigger: "item", formatter: (p: unknown) => { const d = (p as { data: [number, number, string] }).data; return `${d[2]}<br/>${fmtNum(d[1], 2)}`; } },
    series: [
      ...[...groups.entries()].map(([k, ps], i) => ({
        type: "scatter" as const, name: k, symbolSize: 7, itemStyle: { color: colourOf(k) },
        data: ps.map((p) => [p.x, p.y, `${rowTime(p.r)} · ${p.r.label}`]),
        ...(i === 0 && om.length ? { markLine: { silent: true, symbol: "none", lineStyle: { type: "dashed" as const, color: "#ef4444" },
          label: { fontSize: 9, formatter: (q: { name?: string }) => q.name ?? "" }, data: om.map((l) => ({ yAxis: l.value, name: `OM ${l.label}` })) } } : {}),
      })),
      ...(pinned ? [{ type: "scatter" as const, name: "pinned", symbol: "diamond", symbolSize: 15, z: 10,
        itemStyle: { color: "transparent", borderColor: "#facc15", borderWidth: 2 }, data: [[pinned.x, pinned.y, `pinned · ${rowTime(pinned.r)}`]] }] : []),
    ],
  };
}

function mini(title: string, xs: number[], ys: (number | null)[], yr: [number, number] | null, mark: number | null): EChartsOption {
  return {
    animation: false,
    title: { text: title, textStyle: { fontSize: 9, fontWeight: "normal" }, left: 2, top: 0 },
    grid: { left: 34, right: 6, top: 14, bottom: 16 },
    xAxis: { type: "value", min: xs.length ? Math.min(...xs) : 0, max: xs.length ? Math.max(...xs) : 1, axisLabel: { fontSize: 8 } },
    yAxis: { type: "value", ...(yr ? { min: yr[0], max: yr[1] } : { scale: true }), axisLabel: { fontSize: 8 }, splitNumber: 2 },
    series: [{ type: "line", showSymbol: false, lineStyle: { width: 1 }, data: xs.map((x, i) => [x, ys[i]]),
      markLine: mark != null ? { silent: true, symbol: "none", lineStyle: { color: "#facc15" }, label: { show: false }, data: [{ xAxis: mark }] } : undefined }],
  };
}

/** Aligned small multiples: one column per row, the window's detrended
 * trace (t = 0 at the slice start), ACF and periodogram, on shared axes
 * per channel so the columns read against each other. */
function DiagnosticsPanel({ rows, channels, reference }: { rows: CompareRow[]; channels: string[]; reference: string | null }) {
  const [wins, setWins] = useState<Record<string, SignalWindow | string>>({});
  const key = JSON.stringify([rows.map((r) => r.row_id), channels, reference]);
  useEffect(() => {
    let live = true;
    setWins({});
    for (const r of rows) {
      client.analyzeSignal({ flight_id: r.flight, channels, reference, window: { start_s: r.start_s, end_s: r.end_s }, include_strips: false, include_values: false })
        .then((res) => { if (live && res.window) setWins((w) => ({ ...w, [r.row_id]: res.window! })); })
        .catch((e) => { if (live) setWins((w) => ({ ...w, [r.row_id]: e instanceof Error ? e.message : String(e) })); });
    }
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  if (!rows.length) return <div style={BODY}>Pin a row or tick rows in the table to see their windows side by side.</div>;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }} data-testid="compare-diagnostics">
      {channels.map((ch) => {
        const ok = rows.map((r) => wins[r.row_id]).filter((w): w is SignalWindow => typeof w === "object" && !!w?.diagnostics[ch]);
        const tr = ok.flatMap((w) => w.diagnostics[ch].detrended.filter((v): v is number => v != null));
        const trRange: [number, number] | null = tr.length ? [Math.min(...tr), Math.max(...tr)] : null;
        const pw = ok.flatMap((w) => w.diagnostics[ch].periodogram.power);
        return (
          <div key={ch}>
            <div style={{ fontSize: 11, fontWeight: 600, marginBottom: 4 }}>{channelLabel(ch)}</div>
            <div style={{ display: "grid", gridTemplateColumns: `repeat(${rows.length}, minmax(160px, 1fr))`, gap: 6 }}>
              {rows.map((r) => {
                const w = wins[r.row_id];
                const d = typeof w === "object" ? w.diagnostics[ch] : null;
                return (
                  <div key={r.row_id} style={{ border: r.pinned ? "1px solid #facc15" : "1px solid var(--border)", borderRadius: 6, padding: 4 }}>
                    <div style={{ ...MUTED, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{r.pinned ? "pinned · " : ""}{rowTime(r)} · {r.label}</div>
                    {typeof w === "string" && <div style={{ ...MUTED, color: "var(--severity-warning)" }}>{w}</div>}
                    {!w && <div style={MUTED}>computing…</div>}
                    {d && (
                      <>
                        <EChartBase height={80} option={mini("detrended", d.detrended.map((_, i) => i), d.detrended, trRange, null)} />
                        <EChartBase height={80} option={mini(`autocorrelation · ${d.period_s != null ? `${fmtNum(d.period_s, 1)} s` : "no period"}`, d.acf.map((_, i) => i), d.acf, [-1, 1], d.period_s)} />
                        <EChartBase height={80} option={mini("periodogram", d.periodogram.period_s, d.periodogram.power, pw.length ? [0, Math.max(...pw)] : null, d.period_ls_s)} />
                      </>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function CompareSection({ build, ready, compare, readOnly, onChange, onOpenRow, aligned }: {
  build: SliceBuildArgs;
  ready: boolean;
  compare: StudyCompare | null;
  readOnly: boolean;
  onChange: (c: StudyCompare) => void;
  onOpenRow: (r: CompareRow) => void;
  aligned: ReactNode;
}) {
  const cmp: StudyCompare = compare ?? { pinned: null, collapse: false, channels: [], reference: null, chart: {} };
  const channels = cmp.channels.length ? cmp.channels : build.channels ?? ["rpm"];
  const [res, setRes] = useState<CompareResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"rows" | "aligned">("rows");
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string[]>([]);
  const [diagOpen, setDiagOpen] = useState(false);
  const set = (patch: Partial<StudyCompare>) => onChange({ ...cmp, ...patch });

  const key = JSON.stringify([build, channels, cmp.reference, cmp.pinned, cmp.collapse]);
  useEffect(() => {
    if (!ready || readOnly) { setRes(null); return; }
    let live = true;
    const t = setTimeout(async () => {
      setLoading(true);
      try {
        const r = await client.compareRows({ ...build, channels, reference: cmp.reference ?? undefined, pinned: cmp.pinned, collapse: cmp.collapse });
        if (live) { setRes(r); setError(null); }
      } catch (e) {
        if (!live) return;
        // A pinned row that no longer exists (the rule changed): drop the pin.
        if (e instanceof EngineRpcError && e.code === "BAD_PARAMS" && cmp.pinned && /no row/.test(e.message)) { set({ pinned: null }); return; }
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (live) setLoading(false);
      }
    }, 400);
    return () => { live = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ready, readOnly]);

  const byId = useMemo(() => new Map((res?.rows ?? []).map((r) => [r.row_id, r])), [res]);
  const pinnedRow = res?.rows.find((r) => r.pinned) ?? null;
  const diagRows = useMemo(() => {
    const ids = [...(pinnedRow ? [pinnedRow.row_id] : []), ...selected.filter((id) => id !== pinnedRow?.row_id)];
    return ids.map((id) => byId.get(id)).filter((r): r is CompareRow => !!r && r.kind !== "flight").slice(0, DIAG_MAX_ROWS);
  }, [byId, pinnedRow, selected]);

  const yChoices = channels.flatMap((c) => VALUE_COLS.filter((k) => !(k === "corr0" || k === "lag_s") || c !== (res?.reference ?? "rpm")).map((k) => `${c}.${k}`));
  const y = cmp.chart.y && yChoices.includes(cmp.chart.y) ? cmp.chart.y : `${channels[0]}.swing`;
  const x = cmp.chart.x ?? "date";
  const colour = cmp.chart.colour ?? "flight";
  const isRef = (c: string) => c === res?.reference;

  function valueCells(r: CompareRow) {
    return channels.flatMap((c) => VALUE_COLS.filter((k) => !isRef(c) || (k !== "corr0" && k !== "lag_s")).map((k) => {
      const v = r.values[c]?.[k];
      const dim = k === "period_s" && r.kind !== "flight" && !r.values[c]?.period_prominent;
      return <td key={`${c}.${k}`} style={{ ...TD, textAlign: "right", color: dim ? "var(--text-tertiary)" : undefined }}>{k === "lag_s" && typeof v === "number" ? `${v > 0 ? "+" : ""}${v} s` : fmtNum(v, k === "corr0" || k === "period_prominence" ? 2 : 1)}</td>;
    }));
  }
  function deltaCells(r: CompareRow) {
    if (!res?.pinned) return [];
    return channels.flatMap((c) => DELTA_COLS.filter((k) => !isRef(c) || k !== "corr0").map((k) => {
      const v = r.delta?.[c]?.[k];
      return <td key={`d${c}.${k}`} style={{ ...TD, textAlign: "right", color: "var(--text-secondary)" }}>{r.pinned ? "—" : typeof v === "number" ? `${v > 0 ? "+" : ""}${fmtNum(v, k === "corr0" ? 2 : 1)}` : "—"}</td>;
    }));
  }
  function rowCells(r: CompareRow, indent: boolean) {
    return (
      <>
        <td style={TD}>
          {r.kind !== "flight" && <input type="checkbox" checked={selected.includes(r.row_id)} aria-label="Select for diagnostics"
            onChange={(e) => setSelected((s) => (e.target.checked ? [...s, r.row_id] : s.filter((x) => x !== r.row_id)))} />}
        </td>
        <td style={{ ...TD, paddingLeft: indent ? 24 : 10 }}>
          <button type="button" onClick={() => onOpenRow(r)} style={LINK} title="open this window in Flight view">{r.kind === "flight" ? rowTime(r) : `${fmtClock(r.start_s)}–${fmtClock(r.end_s)}`}</button>
          {" "}<span style={MUTED}>{r.label}</span>
        </td>
        <td style={{ ...TD, textAlign: "right" }}>{fmtNum(r.duration_s, 0)} s</td>
        <td style={TD}>{r.source ?? "—"}</td>
        <td style={{ ...TD, textAlign: "right" }}>{fmtNum(r.da_ft, 0)}</td>
        <td style={{ ...TD, textAlign: "right" }}>{fmtNum(r.oat_c, 0)}</td>
        <td style={{ ...TD, textAlign: "right" }}>{fmtNum(r.engine_hours, 1)}</td>
        <td style={{ ...TD, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }} title={phasesText(r.phases)}>{phasesText(r.phases)}</td>
        {valueCells(r)}
        {deltaCells(r)}
        <td style={TD}>
          {!readOnly && <button type="button" onClick={() => set({ pinned: r.pinned ? null : r.row_id })} style={LINK} data-testid="pin-row">{r.pinned ? "unpin" : "pin"}</button>}
        </td>
      </>
    );
  }

  const valueHeads = channels.flatMap((c) => VALUE_COLS.filter((k) => !isRef(c) || (k !== "corr0" && k !== "lag_s")).map((k) => <th key={`${c}.${k}`} style={{ ...TH, textAlign: "right" }}>{channelLabel(c)} {VALUE_LABELS[k]}</th>));
  const deltaHeads = res?.pinned ? channels.flatMap((c) => DELTA_COLS.filter((k) => !isRef(c) || k !== "corr0").map((k) => <th key={`d${c}.${k}`} style={{ ...TH, textAlign: "right" }}>Δ {channelLabel(c)} {VALUE_LABELS[k]}</th>)) : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }} data-testid="compare-section">
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        {(["rows", "aligned"] as const).map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)} data-testid={`compare-tab-${t}`}
            style={{ ...BUTTON, background: tab === t ? "var(--brand)" : BUTTON.background, color: tab === t ? "var(--on-brand)" : BUTTON.color }}>
            {t === "rows" ? "Rows" : "Aligned view"}
          </button>
        ))}
        <span style={{ flexGrow: 1 }} />
        {tab === "rows" && res && (
          <>
            <label style={{ ...MUTED, display: "flex", gap: 4, alignItems: "center" }}>
              <input type="checkbox" checked={cmp.collapse} disabled={readOnly} onChange={(e) => set({ collapse: e.target.checked })} data-testid="compare-collapse" /> one row per flight
            </label>
            <button type="button" onClick={() => downloadText("compare.csv", compareCsv(res), "text/csv")} style={BUTTON} data-testid="compare-csv">CSV</button>
          </>
        )}
      </div>

      {tab === "aligned" && aligned}

      {tab === "rows" && (
        <>
          {!ready && <div style={BODY}>Add a rule (from Signal's <em>Make this a rule</em>, a preset or a phase) or a hand slice to see one row per slice.</div>}
          {readOnly && <div style={BODY}>The sender's rows are not recomputed here; run the study on your flights to compare yours.</div>}
          {error && <div style={{ ...BODY, color: "var(--severity-warning)" }}>{error}</div>}
          {loading && <div style={MUTED}>comparing…</div>}
          {res && (
            <>
              <div style={MUTED} data-testid="compare-counts">
                {res.slice_count} slice{res.slice_count === 1 ? "" : "s"} from {res.flight_count} flight{res.flight_count === 1 ? "" : "s"}
                {res.flights_without.length > 0 && ` · ${res.flights_without.length} selected flight${res.flights_without.length === 1 ? "" : "s"} with no matching slice`}
                {Object.keys(res.by_source ?? {}).length > 1 && ` · ${Object.entries(res.by_source).map(([k, v]) => `${v} ${k}`).join(", ")}`}
                {" "}· Pin <InlineHelp id="research.pinning" />
              </div>

              <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
                <span style={MUTED}>chart</span>
                <select value={y} onChange={(e) => set({ chart: { ...cmp.chart, y: e.target.value } })} style={SELECT} aria-label="Chart value">
                  {yChoices.map((v) => { const [c, k] = v.split("."); return <option key={v} value={v}>{channelLabel(c)} {VALUE_LABELS[k]}</option>; })}
                </select>
                <span style={MUTED}>against</span>
                <select value={x} onChange={(e) => set({ chart: { ...cmp.chart, x: e.target.value as CompareChartX } })} style={SELECT} aria-label="Chart against">
                  {(res.chart_x as CompareChartX[]).map((v) => <option key={v} value={v}>{X_LABELS[v]}</option>)}
                </select>
                <span style={MUTED}>colour by</span>
                <select value={colour} onChange={(e) => set({ chart: { ...cmp.chart, colour: e.target.value as "flight" | "source" } })} style={SELECT} aria-label="Colour by">
                  <option value="flight">flight</option>
                  <option value="source">log source</option>
                </select>
              </div>
              <div data-testid="compare-chart"><EChartBase height={220} option={chartOption(res, x, y, colour)} /></div>

              <div style={{ overflowX: "auto" }}>
                <table style={{ borderCollapse: "collapse", minWidth: "100%" }} data-testid="compare-table">
                  <thead>
                    <tr>
                      <th style={TH} />
                      <th style={TH}>{res.collapsed ? "flight" : "slice"}</th>
                      <th style={{ ...TH, textAlign: "right" }}>duration</th>
                      <th style={TH}>source</th>
                      <th style={{ ...TH, textAlign: "right" }}>DA ft</th>
                      <th style={{ ...TH, textAlign: "right" }}>OAT °C</th>
                      <th style={{ ...TH, textAlign: "right" }}>engine h</th>
                      <th style={TH}>phases</th>
                      {valueHeads}
                      {deltaHeads}
                      <th style={TH} />
                    </tr>
                  </thead>
                  <tbody>
                    {res.collapsed
                      ? res.rows.map((r) => (
                        <tr key={r.row_id} data-testid="compare-row" style={{ background: r.pinned ? "rgba(250,204,21,0.08)" : undefined }}>{rowCells(r, false)}</tr>
                      ))
                      : res.groups.map((g) => {
                        const open = !hidden.has(g.flight);
                        return (
                          <Fragment key={g.flight}>
                            <tr data-testid="compare-group" style={{ background: "var(--bg)" }}>
                              <td style={TD}>
                                <button type="button" onClick={() => setHidden((h) => { const n = new Set(h); if (open) n.add(g.flight); else n.delete(g.flight); return n; })}
                                  style={{ ...LINK, textDecoration: "none" }} aria-label={open ? "Collapse flight" : "Expand flight"} aria-expanded={open}>{open ? "▾" : "▸"}</button>
                              </td>
                              <td style={{ ...TD, fontWeight: 600 }} colSpan={1}>{rowTime(g.summary)} <span style={MUTED}>{g.count} slice{g.count === 1 ? "" : "s"}{g.count > 1 ? " · median" : ""}</span></td>
                              <td style={{ ...TD, textAlign: "right" }}>{fmtNum(g.summary.duration_s, 0)} s</td>
                              <td style={TD}>{g.source ?? "—"}</td>
                              <td style={{ ...TD, textAlign: "right" }}>{fmtNum(g.summary.da_ft, 0)}</td>
                              <td style={{ ...TD, textAlign: "right" }}>{fmtNum(g.summary.oat_c, 0)}</td>
                              <td style={{ ...TD, textAlign: "right" }}>{fmtNum(g.summary.engine_hours, 1)}</td>
                              <td style={TD} />
                              {open ? valueHeads.map((_, i) => <td key={i} style={TD} />) : valueCells(g.summary)}
                              {deltaHeads.map((_, i) => <td key={`d${i}`} style={TD} />)}
                              <td style={TD} />
                            </tr>
                            {open && g.row_ids.map((id) => { const r = byId.get(id); return r ? (
                              <tr key={id} data-testid="compare-row" style={{ background: r.pinned ? "rgba(250,204,21,0.08)" : undefined }}>{rowCells(r, true)}</tr>
                            ) : null; })}
                          </Fragment>
                        );
                      })}
                  </tbody>
                </table>
              </div>
              {res.flights_without.length > 0 && (
                <details>
                  <summary style={{ ...MUTED, cursor: "pointer" }}>{res.flights_without.length} flight{res.flights_without.length === 1 ? "" : "s"} with no matching slice</summary>
                  <div style={{ ...MUTED, marginTop: 4 }}>{res.flights_without.map((f) => f.start_utc?.replace("T", " ").slice(0, 16) ?? f.date ?? f.flight).join(" · ")}</div>
                </details>
              )}

              <div>
                <button type="button" onClick={() => setDiagOpen((v) => !v)} style={LINK} aria-expanded={diagOpen} data-testid="compare-diagnostics-toggle">
                  {diagOpen ? "Hide diagnostics" : `Diagnostics for the pinned and ticked rows${diagRows.length ? ` (${diagRows.length})` : ""}`}
                </button>
                {res.collapsed && diagOpen && <div style={{ ...MUTED, marginTop: 4 }}>Diagnostics are per slice: untick “one row per flight” to choose slices.</div>}
                {diagOpen && <div style={{ marginTop: 8 }}><DiagnosticsPanel rows={diagRows} channels={channels} reference={res.reference} /></div>}
                {diagOpen && selected.length + (pinnedRow ? 1 : 0) > DIAG_MAX_ROWS && <div style={MUTED}>Showing the first {DIAG_MAX_ROWS}.</div>}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}
