import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import casProposal from "../fixtures/cas-filter-proposal.json";
import limitProposal from "../fixtures/limit-filter-proposal.json";
import type { FilterTarget } from "../types/contract";

// Spec 14 v0.8 §7.5: the scope caption's object noun follows the filter
// target — "this alert" for a CAS target, "this limit" for a limit. Both
// proposals are engine output on the synthetic CAS fixture flights
// (web/scripts/gen_cas_fixture.py).
vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({
    proposeFilter: async (t: FilterTarget) => (t.kind === "cas" ? casProposal : limitProposal),
  }),
}));

import { FilterEditor } from "./FilterEditor";

describe("FilterEditor scope caption", () => {
  it("says this alert for a CAS target", async () => {
    render(<FilterEditor target={{ kind: "cas", cas_id: "ENGINE ECU" }} onSaved={() => {}} onCancel={() => {}} />);
    expect(await screen.findByText("All flights in this workspace — this alert")).toBeTruthy();
    expect(screen.queryByText("All flights in this workspace — this limit")).toBeNull();
  });

  it("says this limit for a limit target", async () => {
    render(<FilterEditor target={{ kind: "limit", limit_id: "oil_temp_max" }} onSaved={() => {}} onCancel={() => {}} />);
    expect(await screen.findByText("All flights in this workspace — this limit")).toBeTruthy();
    expect(screen.queryByText("All flights in this workspace — this alert")).toBeNull();
  });
});
