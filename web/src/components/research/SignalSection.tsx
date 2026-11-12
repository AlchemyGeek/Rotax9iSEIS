import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import type { EChartsOption } from "echarts";
import { EChartBase } from "../EChartBase";
import { InlineHelp } from "../InlineHelp";
import { getEngineClient, type FlightSummary } from "../../lib/engineClient";
import type { SignalResult, SignalStrips, SignalWindow, SliceRule, StudySignal, UserReference } from "../../types/contract";
import { RESEARCH_CHANNELS, channelLabel, fmtClock, fmtNum } from "../../lib/research";
import { phaseColorAlpha, phaseLabel } from "../../lib/phases";
import { BODY, CHIP, LINK, MUTED, PRIMARY, SELECT, TD, TH } from "./ui";

const client = getEngineClient();

// Spec 06 §9.1 Signal view: one flight, its channels stacked on one time
// axis with the phases shaded, and under each channel two rolling strips
// (swing; dominant period, drawn only where its prominence passes the
// threshold). Click-drag on the chart or a strip sets the window; the
// window's diagnostics and numbers come back from analyze_signal. Nothing
// here computes a descriptor — the strips and numbers are the host's.

// The plot area's horizontal margins, shared by every chart and strip so a
// second lines up across them (and the drag maps x to seconds).
export const PLOT_LEFT = 56;
export const PLOT_RIGHT = 16;
const STRIP_BINS = 600;
const CHART_HEIGHT = 96;

// A perceptually ordered ramp (dark → light) for the swing strip and a
// hue ramp for the period strip. Values are read from the legend beside
// each strip, never from a colour alone.
const SWING_RAMP = ["#1e293b", "#1e3a8a", "#2563eb", "#38bdf8", "#a5f3fc"];
const PERIOD_RAMP = ["#7c3aed", "#db2777", "#f59e0b", "#84cc16", "#14b8a6"];

function lerpRamp(ramp: string[], t: number): string {
  const x = Math.max(0, Math.min(1, t)) * (ramp.length - 1);
  const i = Math.min(ramp.length - 2, Math.floor(x));
  const f = x - i;
  const a = ramp[i].slice(1), b = ramp[i + 1].slice(1);
  const ch = (k: number) => Math.round(parseInt(a.slice(k, k + 2), 16) * (1 - f) + parseInt(b.slice(k, k + 2), 16) * f);
  return `rgb(${ch(0)},${ch(2)},${ch(4)})`;
}

function quantile(xs: number[], q: number): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.max(0, Math.round(q * (s.length - 1))))];
}

/** Bins a per-second strip to at most STRIP_BINS cells: the bin's largest
 * swing, and the median of its lit periods (none → the cell stays empty). */
export function binStrip(st: SignalStrips, kind: "swing" | "period"): { cells: (number | null)[]; lo: number | null; hi: number | null } {
  const n = st.swing.length;
  const nb = Math.max(1, Math.min(STRIP_BINS, n));
  const cells: (number | null)[] = [];
  const all: number[] = [];
  for (let b = 0; b < nb; b++) {
    const a = Math.floor((b * n) / nb), e = Math.max(a + 1, Math.floor(((b + 1) * n) / nb));
    if (kind === "swing") {
      let m: number | null = null;
      for (let i = a; i < e; i++) { const v = st.swing[i]; if (v != null && (m == null || v > m)) m = v; }
      cells.push(m);
      if (m != null) all.push(m);
    } else {
      const lit: number[] = [];
      for (let i = a; i < e; i++) { const p = st.period_s[i]; if (st.prominent[i] && p != null) lit.push(p); }
      const m = quantile(lit, 0.5);
      cells.push(m);
      if (m != null) all.push(m);
    }
  }
  // The swing scale stops at the 98th percentile so one spike does not
  // wash out the rest of the flight.
  return { cells, lo: all.length ? Math.min(...all) : null, hi: kind === "swing" ? quantile(all, 0.98) : (all.length ? Math.max(...all) : null) };
}

