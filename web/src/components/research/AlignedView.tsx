import { useEffect, useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { EChartBase } from "../EChartBase";
import { getEngineClient, type SliceBuildArgs } from "../../lib/engineClient";
import type { SliceInfo, SliceSamples } from "../../types/contract";
import { RESEARCH_CHANNELS, channelLabel } from "../../lib/research";
import { BUTTON, MUTED, SELECT } from "./ui";

const client = getEngineClient();

// Spec 06 §9 (D6): slices aligned on a rule-based anchor — the condition's
// crossing by default — on one x-axis in elapsed seconds, y shared per
// channel. Overlay up to ~10 slices; small multiples above that (one panel
// per slice, shared axes); channels as stacked strips. A scrubbing cursor
// reads every panel at the same aligned time (ECharts axisPointer link).
// Samples come from get_slice_samples; nothing is computed here.

const SMALL_MULTIPLES_ABOVE = 10;
const PALETTE = ["#38BDF8", "#34D399", "#A78BFA", "#F472B6", "#22D3EE", "#818CF8", "#FBBF24", "#F87171", "#2DD4BF", "#C084FC"];

export const ANCHORS: { id: string; label: string }[] = [
  { id: "crossing", label: "rule crossing (t = 0 where the conditions first hold)" },
  { id: "start", label: "slice start" },
  { id: "end", label: "slice end" },
  { id: "peak:rpm", label: "RPM peak" },
  { id: "peak:map_inhg", label: "MAP peak" },
  { id: "phase:CLIMB", label: "start of climb" },
  { id: "phase:TAKEOFF_ROLL", label: "start of takeoff roll" },
];

export function AlignedView({ build, slices, channels, anchor, onChannels, onAnchor, highlight, onOpenSlice, readOnly }: {
  build: SliceBuildArgs;
  slices: SliceInfo[];
  channels: string[];
  anchor: string;
  onChannels: (c: string[]) => void;
  onAnchor: (a: string) => void;
  highlight?: string | null;
  onOpenSlice?: (s: SliceInfo) => void;
  readOnly?: boolean;
}) {
  const [samples, setSamples] = useState<SliceSamples | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"auto" | "overlay" | "multiples">("auto");

  const ids = useMemo(() => slices.map((s) => s.slice_id), [slices]);
  const key = JSON.stringify([ids, channels, anchor]);

  useEffect(() => {
    if (!ids.length || !channels.length || readOnly) { setSamples(null); return; }
    let live = true;
    setLoading(true);
    setError(null);
    client.getSliceSamples({ ...build, slice_ids: ids, channels, anchor })
      .then((r) => { if (live) setSamples(r); })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, readOnly]);

  const multiples = mode === "multiples" || (mode === "auto" && slices.length > SMALL_MULTIPLES_ABOVE);
  const colorOf = (i: number) => PALETTE[i % PALETTE.length];

  // One grid per (channel × slice) in small multiples, per channel in overlay;
  // all grids share one x extent and, per channel, one y extent.
  const option = useMemo<EChartsOption | null>(() => {
    if (!samples) return null;
    const ss = samples.slices;
    const chans = samples.channels;
    const xs = ss.flatMap((s) => [s.t[0] ?? 0, s.t[s.t.length - 1] ?? 0]);
    const xMin = Math.min(0, ...xs), xMax = Math.max(1, ...xs);
    const yExt: Record<string, [number, number]> = {};
    for (const ch of chans) {
      const vals = ss.flatMap((s) => (s.channels[ch] ?? []).filter((v): v is number => v !== null));
      yExt[ch] = vals.length ? [Math.min(...vals), Math.max(...vals)] : [0, 1];
    }
    const grids: EChartsOption["grid"] = [];
    const xAxes: unknown[] = [];
    const yAxes: unknown[] = [];
    const series: unknown[] = [];
    const panels = multiples ? ss.length : 1;
    const rows = chans.length * panels;
    const top = 8, bottom = 28, gap = 6;
    const h = Math.max(40, (100 - top - bottom) / rows - gap);
    let g = 0;
    for (let p = 0; p < panels; p++) {
      for (const ch of chans) {
        const topPct = top + g * (h + gap);
        (grids as unknown[]).push({ left: 56, right: 16, top: `${topPct}%`, height: `${h}%` });
        xAxes.push({ type: "value", gridIndex: g, min: xMin, max: xMax, show: g === rows - 1, name: g === rows - 1 ? "s from anchor" : undefined,
          nameLocation: "middle", nameGap: 18, axisLabel: { fontSize: 10 }, splitLine: { show: false } });
        yAxes.push({ type: "value", gridIndex: g, min: yExt[ch][0], max: yExt[ch][1], name: multiples && p > 0 ? undefined : channelLabel(ch),
          nameTextStyle: { fontSize: 10, align: "left" }, axisLabel: { fontSize: 9 }, splitLine: { lineStyle: { opacity: 0.15 } }, scale: true });
        const members = multiples ? [ss[p]] : ss;
        members.forEach((s) => {
          const i = ss.indexOf(s);
          const ys = s.channels[ch];
          if (!ys) return;
          const isHi = highlight && s.slice_id === highlight;
          series.push({
            type: "line", name: s.label, xAxisIndex: g, yAxisIndex: g, showSymbol: false, smooth: false,
            lineStyle: { width: isHi ? 2.4 : 1.1, color: isHi ? "var(--brand-tint)" : colorOf(i), opacity: isHi ? 1 : multiples ? 0.95 : 0.75 },
            emphasis: { focus: "series", lineStyle: { width: 2.2 } },
            data: s.t.map((t, k) => [t, ys[k]]),
            sliceId: s.slice_id,
          });
        });
        if (multiples && ch === chans[0]) {
          // the slice label on its first strip
          series.push({ type: "line", xAxisIndex: g, yAxisIndex: g, data: [], markPoint: undefined,
            name: `${ss[p].label}`, silent: true, showSymbol: false });
        }
        g++;
      }
    }
    return {
      animation: false,
      grid: grids,
      xAxis: xAxes as EChartsOption["xAxis"],
      yAxis: yAxes as EChartsOption["yAxis"],
      series: series as EChartsOption["series"],
      // One cursor across every grid: scrubbing (§9).
      axisPointer: { link: [{ xAxisIndex: "all" }], label: { fontSize: 10 }, lineStyle: { opacity: 0.6 } },
      tooltip: { trigger: "axis", axisPointer: { type: "line" }, confine: true, textStyle: { fontSize: 11 },
        formatter: (ps: unknown) => {
          const arr = (ps as { seriesName: string; value: [number, number | null]; axisIndex: number }[]) ?? [];
          if (!arr.length) return "";
          const t = arr[0].value?.[0];
          const lines = arr.filter((p) => p.value && p.value[1] !== null).slice(0, 14)
            .map((p) => `${p.seriesName}: <b>${p.value[1]}</b>`);
          return `t = ${t} s<br/>${lines.join("<br/>")}`;
        } },
      graphic: multiples ? ss.map((s, p) => ({ type: "text", left: 62, top: `${top + p * chans.length * (h + gap) + 0.5}%`,
        style: { text: s.label, fontSize: 10, fill: "#9CA3AF" }, silent: true })) : undefined,
    } as EChartsOption;
  }, [samples, multiples, highlight]);

  const height = samples ? Math.max(220, (multiples ? samples.slices.length : 1) * samples.channels.length * 110 + 50) : 220;

  return (
    <div data-testid="aligned-view">
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", marginBottom: 8 }}>
        <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12 }}>
          <span style={MUTED}>Align on</span>
          <select value={anchor} onChange={(e) => onAnchor(e.target.value)} style={SELECT} aria-label="Alignment anchor" disabled={readOnly}>
            {ANCHORS.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </select>
        </label>
        <span style={MUTED}>Channels</span>
        {channels.map((ch) => (
          <button key={ch} type="button" onClick={() => onChannels(channels.filter((c) => c !== ch))} style={{ ...BUTTON, padding: "2px 8px", fontSize: 11 }} title="remove" disabled={readOnly}>
            {channelLabel(ch)} ×
          </button>
        ))}
        <select value="" onChange={(e) => e.target.value && onChannels([...channels, e.target.value])} style={SELECT} aria-label="Add a channel" disabled={readOnly}>
          <option value="">+ channel</option>
          {RESEARCH_CHANNELS.filter((c) => !channels.includes(c)).map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
        </select>
        <span style={{ flexGrow: 1 }} />
        <select value={mode} onChange={(e) => setMode(e.target.value as typeof mode)} style={SELECT} aria-label="View mode">
          <option value="auto">{slices.length > SMALL_MULTIPLES_ABOVE ? "small multiples (auto)" : "overlay (auto)"}</option>
          <option value="overlay">overlay</option>
          <option value="multiples">small multiples</option>
        </select>
      </div>
      {readOnly && <div style={MUTED}>The aligned view needs the flights' logs; this study's are not in this workspace.</div>}
      {!readOnly && !slices.length && <div style={MUTED}>No slices yet — add a rule or a hand slice.</div>}
      {error && <div style={{ ...MUTED, color: "var(--severity-warning)" }}>{error}</div>}
      {loading && <div style={MUTED}>Reading the slices' samples…</div>}
      {option && (
        <EChartBase option={option} height={height} />
      )}
      {samples && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
          {samples.slices.map((s, i) => {
            const info = slices.find((x) => x.slice_id === s.slice_id);
            return (
              <button key={s.slice_id} type="button" onClick={() => info && onOpenSlice?.(info)} title="open this flight at the slice"
                style={{ ...BUTTON, padding: "2px 8px", fontSize: 10, display: "inline-flex", alignItems: "center", gap: 5, borderColor: highlight === s.slice_id ? "var(--brand-tint)" : undefined }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: colorOf(i), display: "inline-block" }} />
                {s.label}{s.context.source ? ` · ${s.context.source}` : ""}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
