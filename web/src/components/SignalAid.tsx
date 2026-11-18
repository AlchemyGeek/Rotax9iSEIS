import { useEffect, useMemo, useRef, useState } from "react";
import { getEngineClient } from "../lib/engineClient";
import { channelLabel } from "../lib/research";
import { InlineHelp } from "./InlineHelp";
import type { SignalMagnitude, SignalResult, SignalWindow } from "../types/contract";

const client = getEngineClient();

// Spec 16 D15 — the Flight view's seeing aid. The Signal toggle lays the
// rolling swing and period strips (analyze_signal over the whole flight,
// no window) under the chart, on the chart's own time axis; zooming the
// chart to a window shows that window's swing, period and correlation with
// the reference channel, each beside its references. It derives no rule,
// builds no slice set and runs nothing across flights — comparing is an
// ask in Claude Desktop. Nothing here computes a number: the host does.

// The chart's grid (ChannelTimeline): the strips share its x-axis frame.
const GRID_LEFT = 32;
const GRID_RIGHT = 24;
const ROW_H = 9;
const MAX_CHANNELS = 6;
const READOUT_DELAY_MS = 450;

// One whole-flight analysis per flight and channel set, for the session.
const stripCache = new Map<string, Promise<SignalResult>>();
export function clearSignalCache() { stripCache.clear(); }

function stripsFor(flightId: string, channels: string[]): Promise<SignalResult> {
  const key = `${flightId}|${channels.join(",")}`;
  let p = stripCache.get(key);
  if (!p) {
    p = client.analyzeSignal({ flight_id: flightId, channels, include_values: false });
    p.catch(() => stripCache.delete(key));
    stripCache.set(key, p);
  }
  return p;
}

/** The channels the aid reads: rpm (the reference) and MAP first, then the chart's own. */
export function signalChannels(chartChannels: string[]): string[] {
  return [...new Set(["rpm", "map_inhg", ...chartChannels])].slice(0, MAX_CHANNELS);
}

function quantile(xs: number[], q: number): number {
  if (!xs.length) return 0;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.floor(q * (s.length - 1)))];
}

// One strip row as an SVG of `bins` rects over [w0, w1). "swing" shades
// each bin by its mean swing against the flight's 95th percentile; "lit"
// by the share of its seconds where a repeat stands out — so in a wide view
// a lone lit second stays faint and a sustained cycle (a takeoff) is bright.
function StripRow({ values, lit, w0, w1, scale, mode, testid, title }: {
  values: (number | null)[]; lit: boolean[]; w0: number; w1: number; scale: number; mode: "swing" | "lit"; testid: string; title: string;
}) {
  const span = Math.max(1, w1 - w0);
  const bins = Math.min(400, span);
  const rects = [];
  for (let b = 0; b < bins; b++) {
    const a = Math.floor(w0 + (b * span) / bins), z = Math.max(a + 1, Math.floor(w0 + ((b + 1) * span) / bins));
    let sum = 0, n = 0, on = 0, k = 0;
    for (let i = a; i < z && i < values.length; i++) {
      k++;
      if (lit[i]) on++;
      const x = values[i];
      if (x !== null && x !== undefined) { sum += x; n++; }
    }
    const opacity = mode === "lit" ? (k ? on / k : 0) : (scale > 0 && n ? 0.7 * Math.min(1, sum / n / scale) : 0);
    if (opacity > 0.02) {
      rects.push(<rect key={b} x={b} y={0} width={1.02} height={1} fill={mode === "lit" ? "var(--brand-tint)" : "var(--text-tertiary)"} fillOpacity={opacity} />);
    }
  }
  return (
    <svg viewBox={`0 0 ${bins} 1`} preserveAspectRatio="none" width="100%" height={ROW_H} data-testid={testid} role="img" aria-label={title}
      style={{ display: "block", background: "var(--panel-control)", borderRadius: 2 }}>
      <title>{title}</title>
      {rects}
    </svg>
  );
}

function ReadoutRow({ m }: { m: SignalMagnitude }) {
  const refs = m.references.filter((r) => r.text || r.label);
  return (
    <tr style={{ borderTop: "1px solid var(--border)" }} data-testid="signal-number">
      <td style={{ padding: "5px 8px 5px 0", fontSize: 12, whiteSpace: "nowrap", color: "var(--text-secondary)" }}>{m.label}</td>
      <td className="mono" style={{ padding: "5px 8px", fontSize: 12, fontWeight: 600 }}>{m.text}</td>
      <td style={{ padding: "5px 0 5px 8px", fontSize: 11, color: "var(--text-tertiary)" }} data-testid="signal-reference">
        {refs.length ? refs.map((r) => r.text ?? r.label).join(" · ") : "no Operators Manual line for this number"}
      </td>
    </tr>
  );
}

// The read-out shows, per channel, the swing and the period, and for each
// channel beside the reference its correlation and lag with it (§8: each
// number beside its references; level is the chart's own to show).
export function readoutRows(w: SignalWindow, channels: string[]): { channel: string; rows: SignalMagnitude[] }[] {
  return channels.filter((c) => w.numbers[c]).map((c) => ({
    channel: c,
    rows: w.numbers[c].filter((m) => / (swing|period|with the reference)$/.test(m.label)),
  }));
}

