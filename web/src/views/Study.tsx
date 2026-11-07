import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { InlineHelp } from "../components/InlineHelp";
import { EngineRpcError, getEngineClient, type FlightSummary, type SliceBuildArgs } from "../lib/engineClient";
import type {
  HandSlice, ResearchProgress, ResearchTestId, SliceInfo, SlicePresets, SliceRule, SliceSetResult, Study as StudyDoc, StudySelection,
  StudySplit, StudyTest, UserReference,
} from "../types/contract";
import { AlignedView } from "../components/research/AlignedView";
import { SliceRuleEditor, describeRule } from "../components/research/SliceRuleEditor";
import { TestResultCard } from "../components/research/TestResultCard";
import { BODY, BUTTON, CHIP, INPUT, LINK, MUTED, NOTICE, PANEL, PANEL_TITLE, PRIMARY, SELECT } from "../components/research/ui";
import {
  DESCRIPTOR_NAMES, RESEARCH_CHANNELS, RESEARCH_TESTS, channelLabel, describeSelection, downloadText, fmtClock, takeStudySeed,
  type StudySeed,
} from "../lib/research";

const client = getEngineClient();

// Spec 06 §12 — the study page, top to bottom: selection → slice rules and
// hand slices (slice count live) → aligned view → tests (each in the §8
// contract) → references and notes → actions. Every number comes from the
// host (§11). A read-only study (§10.2, Q5) shows the sender's results
// under an unmistakable label, with one action: Run this on my flights.

type Draft = Omit<StudyDoc, "study_id" | "created" | "updated"> & { study_id: string | null; slice_rules: SliceRule[] };

function blankDraft(): Draft {
  return {
    study_id: null, name: "New study", selection: { mode: "all", split: null }, slice_rules: [], hand_slices: [],
    references: [], tests: [], windows: {}, view: { anchor: "crossing", channels: ["rpm", "map_inhg", "fuel_flow_gph"] },
    notes: "", provenance: {},
  };
}

function fromDoc(d: StudyDoc): Draft {
  return { ...d, slice_rules: d.slice_rules ?? [], hand_slices: d.hand_slices ?? [], references: d.references ?? [], tests: d.tests ?? [],
    view: d.view ?? { anchor: "crossing", channels: ["rpm", "map_inhg", "fuel_flow_gph"] }, notes: d.notes ?? "", windows: d.windows ?? {} };
}

function toSave(d: Draft, presetIds: string[] = []): Omit<Partial<StudyDoc>, "slice_rules"> & { slice_rules: (SliceRule | string)[] } {
  return {
    ...(d.study_id ? { study_id: d.study_id } : {}),
    name: d.name, selection: d.selection, slice_rules: [...d.slice_rules, ...presetIds], hand_slices: d.hand_slices,
    references: d.references, tests: d.tests.map((t) => ({ test_id: t.test_id, params: t.params, channels: t.channels })),
    windows: d.windows, view: d.view, notes: d.notes, provenance: d.provenance,
  };
}

function buildArgs(d: Draft, presetIds: string[]): SliceBuildArgs {
  return { ...(d.study_id ? { study_id: d.study_id } : {}), selection: d.selection, slice_rules: [...d.slice_rules, ...presetIds],
    hand_slices: d.hand_slices, channels: d.view.channels ?? ["rpm"] };
}

