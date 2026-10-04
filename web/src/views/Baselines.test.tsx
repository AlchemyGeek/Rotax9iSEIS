import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect } from "vitest";
import { Baselines } from "./Baselines";
import { insightRules } from "../lib/fixtures";

// Regression guard for the Phase A crash: cylinder_rank ships with no
// `triggers` key at all (Spec 08 v0.3 §6), and the rule playground's
// render path assumed every rule had one — `topic.triggers.map()` on
// `undefined` threw the instant a pilot clicked it, caught by nothing
// (Spec 10 Phase B). This renders every rule insight_rules.json actually
// ships (via the fixture, which is a live mirror — see lib/fixtures.ts)
// in the real playground component, so any future rule shape nothing
// expects fails a test instead of a pilot's browser.
//
// No live server in this environment, so the component falls back to its
// own fixture data (`usingFixture`) the same way a disconnected browser
// would — no mocking needed.
describe("Baselines rule playground", () => {
  it("selects every shipped rule without crashing", async () => {
    render(
      <MemoryRouter>
        <Baselines />
      </MemoryRouter>,
    );

    const topicIds = Object.keys(insightRules.rules);
    expect(topicIds.length).toBeGreaterThan(0);

    for (const topicId of topicIds) {
      const row = await screen.findByText(topicId, { selector: "span" });
      fireEvent.click(row);
      // The content pane's own heading echoes the selected topic — proof
      // the click was handled and the panel re-rendered, not just that
      // nothing threw. findByRole itself throws (failing the test) if the
      // heading never appears.
      await screen.findByRole("heading", { name: topicId });
    }
  });
});
