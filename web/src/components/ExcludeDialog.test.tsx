import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { previewReferenceMembership } = vi.hoisted(() => ({ previewReferenceMembership: vi.fn() }));
vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({ previewReferenceMembership }),
}));

import { ExcludeConfirmDialog } from "./ExcludeDialog";

// Spec 14 §7.1 / §7.5 / §9 criteria 16 and 18: exclude-from-reference and
// Include again share one dialog — scope caption (this flight only, other
// flights' comparisons will move), a preview of the other flights whose
// verdict moves, and Apply to this flight.
describe("ExcludeConfirmDialog", () => {
  beforeEach(() => previewReferenceMembership.mockReset());

  it("exclude: caption, preview, required reason, Apply to this flight", async () => {
    previewReferenceMembership.mockResolvedValue({ changed_flight_ids: ["a", "b"] });
    const onConfirm = vi.fn();
    render(<ExcludeConfirmDialog flightId="f1" flightLabel="2026-09-02" busy={false} onConfirm={onConfirm} onCancel={() => {}} />);
    expect(screen.getByText("This flight only — other flights' comparisons will move")).toBeTruthy();
    expect(await screen.findByText("Changes the verdict on 2 other flights.")).toBeTruthy();
    expect(previewReferenceMembership).toHaveBeenCalledWith("f1", "exclude");
    const apply = screen.getByRole("button", { name: "Apply to this flight" }) as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "ground run" } });
    fireEvent.click(apply);
    expect(onConfirm).toHaveBeenCalledWith("ground run");
  });

  it("include again: same caption and preview, no reason field", async () => {
    previewReferenceMembership.mockResolvedValue({ changed_flight_ids: [] });
    const onConfirm = vi.fn();
    render(<ExcludeConfirmDialog mode="include" flightId="f1" flightLabel="2026-09-02" busy={false} onConfirm={onConfirm} onCancel={() => {}} />);
    expect(screen.getByText("Include this flight in reference again")).toBeTruthy();
    expect(screen.getByText("This flight only — other flights' comparisons will move")).toBeTruthy();
    expect(await screen.findByText("No other flight's verdict changes.")).toBeTruthy();
    expect(previewReferenceMembership).toHaveBeenCalledWith("f1", "include");
    expect(screen.queryByRole("textbox")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Apply to this flight" }));
    expect(onConfirm).toHaveBeenCalled();
  });
});
