import { useMemo, useState } from "react";
import type { EChartsOption } from "echarts";
import { EChartBase } from "../EChartBase";
import { InlineHelp } from "../InlineHelp";
import type { ResearchTestResult, StudyTest } from "../../types/contract";
import { TEST_QUESTION, channelLabel, downloadText, fmtNum, fmtRef, tableToCsv } from "../../lib/research";
import { LINK, MUTED, PANEL, TD, TH } from "./ui";

// Spec 06 §8 (D5): every test renders the same five parts, in this order —
// Finding, Evidence (chart + per-slice table one click away, CSV export),
// Magnitude beside its reference, Caveats (with the resolved window and lag
// range), and the machine-readable block behind a disclosure. No verdict:
// the words are the engine's; the page adds labels only.

const HELP_ID: Record<string, "research.test.cycling" | "research.test.coupling" | "research.test.groups" | "research.test.unusual"> = {
  cycling: "research.test.cycling", coupling: "research.test.coupling", groups: "research.test.groups", unusual: "research.test.unusual",
};

export function TestResultCard({ test, index, onRemove, onEdit, readOnly, onOpenSlice }: {
  test: StudyTest;
  index: number;
  onRemove?: () => void;
  onEdit?: () => void;
  readOnly?: boolean;
  onOpenSlice?: (sliceId: string, flight: string) => void;
}) {
  const [showTable, setShowTable] = useState(false);
  const [showBlock, setShowBlock] = useState(false);
  const r = test.result ?? null;
  const question = TEST_QUESTION[test.test_id];

  return (
    <section style={PANEL} data-testid="test-result" data-test-id={test.test_id}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
        <span className="mono" style={MUTED}>{index + 1}</span>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{question}</span>
        <InlineHelp id={HELP_ID[test.test_id]} />
        <span style={MUTED}>
          {test.channels.length ? test.channels.map(channelLabel).join(", ") : ""}
          {test.test_id === "groups" && typeof test.params.descriptor === "string" ? ` · ${String(test.params.descriptor)}` : ""}
        </span>
        <span style={{ flexGrow: 1 }} />
        {!readOnly && onEdit && <button type="button" onClick={onEdit} style={LINK}>Change…</button>}
        {!readOnly && onRemove && <button type="button" onClick={onRemove} style={LINK}>Remove</button>}
      </div>

      {test.error && <div style={{ ...MUTED, color: "var(--severity-warning)" }}>This question could not be answered on these slices: {test.error}</div>}
      {!r && !test.error && <div style={MUTED}>Not run yet — Run the study to answer it.</div>}

      {r && (
        <>
          {/* 1. Finding */}
          <p data-testid="finding" style={{ margin: "0 0 10px", fontSize: 14, color: "var(--text-primary)", lineHeight: 1.45 }}>{r.finding}</p>

          {/* 2. Evidence */}
          <ResultChart result={r} onOpenSlice={onOpenSlice} />
          <div style={{ display: "flex", gap: 14, alignItems: "center", margin: "6px 0 10px" }}>
            <button type="button" onClick={() => setShowTable((v) => !v)} style={LINK}>
              {showTable ? "Hide" : "Show"} the per-slice table ({r.evidence.table.rows.length} slices)
            </button>
            <button type="button" onClick={() => downloadText(`${r.test_id}-evidence.csv`, tableToCsv(r), "text/csv")} style={LINK}>Download CSV</button>
          </div>
          {showTable && <EvidenceTable result={r} onOpenSlice={onOpenSlice} />}

          {/* 3. Magnitude beside its reference */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: 8, marginBottom: 10 }}>
            {r.magnitude.map((m, i) => (
              <div key={i} data-testid="magnitude" style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: "8px 12px", display: "flex", gap: 18, flexWrap: "wrap", alignItems: "baseline" }}>
                <div>
                  <div style={MUTED}>{m.label}</div>
                  <div style={{ fontSize: 16, fontWeight: 600 }}>{m.text}</div>
                  {m.spread && <div style={MUTED}>IQR {fmtNum(m.spread[0])}–{fmtNum(m.spread[1])}{m.unit ? ` ${m.unit}` : ""}</div>}
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 12 }}>
                  {m.references.map((ref, j) => (
                    <div key={j} style={{ color: "var(--text-secondary)" }}>
                      <span style={{ ...MUTED, textTransform: "uppercase", letterSpacing: 0.5, marginRight: 6 }}>{ref.kind === "om" ? "OM" : ref.kind === "set" ? "this set" : "your reference"}</span>
                      {ref.text ?? `${ref.label}: ${fmtRef(ref)}`}
                      {ref.kind === "user" && ref.source ? <span style={MUTED}> — {ref.source}</span> : null}
                    </div>
                  ))}
                  {m.references.length === 0 && <div style={MUTED}>no reference applies</div>}
                </div>
              </div>
            ))}
          </div>

          {/* 4. Caveats */}
          <ul data-testid="caveats" style={{ margin: 0, paddingLeft: 18, fontSize: 11, color: "var(--text-tertiary)", lineHeight: 1.5 }}>
            {r.caveats.map((c, i) => <li key={i}>{c}</li>)}
          </ul>

          {/* 5. The block */}
          <div style={{ marginTop: 8 }}>
            <button type="button" onClick={() => setShowBlock((v) => !v)} style={LINK}>{showBlock ? "Hide" : "Show"} the machine-readable result</button>
            {showBlock && (
              <pre className="mono" style={{ fontSize: 10, maxHeight: 260, overflow: "auto", background: "var(--bg)", padding: 10, borderRadius: 6, marginTop: 6 }}>
                {JSON.stringify({ ...r.block, per_slice: `(${r.evidence.table.rows.length} rows — in the CSV)` }, null, 2)}
              </pre>
            )}
          </div>
        </>
      )}
    </section>
  );
}

