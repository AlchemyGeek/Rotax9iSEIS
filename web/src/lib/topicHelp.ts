import { useEffect, useState } from "react";
import { getEngineClient } from "./engineClient";
import { topicHelp as fixtureTopicHelp } from "./fixtures";
import type { TopicHelp, TopicHelpResult } from "../types/contract";

// Spec 03 §5.2: fetched once per engine profile and rule set, cached —
// not a per-flight call. Keyed by whatever the caller considers "this
// engine profile + rule set" (FlightView passes the provenance hashes
// already on every FlightAnalysis/InsightSet it has in hand).
const _cache = new Map<string, Promise<TopicHelpResult>>();

export function clearTopicHelpCache(): void {
  _cache.clear();
}

export function fetchTopicHelp(cacheKey: string, usingFixture: boolean): Promise<TopicHelpResult> {
  if (usingFixture) {
    return Promise.resolve(fixtureTopicHelp);
  }
  let pending = _cache.get(cacheKey);
  if (!pending) {
    pending = getEngineClient().getTopicHelp();
    _cache.set(cacheKey, pending);
  }
  return pending;
}

export function useTopicHelp(cacheKey: string, usingFixture: boolean): Record<string, TopicHelp> {
  const [byId, setById] = useState<Record<string, TopicHelp>>({});

  useEffect(() => {
    let cancelled = false;
    fetchTopicHelp(cacheKey, usingFixture)
      .then((result) => {
        if (cancelled) return;
        const next: Record<string, TopicHelp> = {};
        for (const t of result.topics) next[t.id] = t;
        setById(next);
      })
      .catch(() => {
        if (!cancelled) setById({});
      });
    return () => {
      cancelled = true;
    };
  }, [cacheKey, usingFixture]);

  return byId;
}