export function SignalAid({ flightId, chartChannels, visibleWindow, fullEnd, enabled }: {
  flightId: string;
  chartChannels: string[];
  visibleWindow: [number, number];
  fullEnd: number;
  enabled: boolean;
}) {
  const [on, setOn] = useState(false);
  const channels = useMemo(() => signalChannels(chartChannels), [chartChannels]);
  const [strips, setStrips] = useState<SignalResult | null>(null);
  const [stripError, setStripError] = useState<string | null>(null);
  const [win, setWin] = useState<SignalWindow | null>(null);
  const [winState, setWinState] = useState<"idle" | "loading" | "error">("idle");
  const [winError, setWinError] = useState<string | null>(null);
  const [w0, w1] = visibleWindow;
  const zoomed = fullEnd > 0 && w1 > w0 && (w0 > 1 || w1 < fullEnd - 1);
  const seq = useRef(0);

  useEffect(() => { setOn(false); setStrips(null); setWin(null); }, [flightId]);

  useEffect(() => {
    if (!on) return;
    let live = true;
    setStripError(null);
    stripsFor(flightId, channels).then((r) => { if (live) setStrips(r); })
      .catch((e) => { if (live) setStripError(e instanceof Error ? e.message : String(e)); });
    return () => { live = false; };
  }, [on, flightId, channels]);

  useEffect(() => {
    if (!on || !zoomed) { setWin(null); setWinState("idle"); return; }
    const mine = ++seq.current;
    setWinState("loading");
    const t = setTimeout(() => {
      client.analyzeSignal({ flight_id: flightId, channels, window: { start_s: Math.floor(w0), end_s: Math.ceil(w1) }, include_strips: false, include_values: false })
        .then((r) => { if (mine === seq.current) { setWin(r.window); setWinState("idle"); } })
        .catch((e) => { if (mine === seq.current) { setWin(null); setWinState("error"); setWinError(e instanceof Error ? e.message : String(e)); } });
    }, READOUT_DELAY_MS);
    return () => clearTimeout(t);
  }, [on, zoomed, flightId, channels, w0, w1]);

  if (!enabled) return null;
  const present = strips ? strips.channels.filter((c) => strips.strips[c]) : [];

  return (
    <div style={{ marginTop: 10 }} data-testid="signal-aid">
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button type="button" onClick={() => setOn((v) => !v)} aria-pressed={on} data-testid="signal-toggle"
          title="Where each channel swings and repeats along the flight; zoom the chart to a window for its numbers"
          style={{ fontSize: 11, padding: "2px 10px", borderRadius: 6, cursor: "pointer", fontWeight: on ? 600 : 400,
            background: on ? "var(--brand)" : "var(--panel-control)", color: on ? "var(--on-brand)" : "var(--text-secondary)",
            border: on ? "1px solid var(--brand)" : "1px solid var(--border)" }}>
          Signal
        </button>
        {on && <InlineHelp id="signal.strips" />}
        {on && !strips && !stripError && <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Reading the log…</span>}
        {on && stripError && <span style={{ fontSize: 11, color: "var(--severity-warning)" }} data-testid="signal-error">{stripError}</span>}
      </div>

      {on && strips && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }} data-testid="signal-strips">
          {present.map((c) => {
            const st = strips.strips[c];
            const swings = st.swing.filter((x): x is number => x !== null);
            const sw = strips.strip_windows[c];
            return (
              <div key={c} style={{ display: "grid", gridTemplateColumns: `${GRID_LEFT}px 1fr ${GRID_RIGHT}px`, alignItems: "center" }} data-testid="signal-channel" data-channel={c}>
                <span />
                <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  <span style={{ fontSize: 10, color: "var(--text-tertiary)" }} data-testid="signal-channel-label">
                    {channelLabel(c)} — swing, and where it repeats{sw?.flight_period_s ? ` (≈ ${sw.flight_period_s.toFixed(1)} s, lit ${Math.round(sw.lit_share * 100)} % of the flight)` : " (no repeat stands out)"}
                  </span>
                  <StripRow values={st.swing} lit={st.prominent} w0={Math.floor(w0)} w1={Math.ceil(w1)} scale={quantile(swings, 0.95)}
                    mode="swing" testid="strip-swing" title={`${channelLabel(c)}: how far it swings`} />
                  <StripRow values={st.period_s} lit={st.prominent} w0={Math.floor(w0)} w1={Math.ceil(w1)} scale={1}
                    mode="lit" testid="strip-period" title={`${channelLabel(c)}: where a repeat stands out`} />
                </div>
                <span />
              </div>
            );
          })}
          {strips.missing_channels.length > 0 && (
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", paddingLeft: GRID_LEFT }}>
              Not in this log: {strips.missing_channels.map(channelLabel).join(", ")}.
            </div>
          )}
        </div>
      )}

      {on && strips && (
        <div style={{ marginTop: 10, paddingLeft: GRID_LEFT }} data-testid="signal-readout">
          {!zoomed && <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>Zoom the chart to a window — a takeoff, a climb — for its swing, period and how the channels move with {channelLabel(strips.reference ?? "rpm")}.</div>}
          {zoomed && winState === "loading" && !win && <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>Measuring the window…</div>}
          {zoomed && winState === "error" && <div style={{ fontSize: 12, color: "var(--severity-warning)" }}>{winError}</div>}
          {zoomed && win && (
            <>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginBottom: 4 }}>
                <span style={{ fontSize: 12, fontWeight: 600 }} data-testid="signal-window">
                  The window: {Math.round(win.duration_s)} s{strips.reference ? `, against ${channelLabel(strips.reference)}` : ""}
                </span>
                <InlineHelp id="signal.window" />
                {winState === "loading" && <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>updating…</span>}
              </div>
              <table style={{ borderCollapse: "collapse", width: "100%" }}>
                <tbody>
                  {readoutRows(win, present).flatMap(({ channel, rows }) => rows.map((m) => <ReadoutRow key={`${channel}:${m.label}`} m={m} />))}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}
    </div>
  );
}
