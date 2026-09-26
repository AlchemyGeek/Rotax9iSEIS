import { createContext, useContext, useState, type ReactNode } from "react";
import type { ChartState } from "../components/PresetBar";

// Spec 07 D7: "No flight has its own view" — the chart's channel
// selection is one piece of state for the whole app, not scoped to
// whichever flight route happens to be mounted. It has to live above
// <Routes> (App.tsx), or navigating through the Flights list (a
// different route, which unmounts FlightView) would reset it — the
// same-route-param-change trick alone isn't enough, since that only
// covers the (currently unreachable through any UI) case of moving
// between two flight ids without visiting another route in between.
//
// Resets only on a full page reload, never persisted — Spec 07 §6.5's
// "only the preset is persisted... so a one-off tweak doesn't carry
// into the next session" already covers cross-session continuity via
// AppSettings.flight_chart.last_preset_id (a real persisted value);
// this context is the in-memory "current session" layer on top of that.

export interface InsightSnapshot {
  activeSlots: string[];
  presetId: string | null;
  chartState: "preset" | "modified";
}

interface ChartSessionValue {
  initialized: boolean;
  setInitialized: (v: boolean) => void;
  activeSlots: string[];
  setActiveSlots: (v: string[]) => void;
  presetId: string | null;
  setPresetId: (v: string | null) => void;
  chartState: ChartState;
  setChartState: (v: ChartState) => void;
  channelColors: Record<string, string>;
  setChannelColors: (v: Record<string, string> | ((prev: Record<string, string>) => Record<string, string>)) => void;
  insightSnapshot: InsightSnapshot | null;
  setInsightSnapshot: (v: InsightSnapshot | null) => void;
  insightLabel: string | undefined;
  setInsightLabel: (v: string | undefined) => void;
}

const ChartSessionContext = createContext<ChartSessionValue | null>(null);

export function ChartSessionProvider({ children }: { children: ReactNode }) {
  const [initialized, setInitialized] = useState(false);
  const [activeSlots, setActiveSlots] = useState<string[]>([]);
  const [presetId, setPresetId] = useState<string | null>(null);
  const [chartState, setChartState] = useState<ChartState>("preset");
  const [channelColors, setChannelColors] = useState<Record<string, string>>({});
  const [insightSnapshot, setInsightSnapshot] = useState<InsightSnapshot | null>(null);
  const [insightLabel, setInsightLabel] = useState<string | undefined>(undefined);

  return (
    <ChartSessionContext.Provider
      value={{
        initialized, setInitialized,
        activeSlots, setActiveSlots,
        presetId, setPresetId,
        chartState, setChartState,
        channelColors, setChannelColors,
        insightSnapshot, setInsightSnapshot,
        insightLabel, setInsightLabel,
      }}
    >
      {children}
    </ChartSessionContext.Provider>
  );
}

export function useChartSession(): ChartSessionValue {
  const ctx = useContext(ChartSessionContext);
  if (!ctx) throw new Error("useChartSession must be used within a ChartSessionProvider");
  return ctx;
}
