import type { SeriesResult } from "./engineClient";
import type { SeriesFixture } from "../types/contract";

// The server's get_series/get_flight_series ops return {channel_id:
// points[]} — no label/unit, so the caller supplies a lookup (Spec 07:
// channel metadata now comes from the fetched channel registry, not a
// static frontend list) to build the fixture shape ChannelTimeline
// expects. Only channels the lookup actually recognizes are kept — an id
// the registry doesn't know about has nothing to label it with.
export function toSeriesFixture(
  flightId: string,
  raw: SeriesResult,
  metaFor: (id: string) => { label: string; unit: string } | undefined,
): SeriesFixture {
  const channels: SeriesFixture["channels"] = {};
  for (const [id, points] of Object.entries(raw)) {
    const meta = metaFor(id);
    if (!meta) continue;
    channels[id] = { unit: meta.unit, label: meta.label, points };
  }
  return { flight_id: flightId, channels };
}
