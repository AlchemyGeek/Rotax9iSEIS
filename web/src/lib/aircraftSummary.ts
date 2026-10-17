import { useEffect, useState } from "react";
import { getEngineClient } from "./engineClient";
import { aircraftSummary as fixtureAircraftSummary } from "./fixtures";
import type { AircraftSummary } from "../types/contract";

export function useAircraftSummary(usingFixture: boolean, refreshKey = 0): AircraftSummary | null {
  const [summary, setSummary] = useState<AircraftSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (usingFixture) {
      setSummary(fixtureAircraftSummary);
      return;
    }
    getEngineClient()
      .getAircraftSummary()
      .then((result) => {
        if (!cancelled) setSummary(result);
      })
      .catch(() => {
        if (!cancelled) setSummary(null);
      });
    return () => {
      cancelled = true;
    };
  }, [usingFixture, refreshKey]);

  return summary;
}
