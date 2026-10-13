import type { CasEvent, CasInsightEvent, EcuClassification, NotLaneCheckReason } from "../types/contract";

// Spec 03 §5.2 (v0.14): a CAS event row names its class and, when the
// run nearly matched a lane check, why it isn't one. Same words as the
// engine's insight text (topics.NOT_LANE_CHECK_PHRASE).
export const NOT_LANE_CHECK_PHRASE: Record<NotLaneCheckReason, string> = {
  rpm_below_band: "below the lane-check band",
  rpm_above_band: "above the lane-check band",
  too_long: "longer than a lane check",
  moving: "while moving, so not a lane check",
  unpaired: "no second lane run",
};

export const ECU_CLASS_LABEL: Record<EcuClassification, string> = {
  GROUND_START: "at start",
  LANE_CHECK: "lane check",
  GROUND: "on the ground, engine running",
  IN_FLIGHT: "in flight",
  GROUND_SHUTDOWN: "at shutdown",
};

const rpmFmt = (v: number) => Math.round(v).toLocaleString("en-US");

function bandText(band: [number, number] | undefined): string {
  if (!band) return "";
  const [lo, hi] = band;
  return ` (${rpmFmt((lo + hi) / 2)} ± ${rpmFmt((hi - lo) / 2)})`;
}

export function notLaneCheckText(ev: Pick<CasEvent, "not_lane_check_reason" | "lane_check_band_rpm">): string | null {
  if (!ev.not_lane_check_reason) return null;
  const phrase = NOT_LANE_CHECK_PHRASE[ev.not_lane_check_reason];
  const isRpm = ev.not_lane_check_reason === "rpm_below_band" || ev.not_lane_check_reason === "rpm_above_band";
  return phrase + (isRpm ? bandText(ev.lane_check_band_rpm) : "");
}

// "ENGINE ECU · TAXI · 7 s · 2,550 rpm — below the lane-check band (4,000 ± 500)"
// withDuration false: for rows that show the duration in their own column.
export function casEventRowText(ev: CasInsightEvent | CasEvent, { casId = "ENGINE ECU", withDuration = true } = {}): string {
  const rpm = "context" in ev ? ev.context.rpm : ev.rpm;
  const parts = [
    casId,
    ev.classification === "IN_FLIGHT" ? `in flight · ${ev.phase}` : ev.phase,
  ];
  if (withDuration) parts.push(`${Math.round(ev.duration_s)} s`);
  if (rpm) parts.push(`${rpmFmt(rpm)} rpm`);
  let text = parts.join(" · ");
  const reason = notLaneCheckText(ev);
  if (reason) text += ` — ${reason}`;
  if (ev.phase_uncertain) text += " (flight phase uncertain)";
  return text;
}
