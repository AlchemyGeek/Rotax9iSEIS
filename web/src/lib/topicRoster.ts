import type {
  FlightAnalysis, Insight, InsightSeverity, MissingReason, ReferenceChangeMarker, TopicHelp, TopicResult,
} from "../types/contract";

// Spec 03 v0.16 §5.2 — the roster rule. Every evaluated topic has a card,
// but it is expanded only when it has something to say; otherwise it is
// one roster line (name · analysis · ?), expandable by tap.

export type ExpandReason = "insight" | "mirrored" | "marker" | "validity";

export interface CardMarker {
  kind: "rule_changed" | "reference_changed";
  marker: ReferenceChangeMarker;
}

export interface TopicCardModel {
  topic: TopicResult;
  reasons: ExpandReason[];
  badge: Insight | null; // own top insight, else the mirrored one
  mirrored: Insight | null;
  markers: CardMarker[];
  validityNotes: string[];
}

const SEVERITY_RANK: Record<InsightSeverity, number> = { limit: 0, warning: 1, watch: 2, info: 3 };

// Cards whose comparison comes from the reference (baseline, trend or
// model) — the ones an exclusion that moved the reference can change.
export const REFERENCE_DERIVED_TOPICS = new Set([
  "egt_spread", "egt_cyl_deviation", "oil_temp_peak", "coolant_temp_peak", "map_at_takeoff",
]);

const MISSING_TEXT: Record<MissingReason, string> = {
  NO_PHASE: "the flight phase it needs wasn't detected",
  CHANNEL_MISSING: "the channel isn't in this log",
  INSUFFICIENT_DATA: "not enough data on this flight",
  NOT_APPLICABLE: "doesn't apply to this flight",
  EXCLUDED: "this flight is excluded",
};

function topInsight(t: TopicResult): Insight | null {
  if (!t.insights.length) return null;
  return [...t.insights].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])[0];
}

export function topicCardModel(
  t: TopicResult,
  ctx: {
    insightsById: Map<string, Insight>;
    markers: ReferenceChangeMarker[];
    help?: TopicHelp;
    metrics: FlightAnalysis["metrics"];
  },
): TopicCardModel {
  const own = topInsight(t);
  const refId = t.limit_refs?.find((r) => r.insight_id)?.insight_id;
  const mirrored = refId ? ctx.insightsById.get(refId) ?? null : null;
  const markers: CardMarker[] = ctx.markers.flatMap((m): CardMarker[] => {
    if (m.cause_kind === "rule_edit" && m.cause_topic_id === t.topic_id) return [{ kind: "rule_changed", marker: m }];
    if (m.cause_kind === "exclusion" && REFERENCE_DERIVED_TOPICS.has(t.topic_id)) return [{ kind: "reference_changed", marker: m }];
    return [];
  });
  const validityNotes: string[] = [];
  const missing = t.metric_ids.map((id) => ctx.metrics[id]?.missing).find((r): r is MissingReason => Boolean(r));
  if (missing) validityNotes.push(`unavailable: ${MISSING_TEXT[missing]}`);
  if (ctx.help && !ctx.help.validated) validityNotes.push("not yet validated on this engine");

  const reasons: ExpandReason[] = [];
  if (own) reasons.push("insight");
  if (mirrored) reasons.push("mirrored");
  if (markers.length) reasons.push("marker");
  if (validityNotes.length) reasons.push("validity");
  return { topic: t, reasons, badge: own ?? mirrored, mirrored, markers, validityNotes };
}

// Expanded cards first, by severity (cards with only a marker or a
// validity note after any with a badge), then the roster in the engine's
// topic order. Disabled topics are roster lines of their own kind.
export function partitionTopicCards(cards: TopicCardModel[]): { expanded: TopicCardModel[]; roster: TopicCardModel[] } {
  const expanded: { c: TopicCardModel; i: number }[] = [];
  const roster: TopicCardModel[] = [];
  cards.forEach((c, i) => {
    if (c.topic.enabled !== false && c.reasons.length > 0) expanded.push({ c, i });
    else roster.push(c);
  });
  const rank = (c: TopicCardModel) => (c.badge ? SEVERITY_RANK[c.badge.severity] : 4);
  expanded.sort((a, b) => rank(a.c) - rank(b.c) || a.i - b.i);
  return { expanded: expanded.map((e) => e.c), roster };
}