function Strip({ st, kind, unit, testId }: { st: SignalStrips; kind: "swing" | "period"; unit: string; testId: string }) {
  const { cells, lo, hi } = useMemo(() => binStrip(st, kind), [st, kind]);
  const ramp = kind === "swing" ? SWING_RAMP : PERIOD_RAMP;
  const span = lo != null && hi != null && hi > lo ? hi - lo : 1;
  const w = 1000 / cells.length;
  return (
    <div style={{ display: "flex", alignItems: "center", height: 14 }} data-testid={testId}>
      <span style={{ width: PLOT_LEFT, flexShrink: 0, fontSize: 10, color: "var(--text-tertiary)", textAlign: "right", paddingRight: 6 }}>{kind === "swing" ? "swing" : "period"}</span>
      <svg viewBox="0 0 1000 10" preserveAspectRatio="none" style={{ flexGrow: 1, height: 12, background: "var(--bg)", borderRadius: 2 }} aria-hidden>
        {cells.map((v, i) => (v == null ? null : <rect key={i} x={i * w} y={0} width={w + 0.5} height={10} fill={lerpRamp(ramp, lo == null ? 0 : (v - lo) / span)} />))}
      </svg>
      <span style={{ width: PLOT_RIGHT + 110, flexShrink: 0, fontSize: 10, color: "var(--text-tertiary)", paddingLeft: 6, whiteSpace: "nowrap" }}>
        {lo == null ? (kind === "period" ? "no clear period" : "—") : `${fmtNum(lo, 1)}–${fmtNum(hi, 1)} ${kind === "period" ? "s" : unit}`}
      </span>
    </div>
  );
}

function channelOption(sig: SignalResult, ch: string, win: { start_s: number; end_s: number } | null, showPhases: boolean): EChartsOption {
  const ys = sig.values?.[ch] ?? [];
  const data = ys.map((v, i) => [i, v]);
  const areas: object[] = showPhases
    ? sig.phases.map((p) => [{ xAxis: p.start_s, itemStyle: { color: phaseColorAlpha(p.phase, 0.16) }, name: phaseLabel(p.phase) }, { xAxis: p.end_s }])
    : [];
  const om = (sig.om_limits[ch] ?? []).filter((l) => l.limit_type === "MAX" || l.limit_type === "MIN");
  return {
    animation: false,
    grid: { left: PLOT_LEFT, right: PLOT_RIGHT + 110, top: 6, bottom: 18 },
    xAxis: { type: "value", min: 0, max: sig.duration_s, axisLabel: { fontSize: 9, formatter: (v: number) => fmtClock(v) }, splitLine: { show: false } },
    yAxis: { type: "value", scale: true, name: channelLabel(ch), nameTextStyle: { fontSize: 10 }, axisLabel: { fontSize: 9 }, splitNumber: 2 },
    tooltip: { trigger: "axis", valueFormatter: (v) => fmtNum(v as number, 2) },
    series: [{
      type: "line", data, showSymbol: false, sampling: "lttb", lineStyle: { width: 1 }, name: channelLabel(ch),
      markArea: { silent: true, data: [
        ...areas,
        ...(win ? [[{ xAxis: win.start_s, itemStyle: { color: "rgba(250,204,21,0.18)", borderColor: "rgba(250,204,21,0.8)", borderWidth: 1 } }, { xAxis: win.end_s }]] : []),
      ] as never },
      markLine: om.length ? { silent: true, symbol: "none", lineStyle: { type: "dashed", color: "var(--severity-limit)" },
        label: { fontSize: 9, formatter: (p: { name?: string }) => p.name ?? "" }, data: om.map((l) => ({ yAxis: l.value, name: `OM ${l.label}` })) } : undefined,
    }],
  };
}

function miniOption(title: string, xs: number[], ys: (number | null)[], mark: number | null, xName: string): EChartsOption {
  return {
    animation: false,
    title: { text: title, textStyle: { fontSize: 10, fontWeight: "normal" }, left: 4, top: 0 },
    grid: { left: 40, right: 8, top: 18, bottom: 22 },
    xAxis: { type: "value", min: xs.length ? Math.min(...xs) : 0, max: xs.length ? Math.max(...xs) : 1, name: xName, nameLocation: "end", nameTextStyle: { fontSize: 9 }, axisLabel: { fontSize: 9 } },
    yAxis: { type: "value", scale: true, axisLabel: { fontSize: 9 }, splitNumber: 2 },
    tooltip: { trigger: "axis", valueFormatter: (v) => fmtNum(v as number, 3) },
    series: [{
      type: "line", showSymbol: false, data: xs.map((x, i) => [x, ys[i]]), lineStyle: { width: 1 },
      markLine: mark != null ? { silent: true, symbol: "none", lineStyle: { color: "#facc15" }, label: { fontSize: 9, formatter: () => fmtNum(mark, 1) }, data: [{ xAxis: mark }] } : undefined,
    }],
  };
}

