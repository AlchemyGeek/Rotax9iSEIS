import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { whatIfRules, applyCardRuleEdit } = vi.hoisted(() => ({ whatIfRules: vi.fn(), applyCardRuleEdit: vi.fn() }));
vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({ whatIfRules, applyCardRuleEdit }),
}));

import { RuleEditorPanel } from "./RuleEditorPanel";
import type { RuleSet, TopicResult } from "../types/contract";

// Spec 14 v0.9 §7.3 — the rule editor panel: the §7.2 flow (preview,
// Apply, Cancel, Reset to shipped, enabled, scope captions) in a side
// sheet that knows its topic and originating flight.
const rules: RuleSet = {
  version: "test",
  rules: { egt_spread: { enabled: true, triggers: [{ type: "trend", r2_min: 0.5, n_min: 10 }] } },
} as RuleSet;
const topic = {
  topic_id: "egt_spread", analysis: { text: "EGT spread 40°F." }, insights: [], metric_ids: ["egt_spread"], enabled: true,
  trigger_status: [{ type: "trend", met: false, detail: "R² 0.30 over 23 flights" }],
} as unknown as TopicResult;

const fired = { id: "x", topic_id: "egt_spread", rule_id: "egt_spread.trend", trigger: "trend", severity: "watch" };
const iset = (insights: unknown[]) => ({ topics: [{ topic_id: "egt_spread", insights }] });

function panel(extra: Partial<React.ComponentProps<typeof RuleEditorPanel>> = {}) {
  const props = {
    topicId: "egt_spread", topic, title: "EGT spread", originFlightId: "f_here", originFlightLabel: "2026-10-05",
    resolvedRules: rules, shippedRules: rules, onApplied: vi.fn(), onClose: vi.fn(), onNavigateFlight: vi.fn(), ...extra,
  };
  render(<RuleEditorPanel {...props} />);
  return props;
}

describe("RuleEditorPanel", () => {
  beforeEach(() => {
    whatIfRules.mockReset();
    applyCardRuleEdit.mockReset();
  });

  it("is a dialog naming its topic and originating flight, with the topic scope caption and Apply label", () => {
    panel();
    expect(screen.getByRole("dialog", { name: "Edit rules: EGT spread" })).toBeTruthy();
    expect(screen.getByText(/opened from the flight of 2026-10-05/)).toBeTruthy();
    expect(screen.getByText("All flights in this workspace — this topic")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Apply to all flights" })).toBeTruthy();
    expect(screen.getByText(/not met on this flight — R² 0.30 over 23 flights/)).toBeTruthy();
  });

  it("previews an edit with the originating flight highlighted, and Apply writes through the card-edit op (Journal server side)", async () => {
    vi.useFakeTimers();
    whatIfRules.mockResolvedValue({
      flights: {
        f_other: { before: iset([]), after: iset([fired]) },
        f_here: { before: iset([]), after: iset([fired]) },
      },
    });
    applyCardRuleEdit.mockResolvedValue({ rules });
    const props = panel();
    fireEvent.change(screen.getByRole("spinbutton", { name: "r2_min" }), { target: { value: "0.2" } });
    await act(async () => { await vi.advanceTimersByTimeAsync(350); });
    vi.useRealTimers();
    expect(screen.getByTestId("origin-flight-preview").textContent).toBe("This flight: + newly flagged.");
    const links = screen.getAllByRole("link");
    expect(links[0].textContent).toContain("f_here (this flight)");
    fireEvent.click(screen.getByRole("button", { name: "Apply to all flights" }));
    await waitFor(() => expect(applyCardRuleEdit).toHaveBeenCalledWith("egt_spread", expect.objectContaining({ triggers: [expect.objectContaining({ r2_min: 0.2 })] })));
    await waitFor(() => expect(props.onApplied).toHaveBeenCalledWith(rules));
    expect(props.onClose).toHaveBeenCalled();
  });

  it("Reset to shipped puts one trigger back without touching the rest", () => {
    panel();
    fireEvent.change(screen.getByRole("spinbutton", { name: "r2_min" }), { target: { value: "0.2" } });
    fireEvent.click(screen.getByText("Reset to shipped"));
    expect((screen.getByRole("spinbutton", { name: "r2_min" }) as HTMLInputElement).value).toBe("0.5");
  });

  it("opened by a disabled topic's Enable, starts with enabled on so the re-enable previews before Apply", () => {
    const off: RuleSet = { ...rules, rules: { egt_spread: { ...rules.rules.egt_spread, enabled: false } } };
    whatIfRules.mockResolvedValue({ flights: {} });
    panel({ resolvedRules: off, shippedRules: rules, topic: { ...topic, enabled: false }, enable: true });
    expect((screen.getByLabelText("enabled") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByRole("button", { name: "Apply to all flights" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("Cancel, the close button and Escape all close without applying", () => {
    const props = panel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    fireEvent.keyDown(window, { key: "Escape" });
    expect(props.onClose).toHaveBeenCalledTimes(3);
    expect(applyCardRuleEdit).not.toHaveBeenCalled();
  });
});
