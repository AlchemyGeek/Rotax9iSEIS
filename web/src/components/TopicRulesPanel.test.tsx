import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

const { whatIfRules, applyCardRuleEdit } = vi.hoisted(() => ({ whatIfRules: vi.fn(), applyCardRuleEdit: vi.fn() }));
vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({ whatIfRules, applyCardRuleEdit }),
}));

import { TopicRulesPanel } from "./TopicRulesPanel";
import type { RuleSet, TopicResult } from "../types/contract";

// Spec 14 §7.3 (v0.4) / §9 criterion 14: the insight card's "edit trigger
// ↓" opens this panel from outside by bumping openRequest; the panel is
// still the only editor.
const rules: RuleSet = {
  version: "test",
  rules: { egt_spread: { enabled: true, triggers: [{ type: "trend", r2_min: 0.5, n_min: 10 }] } },
} as RuleSet;
const topic = {
  topic_id: "egt_spread",
  analysis: { text: "EGT spread 40°F." },
  insights: [],
  metric_ids: ["egt_spread"],
  enabled: true,
  trigger_status: [{ type: "trend", met: false, detail: "R² 0.30 over 23 flights" }],
} as unknown as TopicResult;

function panel(openRequest: number) {
  return (
    <TopicRulesPanel
      topicId="egt_spread"
      topic={topic}
      resolvedRules={rules}
      shippedRules={rules}
      onApplied={() => {}}
      onNavigateFlight={() => {}}
      openRequest={openRequest}
    />
  );
}

// jsdom has no scrollIntoView.
const scrollIntoView = vi.fn();
Element.prototype.scrollIntoView = scrollIntoView;

describe("TopicRulesPanel openRequest", () => {
  beforeEach(() => scrollIntoView.mockClear());

  it("is closed by default and opens when an edit-trigger request arrives", () => {
    const { rerender } = render(panel(0));
    expect(screen.getByText(/▸ triggers/)).toBeTruthy();
    rerender(panel(1));
    expect(screen.getByText(/▾ triggers/)).toBeTruthy();
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
  });

  it("re-opens on a later request after the user closed it", () => {
    const { rerender } = render(panel(1));
    screen.getByText(/▾ triggers/).click();
    rerender(panel(1));
    expect(screen.getByText(/▸ triggers/)).toBeTruthy();
    rerender(panel(2));
    expect(screen.getByText(/▾ triggers/)).toBeTruthy();
    // One scroll per request — closing and the same request again do not scroll.
    expect(scrollIntoView).toHaveBeenCalledTimes(2);
  });
});

// Spec 14 §7.3 (v0.5) / §9 criterion 17: a disabled topic's card is one
// line, <topic> · disabled · Enable; Enable previews before it applies.
describe("TopicRulesPanel on a disabled topic", () => {
  const disabledRules: RuleSet = {
    version: "test",
    rules: { egt_spread: { enabled: false, triggers: [{ type: "trend", r2_min: 0.5, n_min: 10 }] } },
  } as RuleSet;
  const disabledTopic = { topic_id: "egt_spread", analysis: { text: "" }, insights: [], metric_ids: [], enabled: false, trigger_status: [] } as unknown as TopicResult;

  it("is one collapsed line with Enable, and Enable previews then applies enabled: true", async () => {
    whatIfRules.mockResolvedValue({ flights: { f1: { before: { topics: [] }, after: { topics: [{ topic_id: "egt_spread", insights: [{ rule_id: "egt_spread.trend", severity: "watch" }] }] } } } });
    applyCardRuleEdit.mockResolvedValue({ rules: { ...disabledRules, rules: { egt_spread: { ...disabledRules.rules.egt_spread, enabled: true } } }, journal_entry: null });
    const onApplied = vi.fn();
    render(
      <TopicRulesPanel
        topicId="egt_spread" topic={disabledTopic} title="EGT spread"
        resolvedRules={disabledRules} shippedRules={disabledRules}
        onApplied={onApplied} onNavigateFlight={() => {}}
      />,
    );
    expect(screen.getByText("EGT spread").parentElement?.textContent).toBe("EGT spread · disabled · Enable");
    expect(screen.queryByText(/triggers/)).toBeNull();

    fireEvent.click(screen.getByText("Enable"));
    await screen.findByText(/On your 1 flights: 1 change/, {}, { timeout: 2000 });
    expect(whatIfRules.mock.calls[0][0].rules.rules.egt_spread.enabled).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: /Apply/ }));
    await vi.waitFor(() => expect(onApplied).toHaveBeenCalled());
    expect(applyCardRuleEdit).toHaveBeenCalledWith("egt_spread", { ...disabledRules.rules.egt_spread, enabled: true });
  });
});