/** The §9.1 window diagnostics for one channel: detrended trace, ACF with
 * the period marked, periodogram with its peak, and for a non-reference
 * channel the correlation against lag with the best lag marked. */
export function WindowDiagnostics({ w, ch, height = 110 }: { w: SignalWindow; ch: string; height?: number }) {
  const d = w.diagnostics[ch];
  if (!d) return null;
  const t = d.detrended.map((_, i) => i);
  const lags = d.acf.map((_, i) => i);
  const pg = d.periodogram;
  const lc = d.lag_curve ?? [];
  const cell = { flex: "1 1 200px", minWidth: 180 } as const;
  return (
    <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }} data-testid={`diagnostics-${ch}`}>
      <div style={cell}><EChartBase height={height} option={miniOption(`${channelLabel(ch)} detrended`, t, d.detrended, null, "s")} /></div>
      <div style={cell}><EChartBase height={height} option={miniOption("autocorrelation", lags, d.acf, d.period_s, "lag s")} /></div>
      <div style={cell}><EChartBase height={height} option={miniOption("periodogram", pg.period_s, pg.power, d.period_ls_s, "period s")} /></div>
      {lc.length > 0 && <div style={cell}><EChartBase height={height} option={miniOption("with the reference, by lag", lc.map((p) => p.lag_s), lc.map((p) => p.corr), d.best_lag_s ?? null, "lag s")} /></div>}
    </div>
  );
}

