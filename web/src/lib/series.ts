import type { SeriesResult } from "./engineClient";
import type { SeriesFixture } from "../types/contract";
import { channelDef } from "./channels";

// The server's get_series/get_flight_series ops return {channel_id:
// points[]}; ChannelTimeline expects the fixture shape (label/unit per
// channel). Small adapter so live and fixture data render identically.
export function toSeriesFixture(flightId: string, raw: SeriesResult): SeriesFixture {
  const channels: SeriesFixture["channels"] = {};
  for (const [id, points] of Object.entries(raw)) {
    const def = channelDef(id);
    channels[id] = { unit: def.unit, label: def.label, points };
  }
  return { flight_id: flightId, channels };
}
