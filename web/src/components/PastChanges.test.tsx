import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PastChanges } from "./PastChanges";
import type { ShiftEvent } from "../types/contract";

function closedEvent(overrides: Partial<ShiftEvent> = {}): ShiftEvent {
  return {
    id: "ev1", metric_id: "limit_oil_temp_max_peak_excess", detected_at: "2026-09-01T00:00:00Z",
    cleared_at: "2026-09-10T00:00:00Z", cleared_engine_hours: 42,
    kind: "shift",
    window: { flight_ids: ["f1", "f2"], hours_from: 30, hours_to: 40 },
    shift_z: 3.2, direction: "higher",
    comparison: { scope: "all", unmatched: 0 },
    reference: { kind: "rolling", n: 20, hours_from: 0, hours_to: 29 },
    ...overrides,
  };
}

describe("PastChanges", () => {
  it("renders nothing with no closed events", () => {
    const { container } = render(<PastChanges events={[]} onOpenPanel={() => {}} onDelete={() => {}} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows a frequency-kind closed event and calls onDelete", () => {
    const onDelete = vi.fn();
    const event = closedEvent({ kind: "frequency", metric_id: "limit_overboost_block_s" });
    render(<PastChanges events={[event]} onOpenPanel={() => {}} onDelete={onDelete} />);

    fireEvent.click(screen.getByText(/Past changes \(1\)/));
    expect(screen.getByText(/higher · detected/)).toBeTruthy();

    // Spec 14 §7.5 (v0.6): scope stated up front; delete asks to confirm.
    expect(screen.getByText("All flights in this workspace — this metric")).toBeTruthy();
    fireEvent.click(screen.getByTitle("Delete this event"));
    expect(onDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Apply to all flights" }));
    expect(onDelete).toHaveBeenCalledWith("ev1");
  });
});