export function SignalSection({ flights, signal, defaultChannels, references, readOnly, onChange, onMakeRule }: {
  flights: FlightSummary[];
  signal: StudySignal | null;
  defaultChannels: string[];
  references: UserReference[];
  readOnly: boolean;
  onChange: (s: StudySignal) => void;
  onMakeRule: (rule: SliceRule) => void;
}) {
  const flight = signal?.flight ?? "";
  const channels = signal?.channels?.length ? signal.channels : defaultChannels;
  const reference = signal?.reference ?? null;
  const win = signal?.window ?? null;
  const [sig, setSig] = useState<SignalResult | null>(null);
  const [winRes, setWinRes] = useState<SignalWindow | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingWin, setLoadingWin] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ruleChannel, setRuleChannel] = useState<string>("");
  const [showPhases, setShowPhases] = useState(true);
  const [drag, setDrag] = useState<{ a: number; b: number } | null>(null);
  const plotRef = useRef<HTMLDivElement>(null);
  const set = (patch: Partial<StudySignal>) => onChange({ flight: flight || null, channels, reference, window: win, ...patch });

  // The flight's strips and traces: once per flight and channel set.
  const flightKey = JSON.stringify([flight, channels, reference]);
  useEffect(() => {
    if (!flight || readOnly) { setSig(null); return; }
    let live = true;
    setLoading(true);
    setError(null);
    client.analyzeSignal({ flight_id: flight, channels, reference })
      .then((r) => { if (live) setSig(r); })
      .catch((e) => { if (live) { setSig(null); setError(e instanceof Error ? e.message : String(e)); } })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flightKey, readOnly]);

  // The window: diagnostics, numbers and the derived rule, without the strips.
  const winKey = JSON.stringify([flight, channels, reference, win, ruleChannel, references]);
  useEffect(() => {
    if (!flight || !win || readOnly) { setWinRes(null); return; }
    let live = true;
    setLoadingWin(true);
    const t = setTimeout(() => {
      client.analyzeSignal({ flight_id: flight, channels, reference, window: win, references, rule_channel: ruleChannel || undefined,
        include_strips: false, include_values: false })
        .then((r) => { if (live) { setWinRes(r.window); setError(null); } })
        .catch((e) => { if (live) { setWinRes(null); setError(e instanceof Error ? e.message : String(e)); } })
        .finally(() => { if (live) setLoadingWin(false); });
    }, 150);
    return () => { live = false; clearTimeout(t); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [winKey, readOnly]);

  // Click-drag anywhere over the stacked plot sets the window.
  function secondsAt(clientX: number): number {
    const el = plotRef.current;
    if (!el || !sig) return 0;
    const r = el.getBoundingClientRect();
    const w = r.width - PLOT_LEFT - PLOT_RIGHT - 110;
    const x = (clientX - r.left - PLOT_LEFT) / (w > 0 ? w : 1);
    return Math.max(0, Math.min(sig.duration_s, x * sig.duration_s));
  }
  function onDown(e: ReactPointerEvent<HTMLDivElement>) {
    if (!sig || e.button !== 0) return;
    const s = secondsAt(e.clientX);
    setDrag({ a: s, b: s });
    try { e.currentTarget.setPointerCapture(e.pointerId); } catch { /* not supported */ }
  }
  function onMove(e: ReactPointerEvent<HTMLDivElement>) {
    if (drag) setDrag({ ...drag, b: secondsAt(e.clientX) });
  }
  function onUp() {
    if (!drag) return;
    const a = Math.floor(Math.min(drag.a, drag.b)), b = Math.ceil(Math.max(drag.a, drag.b));
    setDrag(null);
    if (b - a >= 4) set({ window: { start_s: a, end_s: b } });
  }
  const dragBox = drag && sig ? (() => {
    const lo = Math.min(drag.a, drag.b) / sig.duration_s, hi = Math.max(drag.a, drag.b) / sig.duration_s;
    return { left: `calc(${PLOT_LEFT}px + (100% - ${PLOT_LEFT + PLOT_RIGHT + 110}px) * ${lo})`, width: `calc((100% - ${PLOT_LEFT + PLOT_RIGHT + 110}px) * ${hi - lo})` };
  })() : null;

  const flightName = (f: FlightSummary) => `${f.header.date}${f.source_filename ? ` · ${f.source_filename}` : ""}`;
  const present = sig?.channels ?? channels;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }} data-testid="signal-section">
      <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
        <span style={MUTED}>flight</span>
        <select value={flight} onChange={(e) => set({ flight: e.target.value || null, window: null })} style={{ ...SELECT, maxWidth: 360 }} disabled={readOnly} aria-label="Signal flight" data-testid="signal-flight">
          <option value="">choose a flight…</option>
          {flights.map((f) => <option key={f.flight_id} value={f.flight_id}>{flightName(f)}</option>)}
        </select>
        <span style={MUTED}>channels</span>
        {channels.map((c) => (
          <span key={c} style={CHIP}>{channelLabel(c)}{c === (sig?.reference ?? reference) ? " (reference)" : ""}
            {!readOnly && channels.length > 1 && <button type="button" onClick={() => set({ channels: channels.filter((x) => x !== c), reference: reference === c ? null : reference })} style={LINK} aria-label={`Remove ${channelLabel(c)}`}>×</button>}
          </span>
        ))}
        {!readOnly && (
          <select value="" onChange={(e) => e.target.value && set({ channels: [...channels, e.target.value] })} style={SELECT} aria-label="Add a signal channel">
            <option value="">+ channel</option>
            {RESEARCH_CHANNELS.filter((c) => !channels.includes(c)).map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
          </select>
        )}
        {channels.length > 1 && (
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <span style={MUTED}>reference</span>
            <select value={reference ?? ""} onChange={(e) => set({ reference: e.target.value || null })} style={SELECT} disabled={readOnly} aria-label="Reference channel">
              <option value="">{channels.includes("rpm") ? "RPM (automatic)" : `${channelLabel(channels[0])} (automatic)`}</option>
              {channels.map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
            </select>
          </label>
        )}
        <span style={{ flexGrow: 1 }} />
        <label style={{ ...MUTED, display: "flex", gap: 4, alignItems: "center" }}><input type="checkbox" checked={showPhases} onChange={(e) => setShowPhases(e.target.checked)} /> phases</label>
      </div>

      {!flight && <div style={BODY}>Choose a flight to see where in it each channel swings and repeats. Research this window on a flight opens here with that flight already chosen.</div>}
      {readOnly && flight && <div style={BODY}>The sender's Signal flight is not in this workspace; run the study on your flights to look at one of yours.</div>}
      {error && <div style={{ ...BODY, color: "var(--severity-warning)" }}>{error}</div>}
      {loading && <div style={MUTED}>reading the flight and computing its strips…</div>}

      {sig && (
        <>
          <div style={{ ...MUTED, display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
            Strips <InlineHelp id="research.strips" />
            <span>{Object.entries(sig.strip_windows).map(([c, w]) => `${channelLabel(c)}: ${w.window_s} s window${w.basis === "period" && w.flight_period_s ? ` (from this flight's ${fmtNum(w.flight_period_s, 1)} s period)` : " (the floor)"}, period clear for ${fmtNum(w.lit_share * 100, 0)}% of the flight`).join(" · ")}</span>
            {sig.missing_channels.length > 0 && <span>· not in this log: {sig.missing_channels.map(channelLabel).join(", ")}</span>}
          </div>
          <div ref={plotRef} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={() => setDrag(null)}
            style={{ position: "relative", cursor: "crosshair", userSelect: "none", touchAction: "none" }} data-testid="signal-plot">
            {present.map((ch) => (
              <div key={ch} style={{ marginBottom: 6 }}>
                <EChartBase height={CHART_HEIGHT} option={channelOption(sig, ch, win, showPhases)} />
                {sig.strips[ch] && <Strip st={sig.strips[ch]} kind="swing" unit={unitOf(ch)} testId={`strip-swing-${ch}`} />}
                {sig.strips[ch] && <div style={{ marginTop: 2 }}><Strip st={sig.strips[ch]} kind="period" unit="s" testId={`strip-period-${ch}`} /></div>}
              </div>
            ))}
            {dragBox && <div style={{ position: "absolute", top: 0, bottom: 0, ...dragBox, background: "rgba(250,204,21,0.15)", border: "1px solid rgba(250,204,21,0.8)", pointerEvents: "none" }} />}
          </div>
        </>
      )}

      {sig && (
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
          <span style={{ fontWeight: 600 }}>Window</span> <InlineHelp id="research.window" />
          {win ? <span style={BODY} data-testid="signal-window">{fmtClock(win.start_s)}–{fmtClock(win.end_s)} ({Math.round(win.end_s - win.start_s)} s)</span>
            : <span style={BODY}>drag across the chart or a strip to choose one</span>}
          {win && !readOnly && <button type="button" onClick={() => set({ window: null })} style={LINK}>clear</button>}
          {loadingWin && <span style={MUTED}>computing…</span>}
        </div>
      )}

      {winRes && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }} data-testid="signal-window-result">
          <table style={{ borderCollapse: "collapse" }}>
            <thead><tr><th style={TH}>This flight's window</th><th style={TH}>Value</th><th style={TH}>Read against</th></tr></thead>
            <tbody>
              {present.flatMap((ch) => (winRes.numbers[ch] ?? []).map((m, i) => (
                <tr key={`${ch}-${i}`} data-testid="signal-number">
                  <td style={TD}>{m.label}</td>
                  <td style={TD}>{m.text}</td>
                  <td style={{ ...TD, whiteSpace: "normal", color: "var(--text-secondary)" }}>
                    {m.references.length ? m.references.map((r) => `${r.kind === "om" ? "" : r.kind === "user" ? "your reference: " : ""}${r.text ?? r.label}${r.source ? ` (${r.source})` : ""}`).join("; ") : "—"}
                  </td>
                </tr>
              )))}
            </tbody>
          </table>
          <div style={MUTED}>
            Windows used: {Object.entries(winRes.windows).map(([c, w]) => `${channelLabel(c)} ${w.window_s} s (lag ±${w.lag_s} s, ${w.basis})`).join(" · ")}.
            These are numbers, not a judgement: no threshold is applied.
          </div>
          <details open>
            <summary style={{ fontSize: 12, cursor: "pointer" }}>Diagnostics</summary>
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 8 }}>
              {present.map((ch) => <WindowDiagnostics key={ch} w={winRes} ch={ch} />)}
            </div>
          </details>
          {!readOnly && (
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
              <button type="button" style={PRIMARY} onClick={() => onMakeRule(winRes.derived_rule)} data-testid="make-rule">Make this a rule</button>
              <InlineHelp id="research.derived_rule" />
              <span style={MUTED}>from</span>
              <select value={ruleChannel} onChange={(e) => setRuleChannel(e.target.value)} style={SELECT} aria-label="Rule channel">
                <option value="">{channelLabel(winRes.derived_rule.derived_from.channel)}</option>
                {present.filter((c) => c !== winRes.derived_rule.derived_from.channel).map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
              </select>
              <span style={BODY}>{winRes.derived_rule.name}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function unitOf(ch: string): string {
  if (ch === "rpm") return "rpm";
  if (ch.endsWith("_inhg")) return "inHg";
  if (ch.endsWith("_gph")) return "gph";
  if (ch.endsWith("_psi")) return "psi";
  if (ch.endsWith("_f")) return "°F";
  if (ch.endsWith("_kt")) return "kt";
  if (ch.endsWith("_fpm")) return "fpm";
  if (ch.endsWith("_pct")) return "%";
  if (ch.endsWith("_volts")) return "V";
  return "";
}
