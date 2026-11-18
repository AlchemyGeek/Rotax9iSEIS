import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { FORBIDDEN_UI_WORDS } from "../lib/research";

// Spec 16 D15 — the Flight view's Signal toggle: strips over the whole
// flight (one analyze_signal with no window, cached per flight), and on a
// zoomed window the read-out — swing, period (with the below-floor wording
// from the host), correlation and lag with the reference — each beside its
// references. No rule, no slice set, nothing across flights. Synthetic numbers.

const N = 600;
const lit = Array.from({ length: N }, (_, i) => i >= 100 && i < 160);
function strip(level: number) {
  return {
    swing: Array.from({ length: N }, (_, i) => (lit[i] ? level : level / 10)),
    period_s: Array.from({ length: N }, (_, i) => (lit[i] ? 3.4 : null)),
    prominence: Array.from({ length: N }, (_, i) => (lit[i] ? 0.6 : 0.05)),
    prominent: lit,
  };
}
const WINDOW = {
  start_s: 100, end_s: 160, duration_s: 60, context: {}, descriptors: {}, windows: {}, diagnostics: {},
  numbers: {
    rpm: [
      { label: "RPM swing", value: 170, unit: "rpm", text: "170 rpm peak-to-peak",
        references: [{ kind: "om", label: "max", text: "OM max 5800 rpm: the window peaks at 5790 rpm, 10 rpm below it" }] },
      { label: "RPM period", value: 3.4, unit: "s", text: "3.4 s",
        references: [{ kind: "threshold", label: "prominence", text: "prominence 0.61 (at or above the 0.2 the questions use)" }] },
      { label: "RPM level", value: 5700, unit: "rpm", text: "median 5700 rpm", references: [] },
    ],
    map_inhg: [
      { label: "MAP swing", value: 0.6, unit: "inHg", text: "0.6 inHg peak-to-peak", references: [] },
      { label: "MAP period", value: 1.4, unit: "s", text: "a cycle faster than the 1 Hz log can resolve (≈ 2 s; 1.4 s measured)",
        references: [{ kind: "threshold", label: "prominence", text: "prominence 0.3 (at or above the 0.2 the questions use; the period is under the 2 s a 1 Hz log resolves)" }] },
      { label: "MAP level", value: 40, unit: "inHg", text: "median 40 inHg", references: [] },
      { label: "MAP with the reference", value: 0.92, unit: "", text: "correlation 0.92 at zero lag; best match at +0 s (0.92)", references: [] },
    ],
  },
};

const state = vi.hoisted(() => ({ calls: [] as Record<string, unknown>[] }));

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const client = {
    analyzeSignal: async (args: Record<string, unknown>) => {
      state.calls.push(args);
      return {
        flight_id: args.flight_id, duration_s: N, source: "G3X", start_time: null, date: "Day 1",
        channels: ["rpm", "map_inhg"], missing_channels: ["oil_temp_f"], reference: "rpm", phases: [], filled: [],
        strip_windows: { rpm: { window_s: 9, basis: "flight period", flight_period_s: 3.4, lit_seconds: 60, lit_share: 0.1 } },
        strips: args.include_strips === false ? {} : { rpm: strip(170), map_inhg: strip(0.6) },
        prominence_min: 0.2, om_limits: {}, window: args.window ? WINDOW : null,
      };
    },
  };
  return { ...actual, getEngineClient: () => client };
});

import { SignalAid, clearSignalCache, signalChannels } from "./SignalAid";

beforeEach(() => {
  state.calls = [];
  clearSignalCache();
  vi.useRealTimers();
});

function aid(props: Partial<{ flightId: string; win: [number, number] }> = {}) {
  return render(<SignalAid flightId={props.flightId ?? "fa"} chartChannels={["oil_temp_f"]} visibleWindow={props.win ?? [0, N]} fullEnd={N} enabled />);
}

