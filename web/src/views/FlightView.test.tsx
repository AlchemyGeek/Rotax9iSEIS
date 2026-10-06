import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { describe, it, expect, vi } from "vitest";
import { ChartSessionProvider } from "../lib/chartSession";

// jsdom has no ResizeObserver, and ECharts needs a real canvas context
// jsdom doesn't provide — this test only cares about the Analysis grid
// and insight list, not the timeline chart, so stub the chart out.
(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
vi.mock("../components/ChannelTimeline", () => ({ ChannelTimeline: () => null }));

// Spec 03 §5.2 / Spec 10 §4.1 (deferred from Phase B): the mirrored
// badge on a topic with limit_refs, and the insight list showing that
// limit's insight exactly once — never a second entry under the
// mirroring topic. Built from the real KACV fixture with one change: an
// injected oil_temp_max exceedance so there's something to mirror (the
// real flight never exceeded it).
vi.mock("../lib/fixtures", async () => {
  const actual = await vi.importActual<typeof import("../lib/fixtures")>("../lib/fixtures");
  const insightSet = JSON.parse(JSON.stringify(actual.insightSet));
  const limitTopic = insightSet.topics.find((t: { topic_id: string }) => t.topic_id === "limit_exceedances");
  const oilTopic = insightSet.topics.find((t: { topic_id: string }) => t.topic_id === "oil_temp_peak");
  const injectedInsight = {
    id: "injected-oil-temp-max",
    topic_id: "limit_exceedances",
    rule_id: "limit_exceedances.threshold",
    trigger: "threshold",
    severity: "limit",
    message: { text: "⚠ [WARNING] Oil temperature maximum: 1 event, worst 255.0°F (max 248.0°F)." },
    evidence: [],
    confidence: { level: "GOOD", n: 49 },
    limit_id: "oil_temp_max",
    events: [],
    filterable: true,
  };
  limitTopic.insights.push(injectedInsight);
  oilTopic.limit_refs = [{ limit_id: "oil_temp_max", insight_id: injectedInsight.id }];
  return { ...actual, insightSet };
});

import { FlightView } from "./FlightView";
import { flightAnalysis as fixtureFlight } from "../lib/fixtures";

describe("FlightView mirrored limit badge", () => {
  it("shows the mirrored badge on the oil_temp_peak card and lists the limit insight exactly once", async () => {
    render(
      <MemoryRouter initialEntries={[`/flights/${fixtureFlight.flight_id}`]}>
        <ChartSessionProvider>
          <Routes>
            <Route path="/flights/:flightId" element={<FlightView />} />
          </Routes>
        </ChartSessionProvider>
      </MemoryRouter>,
    );

    // The insight list shows the mirrored insight exactly once, under
    // limit_exceedances — not a second time under oil_temp_peak.
    const matches = await screen.findAllByText(/Oil temperature maximum/);
    expect(matches).toHaveLength(1);

    // The oil_temp_peak card itself renders (mirrored badge context) —
    // its own analysis line is present once.
    expect(screen.getAllByText(/Peak 213°F/).length).toBe(1);
  });
});
