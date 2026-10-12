import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { ExcludeConfirmDialog } from "./ExcludeDialog";

// Spec 14 §7.5 / §9 criterion 16: exclude-from-reference states its scope
// — this flight only, other flights' comparisons will move — before
// interaction, and its confirm repeats it.
describe("ExcludeConfirmDialog scope", () => {
  it("shows the this-flight caption with its note and confirms with Apply to this flight", () => {
    const onConfirm = vi.fn();
    render(<ExcludeConfirmDialog flightLabel="2026-09-02" busy={false} onConfirm={onConfirm} onCancel={() => {}} />);
    expect(screen.getByText("This flight only — other flights' comparisons will move")).toBeTruthy();
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "ground run" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply to this flight" }));
    expect(onConfirm).toHaveBeenCalledWith("ground run");
  });
});
