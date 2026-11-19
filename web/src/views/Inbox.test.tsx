import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { resetCapabilities } from "../lib/capabilities";

// Spec 16 §6 (D5, D8, D16) — the inbox on Research home, both tiers: the
// owner's questions with their marks (each opening its flight at the
// window), Unassigned, edit / move / delete, the same statuses; candidates
// with their evidence, sensitivity and status; Mark nothing here / watch /
// acted with a note; the linked study opens; the install invitation and
// the question's hand-off line where there is no bench. Synthetic data.

const FA = "aaaaaaaaaaaaaaaa", FB = "bbbbbbbbbbbbbbbb";
type P = { id: string; question_id: string | null; flight: string; start_s: number; end_s: number; channels: string[]; note: string | null; created: string; flight_here?: boolean; date?: string; when?: string; status?: string; study_id?: string | null };
type Q = { id: string; title: string; status: string; study_id: string | null; note: string | null; created: string; updated: string; resolved_at: string | null };
const state = vi.hoisted(() => ({ bench: true, calls: [] as { op: string; params: unknown }[], candidates: [] as Record<string, unknown>[],
  questions: [] as Q[], pins: [] as P[] }));

function pinsListing() {
  const of = (qid: string | null) => state.pins.filter((p) => p.question_id === qid);
  const qs = state.questions.map((q) => {
    const ps = of(q.id);
    return { ...q, pins: ps, pin_count: ps.length, newest_note: [...ps].reverse().find((p) => p.note)?.note ?? null };
  });
  const open = state.questions.filter((q) => q.status === "new" || q.status === "investigating");
  return { questions: qs, unassigned: of(null), counts: {}, pins: state.pins.length, newest_open: open.at(-1)?.id ?? null };
}

function candidate(id: string, extra: Record<string, unknown> = {}) {
  return {
    id, key: "full_power:rpm.period", preset: "full_power", preset_name: "Full-power segment", kind: "recurring", descriptors: ["rpm.period"],
    fired: { rule: "prominent rpm period in a governed-rpm preset", hits: 8, of: 10, n: 6, m: 10 },
    summary: "Full-power segment: RPM repeats with a prominent period in 8 of the last 10 slices (median period 3.7 s, swing 170 rpm).",
    evidence: { columns: ["slice_id", "flight", "date", "source", "rpm.period_s", "rpm.swing"], rows: [
      [`${FA}:r1:600-660`, FA, "2026-01-02", "G3X", 3.7, 170], [`${FB}:r1:900-950`, FB, "2026-01-03", "AXIS", 3.6, 180]] },
    slices: [`${FA}:r1:600-660`, `${FB}:r1:900-950`], window: { flight_ids: [FA, FB] },
    status: "new", sensitivity: "normal", parameters: { n: 6, m: 10, shift_z: 3.0, group_z: 2.25 },
    created: "2026-01-04T00:00:00Z", last_seen: "2026-01-04T00:00:00Z", holds: true, study_id: null, note: null, resolved_at: null, ...extra,
  };
}

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const rec = (op: string, params: unknown) => state.calls.push({ op, params });
  const overrides: Record<string, unknown> = {
    getCapabilities: async () => ({ host: state.bench ? "server" : "browser", engine_version: "1.0.2", host_version: "1.0.2", features: { research: true, investigations: true, bench: state.bench } }),
    getActiveWorkspace: async () => ({ active: true, manifest: { id: "ws", name: "Sample", log_folders: [] } }),
    listWorkspaces: async () => [],
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    getFleet: async () => ({ shift_history: [] }),
    listStudies: async () => ({ studies: [] }),
    listSlicePresets: async () => ({ presets: [], phase_rules: [], engine: "916iS", status: "measured", note: null }),
    listFlights: async () => [{ flight_id: FA }, { flight_id: FB }, { flight_id: "cccccccccccccccc" }],
    inboxList: async () => {
      rec("inbox_list", null);
      const counts = { new: 0, investigating: 0, "nothing-here": 0, watch: 0, acted: 0 } as Record<string, number>;
      for (const c of state.candidates) counts[c.status as string]++;
      return { candidates: state.candidates, counts, last_scan: { at: "2026-01-04T00:00:00Z", sensitivity: "normal", flights: 3, parameters: {} } };
    },
    pinsList: async () => { rec("pins_list", null); return pinsListing(); },
    pinEdit: async (args: { pin_id: string; note?: string | null; question?: string | { title: string } | null }) => {
      rec("pin_edit", args);
      const p = state.pins.find((x) => x.id === args.pin_id)!;
      if ("note" in args) p.note = args.note ?? null;
      if ("question" in args) {
        const t = args.question;
        if (t && typeof t === "object") {
          const q = { id: `q-new${state.questions.length}`, title: t.title, status: "new", study_id: null, note: null, created: "2026-01-05T00:00:00Z", updated: "", resolved_at: null };
          state.questions.push(q);
          p.question_id = q.id;
        } else p.question_id = t ?? null;
      }
      return { pin: p, question: null };
    },
    pinDelete: async (id: string) => { rec("pin_delete", id); state.pins = state.pins.filter((p) => p.id !== id); return { deleted: id }; },
    questionResolve: async (args: { question_id: string; status: string; note: string | null }) => {
      rec("question_resolve", args);
      const q = state.questions.find((x) => x.id === args.question_id)!;
      Object.assign(q, { status: args.status, note: args.note });
      return { question: q };
    },
    questionEdit: async (args: { question_id: string; title: string }) => {
      rec("question_edit", args);
      const q = state.questions.find((x) => x.id === args.question_id)!;
      q.title = args.title;
      return { question: q };
    },
    questionDelete: async (id: string) => {
      rec("question_delete", id);
      state.questions = state.questions.filter((q) => q.id !== id);
      let n = 0;
      for (const p of state.pins) if (p.question_id === id) { p.question_id = null; n++; }
      return { deleted: id, pins_unassigned: n };
    },
    inboxResolve: async (args: { candidate_id: string; status: string; note: string | null }) => {
      rec("inbox_resolve", args);
      const c = state.candidates.find((x) => x.id === args.candidate_id)!;
      Object.assign(c, { status: args.status, note: args.note });
      return { candidate: c };
    },
  };
  const client = new Proxy(overrides, { get: (t, prop: string) => t[prop] ?? (async () => { throw new Error(`unmocked ${prop}`); }) });
  return { ...actual, getEngineClient: () => client };
});

