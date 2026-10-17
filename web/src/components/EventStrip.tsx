import { useMemo } from "react";
import type { EChartsOption } from "echarts";
import { EChartBase } from "./EChartBase";
import { colors, fontMono } from "../theme/colors";
import type { EventTick, Frequency } from "../types/contract";
import { ECU_CLASS_LABEL, NOT_LANE_CHECK_PHRASE } from "../lib/casEvent";

// Spec 12 §8.4 — the event strip every limit panel (and overboost_time)
// opens with: one tick per eligible flight, short/pale for no event,
// tall/solid for one, with the same reference/recent shading as every
// other strip. Ticks don't encode magnitude (the peak_excess strip below
// does); this one is purely "did it happen". The recent/reference split
// is derived from `events` + `frequency.recent.flights` rather than
// carried as its own hours_from/hours_to — `events` is already
// chronological, so the last `recent.flights` entries *are* the window.
// A CAS panel (Spec 12 v0.10 G2) is this strip and its header only; its
// ticks carry the flight's alert events, named in the tooltip.

function tickDetail(e: EventTick): string {
  if (!e.cas_events?.length) return e.has_event ? "event" : "no event";
  return e.cas_events
    .map((c) => `${ECU_CLASS_LABEL[c.classification]} (${c.phase}), ${Math.round(c.duration_s)} s`
      + (c.not_lane_check_reason ? ` — ${NOT_LANE_CHECK_PHRASE[c.not_lane_check_reason]}` : ""))
    .join("<br/>");
}

const RECENT_WINDOW_FILL = "rgba(79,195,176,0.07)";
const REFERENCE_FILL = "rgba(174,183,191,0.10)";

interface Props {
  events: EventTick[];
  frequency: Frequency;
  highlightFlight: string | null;
  onOpenFlight: (flightId: string) => void;
  // "occurred" for an alert (it has no limit to exceed).
  verb?: "exceeded" | "occurred";
}

export function EventStrip({ events, frequency, highlightFlight, onOpenFlight, verb = "exceeded" }: Props) {
  const split = Math.max(0, events.length - frequency.recent.flights);
  const referenceEvents = events.slice(0, split);
  const recentEvents = events.slice(split);

  const option = useMemo<EChartsOption>(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const markAreas: any[] = [];
    if (recentEvents.length) {
      markAreas.push({
        xAxis: [recentEvents[0].x, recentEvents[recentEvents.length - 1].x], color: RECENT_WINDOW_FILL,
      });
    }
    if (referenceEvents.length) {
      markAreas.push({
        xAxis: [referenceEvents[0].x, referenceEvents[referenceEvents.length - 1].x], color: REFERENCE_FILL,
      });
    }

    const data = events.map((e) => [e.x, 1, e.flight_id, e.date, e.has_event, tickDetail(e)]);

    return {
      animation: false,
      grid: { left: 58, right: 12, top: 2, bottom: 2 },
      tooltip: {
        trigger: "item",
        backgroundColor: colors.panelControl, borderColor: colors.border,
        textStyle: { color: colors.textPrimary, fontSize: 11, fontFamily: fontMono },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        formatter: (p: any) => (Array.isArray(p.data) ? `${p.data[3]} &middot; ${p.data[5]}` : ""),
      },
      xAxis: { type: "value", scale: true, show: false },
      yAxis: { type: "value", show: false, min: 0, max: 2 },
      series: [
        {
          type: "scatter" as const,
          data,
          symbol: "rect",
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          symbolSize: (val: any) => [3, val[4] ? 16 : 7],
          itemStyle: {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            color: (p: any) => (p.data[2] === highlightFlight ? colors.accent : p.data[4] ? colors.textSecondary : colors.borderSubtle),
          },
        },
        // Each shaded region is its own silent, dataless series — a
        // single series' markArea.data entries would otherwise share one
        // itemStyle (TrendsPanelStrip's same pattern).
        ...markAreas.map((a) => ({
          type: "scatter" as const, data: [], silent: true,
          markArea: { silent: true, itemStyle: { color: a.color }, data: [[{ xAxis: a.xAxis[0] }, { xAxis: a.xAxis[1] }]] },
        })),
      ],
    } as EChartsOption;
  }, [events, recentEvents, referenceEvents, highlightFlight]);

  const header = `${verb} on ${frequency.recent.events} of ${frequency.recent.flights} recent flight`
    + `${frequency.recent.flights === 1 ? "" : "s"} · ${frequency.reference.events} of ${frequency.reference.flights} earlier`;

  return (
    <div>
      <div style={{ fontSize: 10, color: "var(--text-tertiary)", marginBottom: 2 }}>{header}</div>
      <EChartBase
        option={option}
        height={26}
        onPointClick={(data) => { if (Array.isArray(data) && typeof data[2] === "string") onOpenFlight(data[2]); }}
      />
    </div>
  );
}
