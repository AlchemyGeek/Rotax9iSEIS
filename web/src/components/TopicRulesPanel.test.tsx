import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
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