import { Research } from "./Research";

function Where() {
  const loc = useLocation();
  return <div data-testid="where">{loc.pathname + loc.search}</div>;
}

function app() {
  render(
    <MemoryRouter initialEntries={["/research"]}>
      <Routes>
        <Route path="/research" element={<Research />} />
        <Route path="*" element={<Where />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  state.bench = true;
  state.calls = [];
  state.candidates = [candidate("ib-1"), candidate("ib-2", { status: "watch", study_id: "st-linked", note: "Pending the bulletin." })];
  state.questions = [{ id: "q-rough", title: "rough climbs", status: "new", study_id: null, note: null, created: "2026-01-04T00:00:00Z", updated: "", resolved_at: null }];
  state.pins = [
    { id: "p-1", question_id: "q-rough", flight: FA, start_s: 100.4, end_s: 160, channels: ["rpm", "map_inhg"], note: "rpm wanders in the climb", created: "2026-01-04T00:00:01Z", flight_here: true, date: "2026-01-02", when: "2026-01-02 10:01:40–10:02:40 PST (+01:40–+02:40 into the flight)" },
    { id: "p-2", question_id: "q-rough", flight: FB, start_s: 120, end_s: 170, channels: ["rpm"], note: "again, less", created: "2026-01-04T00:00:02Z", flight_here: true, date: "2026-01-03" },
    { id: "p-3", question_id: null, flight: FB, start_s: 10, end_s: 40, channels: [], note: null, created: "2026-01-04T00:00:03Z", flight_here: true, date: "2026-01-03" },
  ];
  resetCapabilities();
  sessionStorage.clear();
});

describe("the inbox on Research home (§6)", () => {
  it("lists candidates with summary, what fired, the sensitivity, status and evidence", async () => {
    app();
    const cards = await screen.findAllByTestId("inbox-candidate");
    expect(cards.length).toBe(2);
    const first = cards.find((c) => c.dataset.status === "new")!;
    expect(first.textContent).toContain("Full-power segment");
    expect(first.textContent).toContain("recurring pattern · rpm.period");
    expect(within(first).getByTestId("inbox-sensitivity").textContent).toBe(
      "prominent rpm period in a governed-rpm preset — 8 of 10 · normal sensitivity: a pattern in 6 of 10 recent slices, a shift beyond 3");
    expect(screen.getByTestId("inbox-scan").textContent).toContain("looked at 3 flights");
    fireEvent.click(within(first).getByTestId("inbox-evidence-toggle"));
    const table = within(first).getByTestId("inbox-evidence");
    expect(table.querySelectorAll("tbody tr").length).toBe(2);
    fireEvent.click(within(table).getByText("2026-01-02"));
    expect((await screen.findByTestId("where")).textContent).toBe(`/flights/${FA}?window=600-660`);
  });

  it("marks a candidate with a note; resolved ones fold away; the linked investigation opens", async () => {
    app();
    const first = (await screen.findAllByTestId("inbox-candidate")).find((c) => c.dataset.status === "new")!;
    fireEvent.click(within(first).getByTestId("inbox-mark-acted"));
    fireEvent.change(within(first).getByLabelText("Note"), { target: { value: "Governor re-adjusted" } });
    fireEvent.click(within(first).getByTestId("inbox-mark-confirm"));
    await waitFor(() => expect(state.calls.find((c) => c.op === "inbox_resolve")?.params).toMatchObject({ candidate_id: "ib-1", status: "acted", note: "Governor re-adjusted" }));
    await waitFor(() => expect(screen.getAllByTestId("inbox-candidate").length).toBe(1));
    fireEvent.click(screen.getByTestId("inbox-show-resolved"));
    expect(screen.getAllByTestId("inbox-candidate").length).toBe(2);
    const watched = screen.getAllByTestId("inbox-candidate").find((c) => c.dataset.status === "watch")!;
    expect(within(watched).getByTestId("inbox-note").textContent).toContain("Pending the bulletin.");
    fireEvent.click(within(watched).getByTestId("inbox-open-study"));
    expect((await screen.findByTestId("where")).textContent).toBe("/research/st-linked");
  });

  it("on the website (no bench) the inbox is there with the install invitation", async () => {
    state.bench = false;
    app();
    await screen.findAllByTestId("inbox-candidate");
    expect((await screen.findByTestId("inbox-install")).textContent).toContain("install EIS for Claude Desktop");
    state.bench = true;
  });

  it("with a bench there is no install invitation", async () => {
    app();
    await screen.findAllByTestId("inbox-candidate");
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("inbox-install")).toBeNull();
  });
});

