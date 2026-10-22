import { describe, expect, it } from "vitest";
import { spliceDetail, worstMoment } from "./useTimeline";

// Spec 07 §11.3–§11.4.

describe("spliceDetail", () => {
  it("keeps the overview outside the window and the full detail inside it", () => {
    const overview = [[0, 1], [100, 2], [200, 3], [300, 4]];
    const detail = [[100, 2], [101, 2.5], [102, 2.4], [199, 3]];
    expect(spliceDetail(overview, detail, [100, 199])).toEqual([[0, 1], [100, 2], [101, 2.5], [102, 2.4], [199, 3], [200, 3], [300, 4]]);
  });
});

describe("worstMoment", () => {
  const pts = [[1205, 46.1], [1300, 47.5], [1376, 49], [1400, 48.2], [1500, null]];
  it("finds when a MAX event reached its reported value", () => {
    expect(worstMoment(pts, "MAX", 49)).toBe(1376);
  });
  it("finds a MIN event's lowest reading", () => {
    expect(worstMoment([[10, 1800], [20, 1610], [30, 1700]], "MIN", 1610)).toBe(20);
  });
  it("gives no moment when the reported value isn't a reading in that stretch", () => {
    expect(worstMoment(pts, "MAX", 312)).toBeNull();    // e.g. a limit whose value is a duration
  });
});
