// Spec 03 v0.34 — one formatter for a window's time (Research home, the notebook page, the Flight view's
// mark dialog): short, with the engine's full window_label on hover. The export's port is checked against
// the same strings (research-notebook.render.json → short_windows; notebook.test.ts).
import { describe, expect, it } from "vitest";
import { into, labelTime, shortWindow, timelineRange, windowLabel, windowTime } from "./timeLabel";

describe("window time", () => {
  it("the spec's form: date without year · hh:mm–hh:mm (+m:ss into the flight)", () => {
    expect(shortWindow("2026-01-01 12:01:05–12:03:10 PST (+01:50–+03:55 into the flight)")).toBe("Jan 1 · 12:01–12:03 (+1:50 into the flight)");
  });
  it("a window inside one minute keeps its seconds", () => {
    expect(shortWindow("2026-10-24 22:26:07–22:26:53 PDT (+10:16–+11:02 into the flight)")).toBe("Oct 24 · 22:26:07–22:26:53 (+10:16 into the flight)");
  });
  it("past an hour into the flight, h:mm:ss; a point in time; no zone", () => {
    expect(shortWindow("2026-03-09 13:01:05–13:03:10 (+1:01:50–+1:03:55 into the flight)")).toBe("Mar 9 · 13:01–13:03 (+1:01:50 into the flight)");
    expect(shortWindow("2026-01-01 12:01:05 (+01:50 into the flight)")).toBe("Jan 1 · 12:01 (+1:50 into the flight)");
  });
  it("without a local time, the offsets are the window; anything else is shown as it is", () => {
    expect(shortWindow("+06:07–+07:04 into the flight")).toBe("+6:07–+7:04 into the flight");
    expect(shortWindow("not a window")).toBe("not a window");
    expect(shortWindow(null)).toBe("");
  });
  it("builds the engine's window_label from the flight's local start (wall clock, no browser zone)", () => {
    expect(into(616)).toBe("+10:16");
    expect(into(3725)).toBe("+1:02:05");
    expect(windowLabel("2026-10-24T22:15:51-07:00", "PDT", 616, 662)).toBe("2026-10-24 22:26:07–22:26:53 PDT (+10:16–+11:02 into the flight)");
    expect(windowLabel("2026-12-31T23:59:00", null, 120, 180)).toBe("2027-01-01 00:01:00–00:02:00 (+02:00–+03:00 into the flight)");
    expect(windowLabel(null, null, 120, 180)).toBe("+02:00–+03:00 into the flight");
    const t = windowTime("2026-10-24T22:15:51", "PDT", 616, 662);
    expect(t).toEqual({ short: "Oct 24 · 22:26:07–22:26:53 (+10:16 into the flight)", full: "2026-10-24 22:26:07–22:26:53 PDT (+10:16–+11:02 into the flight)" });
    expect(labelTime(t.full)).toEqual(t);
  });
  it("the timeline header: the flight's local clock and zone; UTC said so when the flight's local time is unknown", () => {
    expect(timelineRange("2026-10-24T22:15:51-07:00", "PDT", "2026-10-25T05:15:51Z", 616, 662)).toBe("22:26–22:26 PDT (1 min)");
    expect(timelineRange("2026-10-24T08:16:00", "PDT", null, 600, 3600)).toBe("08:26–09:16 PDT (50 min)");
    expect(timelineRange(null, null, "2026-01-01T12:00:00Z", 110, 190)).toBe("12:01–12:03 UTC (1 min)");
    expect(timelineRange(null, null, null, 0, 60)).toBe("—");
  });
});

