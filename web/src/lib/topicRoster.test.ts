import { describe, it, expect } from "vitest";
import { partitionTopicCards, topicCardModel } from "./topicRoster";
import type { FlightAnalysis, Insight, ReferenceChangeMarker, TopicHelp, TopicResult } from "../types/contract";

// Spec 03 v0.16 §5.2 — the roster rule: expanded only for a fired insight,
// a mirrored badge, a change marker or a validity note; otherwise one line.

const insight = (id: string, severity: Insight["severity"]): Insight => ({
  id, topic_id: "x", rule_id: "x.r", trigger: "threshold", severity,
  message: { text: id }, evidence: [], confidence: { level: "GOOD", n: 10 },
} as unknown as Insight);

const topic = (id: string, extra: Partial<TopicResult> = {}): TopicResult => ({
  topic_id: id, analysis: { text: `${id} analysis` }, insights: [], metric_ids: [`${id}_m`], enabled: true, ...extra,
});

const marker = (kind: "rule_edit" | "exclusion", topicId: string | null): ReferenceChangeMarker => ({
  id: `m-${kind}`, flight_id: "f1", at: "2026-10-13T00:00:00Z", cause_journal_entry_id: "j1", cause_kind: kind,
  cause_flight_id: kind === "exclusion" ? "f2" : null, cause_topic_id: topicId, reason: "test", resolved: false,
});

const help = (validated: boolean) => ({ validated } as TopicHelp);

function model(t: TopicResult, opts: { byId?: Map<string, Insight>; markers?: ReferenceChangeMarker[]; help?: TopicHelp; metrics?: FlightAnalysis["metrics"] } = {}) {
  return topicCardModel(t, { insightsById: opts.byId ?? new Map(), markers: opts.markers ?? [], help: opts.help ?? help(true), metrics: opts.metrics ?? {} });
}

describe("roster rule", () => {
  it("collapses a topic with nothing to say", () => {
    expect(model(topic("egt_spread")).reasons).toEqual([]);
  });

  it("expands for a fired insight", () => {
    expect(model(topic("egt_spread", { insights: [insight("i1", "watch")] })).reasons).toEqual(["insight"]);
  });

  it("expands for a mirrored badge", () => {
    const lim = insight("lim1", "limit");
    const m = model(topic("oil_temp_peak", { limit_refs: [{ limit_id: "oil_temp_max", insight_id: "lim1" }] }), { byId: new Map([["lim1", lim]]) });
    expect(m.reasons).toEqual(["mirrored"]);
    expect(m.badge).toBe(lim);
  });

  it("expands for a rule-changed marker on its own topic, and a reference-changed one on reference-derived topics", () => {
    expect(model(topic("overboost_time"), { markers: [marker("rule_edit", "overboost_time")] }).reasons).toEqual(["marker"]);
    expect(model(topic("overboost_time"), { markers: [marker("rule_edit", "egt_spread")] }).reasons).toEqual([]);
    expect(model(topic("egt_spread"), { markers: [marker("exclusion", null)] }).reasons).toEqual(["marker"]);
    expect(model(topic("overboost_time"), { markers: [marker("exclusion", null)] }).reasons).toEqual([]);
  });

  it("expands for a validity note: unavailable metric, or not validated on this engine", () => {
    const missing = model(topic("map_at_takeoff"), { metrics: { map_at_takeoff_m: { id: "map_at_takeoff_m", value: null, missing: "CHANNEL_MISSING" } } });
    expect(missing.reasons).toEqual(["validity"]);
    expect(missing.validityNotes[0]).toMatch(/^unavailable: /);
    expect(model(topic("egt_spread"), { help: help(false) }).validityNotes).toEqual(["not yet validated on this engine"]);
  });

  it("orders expanded cards by severity, then the roster in engine order; disabled topics stay in the roster", () => {
    const cards = [
      model(topic("a")),
      model(topic("b", { insights: [insight("ib", "watch")] })),
      model(topic("c", { enabled: false })),
      model(topic("d", { insights: [insight("id", "limit")] })),
      model(topic("e"), { help: help(false) }),
    ];
    const { expanded, roster } = partitionTopicCards(cards);
    expect(expanded.map((c) => c.topic.topic_id)).toEqual(["d", "b", "e"]);
    expect(roster.map((c) => c.topic.topic_id)).toEqual(["a", "c"]);
  });
});
