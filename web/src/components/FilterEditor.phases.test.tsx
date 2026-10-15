import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import limitProposal from "../fixtures/limit-filter-proposal.json";
import casProposal from "../fixtures/cas-filter-proposal.json";
import type { FilterPreview, FilterTarget, LimitFilterDraft } from "../types/contract";

// Spec 09 v0.20 §12.1 — phase chips in the filter editor: shown only when
// the limit allows a phase condition; never pre-selected from an event
// unless the pilot asks; the preview breaks suppression down by phase.

const calls = vi.hoisted(() => ({ preview: vi.fn(), save: vi.fn() }));
const state: { phasesAllowed: boolean } = { phasesAllowed: true };

const preview: FilterPreview = {
  target: { kind: "limit", limit_id: "oil_temp_max" }, valid: true, diagnostics: [], flights_considered: 8,
  events_total: 5, events_hidden: 3, flights_affected: 2, flights_with_breach: 0, flights: [],
  phases: {
    suppressed_by_phase: { TAXI: { events: 2, flights: 2 }, LANDING_ROLL: { events: 1, flights: 1 } },
    visible_events: 2, visible_by_phase: { APPROACH: 2, TAXI: 1 }, excludes_every_phase: false,
  },
};

vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({
    proposeFilter: async (t: FilterTarget) =>
      t.kind === "cas" ? casProposal : { ...limitProposal, policy: { ...limitProposal.policy, phases_allowed: state.phasesAllowed } },
    previewFilter: async (d: LimitFilterDraft) => { calls.preview(d); return preview; },
    saveFilter: async (d: LimitFilterDraft) => { calls.save(d); return d; },
  }),
}));

import { FilterEditor } from "./FilterEditor";

const LIMIT: FilterTarget = { kind: "limit", limit_id: "oil_temp_max" };

describe("FilterEditor phase condition", () => {
  beforeEach(() => {
    state.phasesAllowed = true;
    calls.preview.mockClear();
    calls.save.mockClear();
  });

  it("shows the phase chips in flight order when the limit allows them, none selected", async () => {
    render(<FilterEditor target={LIMIT} eventPhases={["APPROACH", "TAXI"]} onSaved={() => {}} onCancel={() => {}} />);
    const chips = await screen.findByTestId("phase-chips");
    const names = within(chips).getAllByRole("button", { pressed: false }).map((b) => b.textContent);
    expect(names).toEqual(["PRE_START", "ENGINE_START", "WARMUP", "TAXI", "TAKEOFF_ROLL", "CLIMB", "CRUISE", "DESCENT", "APPROACH", "LANDING_ROLL", "SHUTDOWN"]);
    expect(within(chips).queryAllByRole("button", { pressed: true })).toHaveLength(0);
  });

  it("selects the event's phases only when asked", async () => {
    render(<FilterEditor target={LIMIT} eventPhases={["APPROACH", "TAXI"]} onSaved={() => {}} onCancel={() => {}} />);
    const chips = await screen.findByTestId("phase-chips");
    fireEvent.click(within(chips).getByText(/Exclude this event's phases/));
    expect(within(chips).getAllByRole("button", { pressed: true }).map((b) => b.textContent)).toEqual(["TAXI", "APPROACH"]);
  });

  it("hides the chips when the policy doesn't allow phases, and for an alert", async () => {
    state.phasesAllowed = false;
    const { unmount } = render(<FilterEditor target={LIMIT} onSaved={() => {}} onCancel={() => {}} />);
    await screen.findByText(/Filter this limit/);
    expect(screen.queryByTestId("phase-chips")).toBeNull();
    unmount();
    state.phasesAllowed = true;
    render(<FilterEditor target={{ kind: "cas", cas_id: "ENGINE ECU" }} onSaved={() => {}} onCancel={() => {}} />);
    await screen.findByText(/Filter this alert/);
    expect(screen.queryByTestId("phase-chips")).toBeNull();
  });

  it("a phases-only filter previews by phase and saves its phases in flight order", async () => {
    render(<FilterEditor target={LIMIT} onSaved={() => {}} onCancel={() => {}} />);
    const chips = await screen.findByTestId("phase-chips");
    // Magnitude off: only the phase condition.
    fireEvent.click(screen.getByRole("checkbox", { name: /past the limit is fine/i }));
    fireEvent.click(within(chips).getByText("LANDING_ROLL"));
    fireEvent.click(within(chips).getByText("TAXI"));
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    const p = await screen.findByTestId("phase-preview");
    expect(p.textContent).toContain("Suppressed by phase: TAXI 2 events on 2 flights · LANDING_ROLL 1 event on 1 flight");
    expect(p.textContent).toContain("Still visible: 2 events (APPROACH 2 · TAXI 1)");
    expect(calls.preview).toHaveBeenCalledWith(expect.objectContaining({ phases: ["TAXI", "LANDING_ROLL"], magnitude: undefined }));
    // oil_temp_max is a WARNING limit: the note is required (§6.3).
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "low idle while taxiing is normal here" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply to all flights" }));
    await waitFor(() => expect(calls.save).toHaveBeenCalledWith(expect.objectContaining({ phases: ["TAXI", "LANDING_ROLL"] })));
  });
});