describe("the Signal toggle (Spec 16 D15)", () => {
  it("is off until pressed; on, it reads the whole flight once and lays a swing and a period strip per channel", async () => {
    aid();
    expect(screen.queryByTestId("signal-strips")).toBeNull();
    expect(state.calls).toEqual([]);
    fireEvent.click(screen.getByTestId("signal-toggle"));
    const strips = await screen.findByTestId("signal-strips");
    expect(state.calls).toEqual([{ flight_id: "fa", channels: ["rpm", "map_inhg", "oil_temp_f"], include_values: false }]);
    const rows = within(strips).getAllByTestId("signal-channel");
    expect(rows.map((r) => r.dataset.channel)).toEqual(["rpm", "map_inhg"]);
    expect(within(rows[0]).getAllByTestId(/strip-(swing|period)/).length).toBe(2);
    expect(rows[0].textContent).toContain("RPM — swing, and where it repeats (≈ 3.4 s, lit 10 % of the flight)");
    expect(rows[1].textContent).toContain("MAP — swing, and where it repeats (no repeat stands out)");
    expect(strips.textContent).toContain("Not in this log: Oil temperature.");
    expect(screen.getByTestId("signal-readout").textContent).toContain("Zoom the chart to a window");
  });

  it("caches the whole-flight strips per flight: off and on again asks nothing new", async () => {
    aid();
    fireEvent.click(screen.getByTestId("signal-toggle"));
    await screen.findByTestId("signal-strips");
    fireEvent.click(screen.getByTestId("signal-toggle"));
    fireEvent.click(screen.getByTestId("signal-toggle"));
    await screen.findByTestId("signal-strips");
    expect(state.calls.length).toBe(1);
  });

  it("rpm and MAP lead the channels; at most six", () => {
    expect(signalChannels(["egt1_f", "rpm", "a", "b", "c", "d", "e"])).toEqual(["rpm", "map_inhg", "egt1_f", "a", "b", "c"]);
  });
});

describe("the window read-out (acceptance 17's numbers)", () => {
  it("a zoomed window shows swing, period and correlation with the reference, each beside its references", async () => {
    aid({ win: [100, 160] });
    fireEvent.click(screen.getByTestId("signal-toggle"));
    const out = await screen.findByTestId("signal-window", {}, { timeout: 3000 });
    expect(out.textContent).toBe("The window: 60 s, against RPM");
    const windowed = state.calls.find((c) => c.window)!;
    expect(windowed).toEqual({ flight_id: "fa", channels: ["rpm", "map_inhg", "oil_temp_f"], window: { start_s: 100, end_s: 160 }, include_strips: false, include_values: false });
    const rows = screen.getAllByTestId("signal-number").map((r) => [...r.querySelectorAll("td")].map((td) => td.textContent));
    expect(rows.map((r) => r[0])).toEqual(["RPM swing", "RPM period", "MAP swing", "MAP period", "MAP with the reference"]);
    expect(rows[0]).toEqual(["RPM swing", "170 rpm peak-to-peak", "OM max 5800 rpm: the window peaks at 5790 rpm, 10 rpm below it"]);
    expect(rows[1][1]).toBe("3.4 s");
    expect(rows[3][1]).toContain("faster than the 1 Hz log can resolve");
    expect(rows[4][1]).toContain("correlation 0.92");
    expect(rows[2][2]).toBe("no Operators Manual line for this number");
  });

  it("offers no rule, slice set or run across flights, and says no verdict", async () => {
    aid({ win: [100, 160] });
    fireEvent.click(screen.getByTestId("signal-toggle"));
    await screen.findByTestId("signal-window", {}, { timeout: 3000 });
    const text = screen.getByTestId("signal-aid").textContent!.toLowerCase();
    for (const w of ["make this a rule", "compare", "across flights", "every flight", ...FORBIDDEN_UI_WORDS]) expect(text.includes(w), w).toBe(false);
    expect(screen.queryAllByRole("button").map((b) => b.textContent)).toEqual(["Signal", expect.any(String), expect.any(String)]);
  });

  it("is absent where the host has no research capability", () => {
    render(<SignalAid flightId="fa" chartChannels={[]} visibleWindow={[0, N]} fullEnd={N} enabled={false} />);
    expect(screen.queryByTestId("signal-toggle")).toBeNull();
  });

  it("waits for the zoom to settle before measuring", async () => {
    vi.useFakeTimers();
    const r = aid({ win: [100, 160] });
    fireEvent.click(screen.getByTestId("signal-toggle"));
    r.rerender(<SignalAid flightId="fa" chartChannels={["oil_temp_f"]} visibleWindow={[100, 170]} fullEnd={N} enabled />);
    r.rerender(<SignalAid flightId="fa" chartChannels={["oil_temp_f"]} visibleWindow={[100, 180]} fullEnd={N} enabled />);
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(state.calls.filter((c) => c.window).map((c) => c.window)).toEqual([{ start_s: 100, end_s: 180 }]);
  });
});