export function Study() {
  const { studyId } = useParams();
  const navigate = useNavigate();
  const isNew = !studyId || studyId === "new";

  const [draft, setDraft] = useState<Draft | null>(null);
  const [pendingPresets, setPendingPresets] = useState<string[]>([]); // preset ids not yet resolved into rules
  const [suggestedPreset, setSuggestedPreset] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [presets, setPresets] = useState<SlicePresets | null>(null);
  const [flights, setFlights] = useState<FlightSummary[]>([]);
  const [sliceSet, setSliceSet] = useState<SliceSetResult | null>(null);
  const [building, setBuilding] = useState(false);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<ResearchProgress>({ active: false });
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editingRule, setEditingRule] = useState<SliceRule | null>(null);
  const [addingTest, setAddingTest] = useState<StudyTest | null>(null);
  const [editingTest, setEditingTest] = useState<number | null>(null);
  const [highlightSlice, setHighlightSlice] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const buildSeq = useRef(0);

  const readOnly = !!draft?.read_only;

  // Load: a saved study, or a new one from a seed / blank.
  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const [p, fl] = await Promise.all([client.listSlicePresets(), client.listFlights().catch(() => [] as FlightSummary[])]);
        if (!live) return;
        setPresets(p);
        setFlights(fl);
        if (isNew) {
          const seed = takeStudySeed();
          setDraft(seed ? applySeed(seed) : blankDraft());
          setPendingPresets(seed ? seed.slice_rules.filter((r): r is string => typeof r === "string") : []);
          setSuggestedPreset(seed?.suggested_preset ?? null);
          setDirty(true);
        } else {
          const doc = await client.loadStudy(studyId!);
          if (!live) return;
          setDraft(fromDoc(doc));
        }
      } catch (e) {
        if (!live) return;
        setError(e instanceof EngineRpcError && e.code === "NO_ACTIVE_WORKSPACE" ? "Open a workspace first." : e instanceof Error ? e.message : String(e));
        setDraft(blankDraft());
      }
    })();
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [studyId]);

  // Progress polling while a build or run is in flight.
  useEffect(() => {
    if (!building && !running) { setProgress({ active: false }); return; }
    const id = setInterval(() => { client.getResearchProgress().then(setProgress).catch(() => undefined); }, 400);
    return () => clearInterval(id);
  }, [building, running]);

  // Live slice count: rebuild when the definition changes (debounced).
  const defKey = draft ? JSON.stringify([draft.selection, draft.slice_rules, pendingPresets, draft.hand_slices, draft.view.channels]) : "";
  const builtKey = useRef<string>("");
  useEffect(() => {
    if (!draft || readOnly || (!draft.slice_rules.length && !pendingPresets.length && !draft.hand_slices.length)) { setSliceSet(null); return; }
    // The build that resolved presets into rules already describes this
    // definition — don't pay a second pass for the same slices.
    if (defKey === builtKey.current) return;
    const seq = ++buildSeq.current;
    const t = setTimeout(async () => {
      setBuilding(true);
      try {
        const res = await client.buildSlices(buildArgs(draft, pendingPresets));
        if (seq !== buildSeq.current) return;
        setSliceSet(res);
        // Presets come back as full rules — keep them in the draft so the
        // study stores the rule, not the preset name (§3.2).
        if (pendingPresets.length) {
          builtKey.current = JSON.stringify([draft.selection, res.rules, [], draft.hand_slices, draft.view.channels]);
          setDraft((d) => d && ({ ...d, slice_rules: res.rules }));
          setPendingPresets([]);
        } else {
          builtKey.current = defKey;
        }
        setError(null);
      } catch (e) {
        if (seq === buildSeq.current) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (seq === buildSeq.current) setBuilding(false);
      }
    }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defKey, readOnly]);

  const update = useCallback((patch: Partial<Draft> | ((d: Draft) => Partial<Draft>)) => {
    setDraft((d) => (d ? { ...d, ...(typeof patch === "function" ? patch(d) : patch) } : d));
    setDirty(true);
  }, []);

  async function save(): Promise<StudyDoc | null> {
    if (!draft) return null;
    try {
      const saved = await client.saveStudy(toSave(draft, pendingPresets));
      setPendingPresets([]);
      // The saved rules are the ones just built (normalised by the host):
      // keep the slice set rather than building the same slices again.
      if (sliceSet && !pendingPresets.length) builtKey.current = JSON.stringify([saved.selection, saved.slice_rules, [], saved.hand_slices, draft.view.channels]);
      setDraft((d) => d && ({ ...fromDoc(saved), view: d.view }));
      setDirty(false);
      if (isNew) navigate(`/research/${saved.study_id}`, { replace: true });
      return saved;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    }
  }

  async function run() {
    const saved = dirty || !draft?.study_id ? await save() : null;
    const id = saved?.study_id ?? draft?.study_id;
    if (!id) return;
    setRunning(true);
    setError(null);
    try {
      const doc = await client.runStudy(id);
      if (sliceSet) builtKey.current = JSON.stringify([doc.selection, doc.slice_rules, [], doc.hand_slices, draft!.view.channels]);
      setDraft((d) => d && ({ ...fromDoc(doc), view: d.view }));
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  async function exportStudy() {
    if (!draft?.study_id) { const s = await save(); if (!s) return; }
    const id = draft!.study_id!;
    try {
      const res = await client.exportStudy(id);
      const a = document.createElement("a");
      a.href = client.downloadUrl(res.download_url);
      a.download = res.filename;
      a.click();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  // §10.3 evidence package: the findings, magnitudes, caveats and every
  // per-slice table, as one Markdown file a manufacturer or mechanic can
  // read; the charts travel in the .eisstudy export.
  function evidencePackage() {
    if (!draft) return;
    const lines: string[] = [`# ${draft.name}`, "", `Selection: ${describeSelection(draft.selection, flights.length)}.`,
      ...draft.slice_rules.map((r) => `Slice rule: ${r.name} — ${describeRule(r)}.`),
      ...draft.hand_slices.map((h) => `Hand slice: ${h.label} (${fmtClock(h.start_s)}–${fmtClock(h.end_s)}).`), ""];
    draft.tests.forEach((t, i) => {
      const r = t.result;
      lines.push(`## ${i + 1}. ${r?.question ?? t.test_id}`, "");
      if (!r) { lines.push(t.error ? `Could not run: ${t.error}` : "Not run.", ""); return; }
      lines.push(r.finding, "");
      for (const m of r.magnitude) {
        lines.push(`- **${m.label}:** ${m.text}`);
        for (const ref of m.references) lines.push(`  - ${ref.kind === "om" ? "OM" : ref.kind === "set" ? "this set" : "reference"}: ${ref.text ?? ref.label}${ref.source ? ` (${ref.source})` : ""}`);
      }
      lines.push("", "Caveats:", ...r.caveats.map((c) => `- ${c}`), "", "Per-slice table (CSV):", "", "```csv");
      const cols = r.evidence.table.columns;
      lines.push(cols.map((c) => (c.unit ? `${c.label} (${c.unit})` : c.label)).join(","));
      for (const row of r.evidence.table.rows) lines.push(cols.map((c) => String(row[c.key] ?? "")).join(","));
      lines.push("```", "");
    });
    if (draft.notes) lines.push("## Notes", "", draft.notes, "");
    lines.push(`_Produced by SlingologyEIS Research; the aligned charts are in the study's .eisstudy export._`);
    downloadText(`${draft.name.replace(/[^A-Za-z0-9._ -]+/g, "").trim().replace(/ /g, "-") || "study"}-evidence.md`, lines.join("\n"), "text/markdown");
  }

  async function noteInJournal(i: number) {
    if (!draft?.study_id) return;
    try {
      await client.noteStudyFinding(draft.study_id, i);
      setNotice("Noted in the Journal.");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function deleteStudy() {
    if (!draft?.study_id) { navigate("/research"); return; }
    try {
      await client.deleteStudy(draft.study_id);
      navigate("/research");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  async function runOnMyFlights() {
    if (!draft?.study_id) return;
    setRunning(true);
    try {
      const doc = await client.runStudyOnMyFlights(draft.study_id);
      navigate(`/research/${doc.study_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  function openSlice(s: SliceInfo) {
    navigate(`/flights/${encodeURIComponent(s.flight)}?window=${s.start_s}-${s.end_s}`);
  }
  function openSliceById(sliceId: string, flight: string) {
    const s = sliceSet?.slices.find((x) => x.slice_id === sliceId);
    if (s) openSlice(s);
    else if (flight) navigate(`/flights/${encodeURIComponent(flight)}`);
  }

  const flightById = useMemo(() => new Map(flights.map((f) => [f.flight_id, f])), [flights]);
  const flightLabel = (id: string) => { const f = flightById.get(id); return f ? `${f.header.date}${f.source_filename ? ` · ${f.source_filename}` : ""}` : id; };

  if (!draft) {
    return <NavShell><div style={{ padding: 24, ...MUTED }}>{error ?? "Loading…"}</div></NavShell>;
  }

  const slices = sliceSet?.slices ?? [];
  const canRun = !readOnly && (draft.slice_rules.length + pendingPresets.length + draft.hand_slices.length) > 0 && draft.tests.length > 0 && !running;

  return (
    <NavShell right={progress.active ? <span style={CHIP}>reading flights {progress.done ?? 0}/{progress.total ?? "…"}</span> : undefined}>
      <div style={{ width: "100%", overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 14 }} data-testid="study-page">
        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <button type="button" onClick={() => navigate("/research")} style={LINK}>← Research</button>
          <input value={draft.name} onChange={(e) => update({ name: e.target.value })} disabled={readOnly} aria-label="Study name"
            style={{ ...INPUT, fontSize: 18, fontWeight: 700, padding: "4px 8px", minWidth: 320, background: "transparent", border: "1px solid transparent" }}
            onFocus={(e) => (e.currentTarget.style.borderColor = "var(--border)")} onBlur={(e) => (e.currentTarget.style.borderColor = "transparent")} />
          {dirty && !readOnly && <span style={MUTED}>unsaved</span>}
          <span style={{ flexGrow: 1 }} />
          {!readOnly && (
            <>
              <button type="button" onClick={() => void save()} style={BUTTON} disabled={!dirty && !!draft.study_id}>Save</button>
              <button type="button" onClick={() => void run()} style={{ ...PRIMARY, opacity: canRun ? 1 : 0.5 }} disabled={!canRun} data-testid="run-study">
                {running ? "Running…" : "Run"}
              </button>
            </>
          )}
          <button type="button" onClick={evidencePackage} style={BUTTON} disabled={!draft.tests.some((t) => t.result)} title="findings, magnitudes, caveats and the per-slice tables as one file">Evidence package</button>
          <button type="button" onClick={() => void exportStudy()} style={BUTTON} disabled={!draft.study_id && readOnly}>Export .eisstudy</button>
          {draft.study_id && (confirmDelete
            ? <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}><span style={MUTED}>Delete this study?</span><button type="button" onClick={() => void deleteStudy()} style={{ ...BUTTON, color: "var(--severity-limit)" }}>Delete</button><button type="button" onClick={() => setConfirmDelete(false)} style={BUTTON}>Keep</button></span>
            : <button type="button" onClick={() => setConfirmDelete(true)} style={LINK}>Delete</button>)}
        </div>

        {readOnly && (
          <div data-testid="read-only-banner" style={{ ...NOTICE, display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", borderColor: "var(--severity-watch)" }}>
            <strong style={{ color: "var(--severity-watch)" }}>Sender's results — none of these flights are in this workspace.</strong>
            <span style={BODY}>The numbers below describe the sender's engine, not yours. The rules, references and questions can be run on your own flights.</span>
            <span style={{ flexGrow: 1 }} />
            <button type="button" onClick={() => void runOnMyFlights()} style={PRIMARY} disabled={running} data-testid="run-on-my-flights">{running ? "Running…" : "Run this on my flights"}</button>
          </div>
        )}
        {draft.imported && !readOnly && (
          <div style={NOTICE}>Imported study: {draft.imported.matched.length} of {draft.imported.matched.length + draft.imported.missing.length} of the sender's flights are in this workspace; the results are recomputed from yours.</div>
        )}
        {error && <div style={{ ...NOTICE, color: "var(--severity-warning)" }}>{error} <button type="button" onClick={() => setError(null)} style={LINK}>dismiss</button></div>}
        {notice && <div style={NOTICE}>{notice} <button type="button" onClick={() => setNotice(null)} style={LINK}>ok</button></div>}

        {/* Selection */}
        <section style={PANEL}>
          <div style={PANEL_TITLE}>Flights <InlineHelp id="research.selection" /><span style={MUTED}>{describeSelection(draft.selection, flights.length)}</span></div>
          <SelectionEditor selection={draft.selection} flights={flights} readOnly={readOnly} onChange={(selection) => update({ selection })} />
        </section>

        {/* Slice rules and hand slices */}
        <section style={PANEL}>
          <div style={PANEL_TITLE}>
            Slices <InlineHelp id="research.slice_rule" />
            <span style={MUTED} data-testid="slice-count">
              {building ? "counting…" : sliceSet ? `${sliceSet.count} slice${sliceSet.count === 1 ? "" : "s"} from ${sliceSet.flights_with_slices} of ${sliceSet.flights_selected} flights`
                + (Object.keys(sliceSet.by_source).length > 1 ? ` (${Object.entries(sliceSet.by_source).map(([k, v]) => `${v} ${k}`).join(", ")})` : "")
                : readOnly && draft.last_run ? `${draft.last_run.slices} slices in the sender's run` : "no rule yet"}
            </span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {draft.slice_rules.map((r) => (
              <div key={r.rule_id} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }} data-testid="slice-rule">
                <span style={{ fontWeight: 600 }}>{r.name}</span>
                <span style={BODY}>{describeRule(r)}</span>
                {r.from_preset && <span style={CHIP}>from preset</span>}
                <span style={{ flexGrow: 1 }} />
                {!readOnly && <button type="button" onClick={() => setEditingRule(r)} style={LINK}>Edit…</button>}
                {!readOnly && <button type="button" onClick={() => update((d) => ({ slice_rules: d.slice_rules.filter((x) => x.rule_id !== r.rule_id) }))} style={LINK}>Remove</button>}
              </div>
            ))}
            {pendingPresets.map((p) => <div key={p} style={BODY} data-testid="slice-rule">preset {p} (resolving…)</div>)}
            {draft.hand_slices.map((h, i) => (
              <div key={`${h.flight}-${h.start_s}-${i}`} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12 }} data-testid="hand-slice">
                <span style={{ fontWeight: 600 }}>{h.label}</span>
                <span style={BODY}>{flightLabel(h.flight)} · {fmtClock(h.start_s)}–{fmtClock(h.end_s)} by hand</span>
                <span style={{ flexGrow: 1 }} />
                <button type="button" onClick={() => setHighlightSlice(`${h.flight}:hand:${h.start_s}-${h.end_s}`)} style={LINK}>Highlight</button>
                {!readOnly && <button type="button" onClick={() => update((d) => ({ hand_slices: d.hand_slices.filter((_, j) => j !== i) }))} style={LINK}>Remove</button>}
              </div>
            ))}
          </div>
          {suggestedPreset && !readOnly && !draft.slice_rules.some((r) => r.from_preset === suggestedPreset) && (
            <div style={{ ...NOTICE, marginTop: 10, display: "flex", gap: 10, alignItems: "center" }}>
              <span>This window covers a takeoff. Compare it with every takeoff?</span>
              <button type="button" onClick={() => { setPendingPresets((p) => [...p, suggestedPreset]); setSuggestedPreset(null); setDirty(true); }} style={BUTTON} data-testid="add-suggested-preset">Add the full-power rule</button>
              <button type="button" onClick={() => setSuggestedPreset(null)} style={LINK}>No</button>
            </div>
          )}
          {!readOnly && (
            <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 10, flexWrap: "wrap" }}>
              <select value="" onChange={(e) => { const id = e.target.value; if (!id) return; setPendingPresets((p) => [...p, id]); setDirty(true); }} style={SELECT} aria-label="Add a preset" data-testid="add-preset">
                <option value="">+ preset…</option>
                {presets?.presets.map((p) => <option key={p.rule_id} value={p.rule_id}>{p.name}</option>)}
              </select>
              <select value="" onChange={(e) => { const id = e.target.value; if (!id) return; setPendingPresets((p) => [...p, id]); setDirty(true); }} style={SELECT} aria-label="Add a phase slice">
                <option value="">+ phase…</option>
                {presets?.phase_rules.map((p) => <option key={p.rule_id} value={p.rule_id}>{p.name}</option>)}
              </select>
              <button type="button" onClick={() => setEditingRule({ rule_id: `r-${Date.now().toString(36)}`, name: "New rule", conditions: [{ channel: "rpm", op: ">=", value: 5000 }], min_duration_s: 10, merge_gap_s: 2, pad_s: 0, phase: null })} style={BUTTON}>+ Rule…</button>
              <HandSliceAdder flights={flights} onAdd={(h) => update((d) => ({ hand_slices: [...d.hand_slices, h] }))} />
            </div>
          )}
          {editingRule && (
            <div style={{ marginTop: 10 }}>
              <SliceRuleEditor initial={editingRule} onCancel={() => setEditingRule(null)}
                onSave={(rule) => { update((d) => ({ slice_rules: d.slice_rules.some((x) => x.rule_id === rule.rule_id) ? d.slice_rules.map((x) => (x.rule_id === rule.rule_id ? rule : x)) : [...d.slice_rules, rule] })); setEditingRule(null); }} />
            </div>
          )}
          {sliceSet && sliceSet.missing_flights.length > 0 && <div style={{ ...MUTED, marginTop: 6 }}>{sliceSet.missing_flights.length} selected flight{sliceSet.missing_flights.length === 1 ? " is" : "s are"} not in this workspace and contribute{sliceSet.missing_flights.length === 1 ? "s" : ""} no slices.</div>}
          {sliceSet && sliceSet.unreachable_flights.length > 0 && <div style={{ ...MUTED, marginTop: 6 }}>{sliceSet.unreachable_flights.length} flight log{sliceSet.unreachable_flights.length === 1 ? "" : "s"} could not be read right now.</div>}
          {presets?.note && <div style={{ ...MUTED, marginTop: 6 }}>{presets.note}</div>}
        </section>

        {/* Aligned view */}
        <section style={PANEL}>
          <div style={PANEL_TITLE}>Aligned view</div>
          <AlignedView build={buildArgs(draft, pendingPresets)} slices={slices} channels={draft.view.channels ?? ["rpm"]} anchor={draft.view.anchor ?? "crossing"}
            onChannels={(channels) => update((d) => ({ view: { ...d.view, channels } }))} onAnchor={(anchor) => update((d) => ({ view: { ...d.view, anchor } }))}
            highlight={highlightSlice} onOpenSlice={openSlice} readOnly={readOnly} />
        </section>

        {/* Tests */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 13, fontWeight: 600 }}>Questions</span>
          {!readOnly && !addingTest && (
            <select value="" onChange={(e) => { const id = e.target.value as ResearchTestId; if (id) setAddingTest(defaultTest(id, draft)); }} style={SELECT} aria-label="Add a question" data-testid="add-question">
              <option value="">+ ask a question…</option>
              {RESEARCH_TESTS.map((t) => <option key={t.id} value={t.id}>{t.question}</option>)}
            </select>
          )}
        </div>
        {addingTest && (
          <TestEditor test={addingTest} selection={draft.selection} onCancel={() => setAddingTest(null)}
            onSave={(t) => { update((d) => ({ tests: [...d.tests, t] })); setAddingTest(null); }} />
        )}
        {draft.tests.map((t, i) => (
          editingTest === i
            ? <TestEditor key={i} test={t} selection={draft.selection} onCancel={() => setEditingTest(null)}
                onSave={(nt) => { update((d) => ({ tests: d.tests.map((x, j) => (j === i ? { ...nt, result: undefined, error: undefined } : x)) })); setEditingTest(null); }} />
            : (
              <div key={i}>
                <TestResultCard test={t} index={i} readOnly={readOnly} onOpenSlice={openSliceById}
                  onEdit={() => setEditingTest(i)} onRemove={() => update((d) => ({ tests: d.tests.filter((_, j) => j !== i) }))} />
                {t.result && draft.study_id && !readOnly && (
                  <div style={{ marginTop: 4, textAlign: "right" }}>
                    <button type="button" onClick={() => void noteInJournal(i)} style={LINK}>Note this finding in the Journal</button>
                  </div>
                )}
              </div>
            )
        ))}
        {draft.tests.length === 0 && !addingTest && <div style={{ ...PANEL, ...BODY }}>No question yet. Add one above, then Run.</div>}

        {/* References and notes */}
        <section style={PANEL}>
          <div style={PANEL_TITLE}>Your references <InlineHelp id="research.reference" /></div>
          <ReferencesEditor references={draft.references} readOnly={readOnly} onChange={(references) => update({ references })} />
          <div style={{ ...PANEL_TITLE, marginTop: 14 }}>Notes</div>
          <textarea value={draft.notes} onChange={(e) => update({ notes: e.target.value })} disabled={readOnly} rows={4} aria-label="Notes"
            style={{ ...INPUT, width: "100%", resize: "vertical", fontFamily: "inherit" }} placeholder="What you were looking for, what you found, whom you sent it to…" />
          {draft.provenance && Object.keys(draft.provenance).length > 0 && (
            <div style={{ ...MUTED, marginTop: 6 }}>Provenance: {Object.entries(draft.provenance).map(([k, v]) => `${k}: ${String(v)}`).join(" · ")}</div>
          )}
        </section>
      </div>
    </NavShell>
  );
}

function applySeed(seed: StudySeed): Draft {
  return { ...blankDraft(), name: seed.name, selection: seed.selection, slice_rules: seed.slice_rules.filter((r): r is SliceRule => typeof r !== "string"),
    hand_slices: seed.hand_slices, tests: seed.tests, references: seed.references ?? [], notes: seed.notes ?? "",
    view: { ...blankDraft().view, ...(seed.view ?? {}) }, provenance: { started_from: seed.from } };
}

function defaultTest(id: ResearchTestId, d: Draft): StudyTest {
  const first = d.view.channels?.[0] ?? "rpm";
  switch (id) {
    case "cycling": return { test_id: id, params: {}, channels: [first] };
    case "coupling": return { test_id: id, params: {}, channels: ["rpm", first === "rpm" ? "map_inhg" : first] };
    case "groups": return { test_id: id, params: { descriptor: `${first}.median` }, channels: [first] };
    case "unusual": return { test_id: id, params: {}, channels: [] };
  }
}

// ── Selection ──────────────────────────────────────────────────────────────

function SelectionEditor({ selection, flights, readOnly, onChange }: { selection: StudySelection; flights: FlightSummary[]; readOnly: boolean; onChange: (s: StudySelection) => void }) {
  const [pick, setPick] = useState(false);
  const split = selection.split ?? null;
  const by = split?.by ?? "";
  function setSplit(b: string) {
    if (!b) return onChange({ ...selection, split: null });
    const next: StudySplit = b === "date" ? { by: "date", date: new Date().toISOString().slice(0, 10) }
      : b === "flights" ? { by: "flights", groups: [{ label: "group A", flights: [] }, { label: "group B", flights: [] }] }
      : b === "source" || b === "rule" ? { by: b } : { by: b as "da_band" | "oat_band" | "engine_hours" };
    onChange({ ...selection, split: next });
  }
  const chosen = new Set(selection.flights ?? []);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 12 }}>
        <label><input type="radio" checked={selection.mode === "all"} disabled={readOnly} onChange={() => onChange({ ...selection, mode: "all", flights: undefined })} /> all flights</label>
        <label><input type="radio" checked={selection.mode === "flights"} disabled={readOnly} onChange={() => { onChange({ ...selection, mode: "flights", flights: selection.flights ?? [] }); setPick(true); }} /> chosen flights</label>
        {selection.mode === "flights" && !readOnly && <button type="button" onClick={() => setPick((v) => !v)} style={LINK}>{pick ? "done" : `pick… (${chosen.size})`}</button>}
        <span style={{ flexGrow: 1 }} />
        <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span style={MUTED}>split by</span>
          <select value={by} onChange={(e) => setSplit(e.target.value)} style={SELECT} disabled={readOnly} aria-label="Split by">
            <option value="">no split</option>
            <option value="da_band">density-altitude band</option>
            <option value="oat_band">OAT band</option>
            <option value="source">log source</option>
            <option value="date">before / after a date</option>
            <option value="engine_hours">engine hours</option>
            <option value="rule">slice rule</option>
            <option value="flights">two groups of flights</option>
          </select>
        </label>
        {split?.by === "date" && <input type="date" value={split.date} disabled={readOnly} onChange={(e) => onChange({ ...selection, split: { by: "date", date: e.target.value } })} style={INPUT} aria-label="Split date" />}
        {split && (split.by === "da_band" || split.by === "oat_band" || split.by === "engine_hours") && (
          <input value={(split.edges ?? []).join(", ")} placeholder="edges, e.g. 3500, 6000 (blank = fleet bands)" disabled={readOnly}
            onChange={(e) => onChange({ ...selection, split: { by: split.by, edges: e.target.value.split(",").map((x) => Number(x.trim())).filter((x) => !isNaN(x) && x !== 0) } })}
            style={{ ...INPUT, width: 260 }} aria-label="Band edges" />
        )}
      </div>
      {split?.by === "flights" && (
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          {split.groups.map((g, gi) => (
            <div key={gi} style={{ flex: 1, minWidth: 220, background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: 8 }}>
              <input value={g.label} disabled={readOnly} onChange={(e) => onChange({ ...selection, split: { by: "flights", groups: split.groups.map((x, j) => (j === gi ? { ...x, label: e.target.value } : x)) } })} style={{ ...INPUT, width: "100%", marginBottom: 6 }} aria-label="Group label" />
              <div style={MUTED}>{g.flights.length} flight{g.flights.length === 1 ? "" : "s"}</div>
              {!readOnly && (
                <div style={{ maxHeight: 140, overflowY: "auto", marginTop: 4 }}>
                  {flights.map((f) => (
                    <label key={f.flight_id} style={{ display: "block", fontSize: 11 }}>
                      <input type="checkbox" checked={g.flights.includes(f.flight_id)}
                        onChange={(e) => onChange({ ...selection, split: { by: "flights", groups: split.groups.map((x, j) => (j === gi ? { ...x, flights: e.target.checked ? [...x.flights, f.flight_id] : x.flights.filter((id) => id !== f.flight_id) } : x)) } })} />
                      {" "}{f.header.date} <span style={MUTED}>{f.source_filename}</span>
                    </label>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {selection.mode === "flights" && pick && !readOnly && (
        <div style={{ maxHeight: 220, overflowY: "auto", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 8, padding: 8 }} data-testid="flight-picker">
          {flights.map((f) => (
            <label key={f.flight_id} style={{ display: "block", fontSize: 11 }}>
              <input type="checkbox" checked={chosen.has(f.flight_id)}
                onChange={(e) => onChange({ ...selection, flights: e.target.checked ? [...chosen, f.flight_id] : [...chosen].filter((id) => id !== f.flight_id) })} />
              {" "}{f.header.date} <span style={MUTED}>{f.source_filename}</span>
            </label>
          ))}
          {flights.length === 0 && <div style={MUTED}>No flights in this workspace.</div>}
        </div>
      )}
    </div>
  );
}

// ── Hand slice (§5.4 minimum: a flight and a window; the chart's zoom on
// Flight view fills this in through "Research this") ────────────────────────

function HandSliceAdder({ flights, onAdd }: { flights: FlightSummary[]; onAdd: (h: HandSlice) => void }) {
  const [open, setOpen] = useState(false);
  const [flight, setFlight] = useState("");
  const [start, setStart] = useState("0");
  const [end, setEnd] = useState("60");
  if (!open) return <button type="button" onClick={() => setOpen(true)} style={BUTTON}>+ Hand slice…</button>;
  const f = flights.find((x) => x.flight_id === flight);
  const ok = !!f && Number(end) > Number(start);
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center", flexWrap: "wrap" }} data-testid="hand-slice-adder">
      <select value={flight} onChange={(e) => setFlight(e.target.value)} style={SELECT} aria-label="Flight">
        <option value="">flight…</option>
        {flights.map((x) => <option key={x.flight_id} value={x.flight_id}>{x.header.date} · {x.source_filename}</option>)}
      </select>
      <span style={MUTED}>from</span><input type="number" min={0} value={start} onChange={(e) => setStart(e.target.value)} style={{ ...INPUT, width: 70 }} aria-label="Start (s)" />
      <span style={MUTED}>to</span><input type="number" min={1} value={end} onChange={(e) => setEnd(e.target.value)} style={{ ...INPUT, width: 70 }} aria-label="End (s)" />
      <span style={MUTED}>s into the log</span>
      <button type="button" disabled={!ok} style={{ ...PRIMARY, opacity: ok ? 1 : 0.5 }}
        onClick={() => { onAdd({ flight, start_s: Number(start), end_s: Number(end), label: `${f!.header.date} ${fmtClock(Number(start))}`, offset_s: 0 }); setOpen(false); }}>Add</button>
      <button type="button" onClick={() => setOpen(false)} style={LINK}>cancel</button>
    </span>
  );
}

// ── Test editor: the question's channels and parameters ────────────────────

function TestEditor({ test, selection, onSave, onCancel }: { test: StudyTest; selection: StudySelection; onSave: (t: StudyTest) => void; onCancel: () => void }) {
  const [channels, setChannels] = useState<string[]>(test.channels);
  const [descriptor, setDescriptor] = useState<string>(typeof test.params.descriptor === "string" ? test.params.descriptor : `${test.channels[0] ?? "rpm"}.median`);
  const q = RESEARCH_TESTS.find((t) => t.id === test.test_id)!;
  const [descCh, descName] = descriptor.split(".");
  const pick = (label: string, value: string, onChange: (v: string) => void, exclude: string[] = []) => (
    <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
      <span style={MUTED}>{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)} style={SELECT} aria-label={label}>
        {RESEARCH_CHANNELS.filter((c) => !exclude.includes(c) || c === value).map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
      </select>
    </label>
  );
  return (
    <section style={{ ...PANEL, border: "1px solid var(--border)" }} data-testid="test-editor">
      <div style={PANEL_TITLE}>{q.question} <span style={MUTED}>— needs {q.needs}</span></div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        {test.test_id === "cycling" && pick("Channel", channels[0] ?? "rpm", (v) => setChannels([v]))}
        {test.test_id === "coupling" && (
          <>
            {pick("Reference channel", channels[0] ?? "rpm", (v) => setChannels([v, ...channels.slice(1).filter((c) => c !== v)]))}
            {channels.slice(1).map((c, i) => (
              <span key={c} style={CHIP}>{channelLabel(c)} <button type="button" onClick={() => setChannels(channels.filter((_, j) => j !== i + 1))} style={LINK}>×</button></span>
            ))}
            <select value="" onChange={(e) => e.target.value && setChannels([...channels, e.target.value])} style={SELECT} aria-label="Add a channel to compare">
              <option value="">+ channel that may follow</option>
              {RESEARCH_CHANNELS.filter((c) => !channels.includes(c)).map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
            </select>
          </>
        )}
        {test.test_id === "groups" && (
          <>
            {pick("Channel", descCh, (v) => setDescriptor(`${v}.${descName}`))}
            <label style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12 }}>
              <span style={MUTED}>Measure</span>
              <select value={descName} onChange={(e) => setDescriptor(`${descCh}.${e.target.value}`)} style={SELECT} aria-label="Descriptor">
                {DESCRIPTOR_NAMES.map((d) => <option key={d.key} value={d.key}>{d.label}</option>)}
              </select>
            </label>
            {!selection.split && <span style={{ ...MUTED, color: "var(--severity-warning)" }}>This question needs a split — set one under Flights.</span>}
          </>
        )}
        {test.test_id === "unusual" && (
          <>
            <span style={MUTED}>{channels.length ? "Across" : "Across the standard channels"}</span>
            {channels.map((c, i) => <span key={c} style={CHIP}>{channelLabel(c)} <button type="button" onClick={() => setChannels(channels.filter((_, j) => j !== i))} style={LINK}>×</button></span>)}
            <select value="" onChange={(e) => e.target.value && setChannels([...channels, e.target.value])} style={SELECT} aria-label="Add a channel">
              <option value="">+ channel</option>
              {RESEARCH_CHANNELS.filter((c) => !channels.includes(c)).map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
            </select>
          </>
        )}
        <span style={{ flexGrow: 1 }} />
        <button type="button" onClick={onCancel} style={BUTTON}>Cancel</button>
        <button type="button" style={PRIMARY} data-testid="save-question"
          onClick={() => onSave({ test_id: test.test_id, channels: test.test_id === "groups" ? [descCh] : channels,
            params: test.test_id === "groups" ? { ...test.params, descriptor } : test.params })}>Ask</button>
      </div>
    </section>
  );
}

// ── References a pilot types in (§8: "your reference") ─────────────────────

function ReferencesEditor({ references, readOnly, onChange }: { references: UserReference[]; readOnly: boolean; onChange: (r: UserReference[]) => void }) {
  const [draft, setDraft] = useState<UserReference>({ label: "", channel: "rpm", value: 0, kind: "value", source: "" });
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {references.map((r, i) => (
        <div key={i} style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 12 }} data-testid="user-reference">
          <span style={{ fontWeight: 600 }}>{r.label}</span>
          <span style={BODY}>{channelLabel(r.channel)} {r.kind === "band" ? `±${r.value}` : r.value}{r.source ? ` — ${r.source}` : ""}</span>
          <span style={{ flexGrow: 1 }} />
          {!readOnly && <button type="button" onClick={() => onChange(references.filter((_, j) => j !== i))} style={LINK}>Remove</button>}
        </div>
      ))}
      {references.length === 0 && <div style={MUTED}>None — a result is read against the Operators Manual limit where one applies, and against the spread of your own slices.</div>}
      {!readOnly && (
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center", marginTop: 4 }}>
          <input placeholder="label (e.g. governing band)" value={draft.label} onChange={(e) => setDraft({ ...draft, label: e.target.value })} style={{ ...INPUT, width: 190 }} aria-label="Reference label" />
          <select value={draft.channel} onChange={(e) => setDraft({ ...draft, channel: e.target.value })} style={SELECT} aria-label="Reference channel">
            {RESEARCH_CHANNELS.map((c) => <option key={c} value={c}>{channelLabel(c)}</option>)}
          </select>
          <select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value as "value" | "band" })} style={SELECT} aria-label="Reference kind">
            <option value="value">value</option>
            <option value="band">± band</option>
          </select>
          <input type="number" value={draft.value} onChange={(e) => setDraft({ ...draft, value: Number(e.target.value) })} style={{ ...INPUT, width: 90 }} aria-label="Reference value" />
          <input placeholder="source (manual, bulletin…)" value={draft.source} onChange={(e) => setDraft({ ...draft, source: e.target.value })} style={{ ...INPUT, width: 200 }} aria-label="Reference source" />
          <button type="button" disabled={!draft.label.trim()} style={{ ...BUTTON, opacity: draft.label.trim() ? 1 : 0.5 }}
            onClick={() => { onChange([...references, { ...draft, label: draft.label.trim(), source: draft.source?.trim() || undefined }]); setDraft({ label: "", channel: "rpm", value: 0, kind: "value", source: "" }); }}>Add</button>
        </div>
      )}
    </div>
  );
}