function EvidenceTable({ result, onOpenSlice }: { result: ResearchTestResult; onOpenSlice?: (sliceId: string, flight: string) => void }) {
  const cols = result.evidence.table.columns;
  const highlight = new Set(result.evidence.chart.highlight ?? []);
  return (
    <div style={{ overflowX: "auto", marginBottom: 10 }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }} data-testid="evidence-table">
        <thead><tr>{cols.map((c) => <th key={c.key} style={TH}>{c.label}{c.unit ? <span style={{ fontWeight: 400 }}> ({c.unit})</span> : null}</th>)}</tr></thead>
        <tbody>
          {result.evidence.table.rows.map((row, i) => {
            const id = String(row.slice_id ?? i);
            return (
              <tr key={id} style={{ background: highlight.has(id) ? "var(--brand-fill)" : undefined, cursor: onOpenSlice ? "pointer" : undefined }}
                onClick={() => onOpenSlice?.(id, String(row.flight ?? ""))}>
                {cols.map((c) => <td key={c.key} style={TD} className={typeof row[c.key] === "number" ? "mono" : undefined}>{fmtNum(row[c.key], 2)}</td>)}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// The chart the engine asks for (§8 Evidence). The samples-based kinds
// (aligned slices, channel stack) are the study page's AlignedView; here a
// result draws the per-slice numbers it carries: distributions for cycling,
// coupling and groups, a ranked bar for unusual.
function ResultChart({ result, onOpenSlice }: { result: ResearchTestResult; onOpenSlice?: (sliceId: string, flight: string) => void }) {
  const option = useMemo<EChartsOption | null>(() => {
    const rows = result.evidence.table.rows;
    const chart = result.evidence.chart;
    if (!rows.length) return null;
    if (chart.kind === "ranked") {
      const col = chart.descriptor_column ?? "descriptor";
      const top = rows.slice(0, 25);
      return {
        animation: false, grid: { left: 150, right: 24, top: 10, bottom: 28 },
        xAxis: { type: "value", name: "robust z", nameLocation: "middle", nameGap: 16, axisLabel: { fontSize: 10 } },
        yAxis: { type: "category", inverse: true, data: top.map((r) => `${String(r.start_time ?? r.label ?? "").slice(0, 16)}  ${String(r[col] ?? "")}`), axisLabel: { fontSize: 9 } },
        tooltip: { trigger: "item", textStyle: { fontSize: 11 } },
        series: [{ type: "bar", data: top.map((r) => ({ value: Number(r.z ?? r.robust_z ?? 0), slice_id: r.slice_id, flight: r.flight,
          itemStyle: { color: (chart.highlight ?? []).includes(String(r.slice_id)) ? "#F472B6" : "#38BDF8" } })), barMaxWidth: 12 }],
      } as EChartsOption;
    }
    // Distributions: one scatter column per group (or per source), the
    // descriptor on y. cycling → swing; coupling → corr0; groups → the descriptor.
    const yKey = chart.kind === "distributions" ? (chart.descriptor?.split(".").pop() ?? "value")
      : chart.distribution?.descriptor ?? (result.test_id === "coupling" ? "corr0" : "swing");
    const groupKey = chart.kind === "distributions" ? (chart.group_by ?? "group") : "source";
    const groups = [...new Set(rows.map((r) => String(r[groupKey] ?? "all")))];
    const unit = result.evidence.table.columns.find((c) => c.key === yKey)?.unit;
    return {
      animation: false, grid: { left: 56, right: 16, top: 12, bottom: 30 },
      xAxis: { type: "category", data: groups, axisLabel: { fontSize: 10, interval: 0 } },
      yAxis: { type: "value", name: `${yKey}${unit ? ` (${unit})` : ""}`, nameTextStyle: { fontSize: 10, align: "left" }, axisLabel: { fontSize: 10 }, scale: true, splitLine: { lineStyle: { opacity: 0.15 } } },
      tooltip: { trigger: "item", textStyle: { fontSize: 11 }, formatter: (p: unknown) => {
        const d = (p as { data: { label?: string; value: [string, number] } }).data;
        return `${d.label ?? ""}<br/>${yKey}: <b>${d.value[1]}</b>`;
      } },
      series: [{ type: "scatter", symbolSize: 7,
        data: rows.filter((r) => typeof r[yKey] === "number").map((r) => ({
          value: [String(r[groupKey] ?? "all"), r[yKey] as number], label: String(r.start_time ?? r.label ?? "").slice(0, 16), slice_id: r.slice_id, flight: r.flight,
          itemStyle: { opacity: 0.8, color: (chart.highlight ?? []).includes(String(r.slice_id)) ? "#F472B6" : "#38BDF8" } })),
      }],
    } as EChartsOption;
  }, [result]);
  if (!option) return null;
  return (
    <div data-testid="result-chart">
      <EChartBase option={option} height={200} onPointClick={(d: { slice_id?: string; flight?: string }) => d?.slice_id && onOpenSlice?.(d.slice_id, d.flight ?? "")} />
    </div>
  );
}