describe("the owner's questions in the inbox (D16)", () => {
  it("one question with its two marks beside the candidates, each opening its flight at the window with its channels", async () => {
    app();
    const q = await screen.findByTestId("question");
    expect(q.dataset.status).toBe("new");
    expect(within(q).getByTestId("question-title").textContent).toBe("rough climbs");
    expect(q.textContent).toContain("2 marks");
    const pins = within(q).getAllByTestId("pin");
    expect(pins.map((p) => within(p).getByTestId("pin-note").textContent)).toEqual(["“rpm wanders in the climb”", "“again, less”"]);
    expect(pins[0].textContent).toContain("+01:40–+02:40 into the flight");
    expect(pins[0].textContent).toContain("RPM, MAP");
    // Unassigned holds the loose mark; the candidates are still there.
    expect(within(screen.getByTestId("questions-unassigned")).getAllByTestId("pin").length).toBe(1);
    expect((await screen.findAllByTestId("inbox-candidate")).length).toBe(2);
    fireEvent.click(within(pins[0]).getByTestId("pin-open"));
    expect((await screen.findByTestId("where")).textContent).toBe(`/flights/${FA}?window=100-160&channels=rpm,map_inhg`);
  });

  it("a question takes the candidates' statuses with a note", async () => {
    app();
    const q = await screen.findByTestId("question");
    fireEvent.click(within(q).getByTestId("question-mark-nothing-here"));
    fireEvent.change(within(q).getByLabelText("Note"), { target: { value: "the governor, known" } });
    fireEvent.click(within(q).getByTestId("question-mark-confirm"));
    await waitFor(() => expect(state.calls.find((c) => c.op === "question_resolve")?.params).toMatchObject({ question_id: "q-rough", status: "nothing-here", note: "the governor, known" }));
    await waitFor(() => expect(screen.queryByTestId("question")).toBeNull());       // resolved ones fold away
    fireEvent.click(screen.getByTestId("questions-show-resolved"));
    expect(screen.getByTestId("question").dataset.status).toBe("nothing-here");
  });

  it("edit a mark's note, move a mark to a new question, delete a mark, rename and delete a question", async () => {
    app();
    const loose = within(await screen.findByTestId("questions-unassigned")).getByTestId("pin");
    fireEvent.click(within(loose).getByTestId("pin-edit"));
    fireEvent.change(within(loose).getByLabelText("Mark note"), { target: { value: "a dip at 30 s" } });
    fireEvent.click(within(loose).getByTestId("pin-note-save"));
    await waitFor(() => expect(state.calls.find((c) => c.op === "pin_edit")?.params).toEqual({ pin_id: "p-3", note: "a dip at 30 s" }));
    const again = within(await screen.findByTestId("questions-unassigned")).getByTestId("pin");
    fireEvent.click(within(again).getByTestId("pin-move"));
    fireEvent.change(within(again).getByLabelText("Move to"), { target: { value: "__new__" } });
    fireEvent.change(within(again).getByLabelText("New question title"), { target: { value: "dips" } });
    fireEvent.click(within(again).getByTestId("pin-move-confirm"));
    await waitFor(() => expect(state.calls.filter((c) => c.op === "pin_edit").at(-1)?.params).toEqual({ pin_id: "p-3", question: { title: "dips" } }));
    await waitFor(() => expect(screen.getAllByTestId("question").length).toBe(2));
    expect(screen.queryByTestId("questions-unassigned")).toBeNull();
    const rough = screen.getAllByTestId("question").find((x) => x.dataset.question === "q-rough")!;
    fireEvent.click(within(within(rough).getAllByTestId("pin")[1]).getByTestId("pin-delete"));
    await waitFor(() => expect(state.calls.find((c) => c.op === "pin_delete")?.params).toBe("p-2"));
    const r2 = (await screen.findAllByTestId("question")).find((x) => x.dataset.question === "q-rough")!;
    fireEvent.click(within(r2).getByTestId("question-rename"));
    fireEvent.change(within(r2).getByLabelText("Question title"), { target: { value: "rough climbs in summer" } });
    fireEvent.click(within(r2).getByText("Save"));
    await waitFor(() => expect(state.calls.find((c) => c.op === "question_edit")?.params).toEqual({ question_id: "q-rough", title: "rough climbs in summer" }));
    const r3 = (await screen.findAllByTestId("question")).find((x) => x.dataset.question === "q-rough")!;
    fireEvent.click(within(r3).getByTestId("question-delete"));
    expect(r3.textContent).toContain("Its marks stay, unassigned.");
    fireEvent.click(within(r3).getByTestId("question-delete-confirm"));
    await waitFor(() => expect(within(screen.getByTestId("questions-unassigned")).getAllByTestId("pin").length).toBe(1));
  });

  it("on the website the question waits, with the hand-off line and the install link", async () => {
    state.bench = false;
    app();
    const line = await screen.findByTestId("questions-handoff");
    expect(line.textContent).toContain("“rough climbs” is waiting for Claude.");
    expect(line.textContent).toContain("Investigate");
    expect(line.querySelector("a")!.getAttribute("href")).toContain("walkthroughs/install-extension/");
    state.bench = true;
  });

  it("with a bench there is no hand-off line; with no marks the inbox says how to mark", async () => {
    state.questions = [];
    state.pins = [];
    app();
    expect((await screen.findByTestId("questions-empty")).textContent).toContain("Mark for Claude");
    expect(screen.queryByTestId("questions-handoff")).toBeNull();
  });
});
