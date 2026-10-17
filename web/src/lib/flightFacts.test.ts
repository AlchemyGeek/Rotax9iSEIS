import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { createElement } from "react";
import { FLIGHT_FACT_IDS, admitFacts, flightFacts } from "./flightFacts";
import { FlightFacts } from "../components/FlightFacts";
import eventsFlight from "../fixtures/flight-events-analysis.json";
import type { FlightAnalysis } from "../types/contract";

const fa = eventsFlight as unknown as FlightAnalysis;

// Spec 10 §4.3 (D20): the Flight facts row admits exactly the §4.3 table.
describe("Flight facts allow-list", () => {
  it("is the §4.3 table: fuel burned, cruise nm/gal, cruise fuel flow, lane check", () => {
    expect([...FLIGHT_FACT_IDS]).toEqual(["fuel_burned", "cruise_nmpg", "cruise_fuel_flow", "lane_check"]);
    expect(flightFacts(fa).map((f) => f.id)).toEqual([...FLIGHT_FACT_IDS]);
  });

  it("drops anything not on the list, wherever it was built", () => {
    const admitted = admitFacts([
      { id: "fuel_burned", label: "Fuel burned", value: "3.0 gal" },
      { id: "egt_spread", label: "EGT spread", value: "40 °F" },
    ]);
    expect(admitted.map((f) => f.id)).toEqual(["fuel_burned"]);
    render(createElement(FlightFacts, {
      facts: [...flightFacts(fa), { id: "oil_temp_peak", label: "Oil temp peak", value: "255 °F" }] as never,
      engine: "916iS", units: "imperial",
    }));
    expect(screen.queryByText(/Oil temp peak/)).toBeNull();
    expect(screen.getByTestId("flight-facts").querySelectorAll("[data-fact]")).toHaveLength(4);
  });

  it("shows plain values and — when unavailable", () => {
    const bare = { ...fa, metrics: {}, ecu_lane_check: undefined } as unknown as FlightAnalysis;
    expect(flightFacts(bare).map((f) => f.value)).toEqual(["—", "—", "—", "—"]);
    const lane = flightFacts({ ...fa, ecu_lane_check: "both" }).find((f) => f.id === "lane_check");
    expect(lane?.value).toBe("both lanes ✓");
  });
});
