import type { FleetAnalysis, TrendsPanel } from "../types/contract";

// Spec 12 §9.1 (Session F) — three panel tiers, so the page reads top
// to bottom as "what moved -> what is being watched -> what has never
// been a problem". Membership comes from engine output only
// (change_summary, readiness) — no web-side heuristics.

export interface Tiers {
  tier1: TrendsPanel[]; // qualifying — holds a change-summary row, in summary order
  tier2: TrendsPanel[]; // trendable, nothing to report — engine's own panel order preserved
  tier3: TrendsPanel[]; // never exceeded — collapsed into one group, not rendered as panels
}

function rankByMetric(fleet: FleetAnalysis): Map<string, number> {
  const ranks = new Map<string, number>();
  for (const row of fleet.change_summary) {
    for (const id of row.members ?? [row.metric_id]) ranks.set(id, row.rank);
  }
  return ranks;
}

function panelRank(panel: TrendsPanel, ranks: Map<string, number>): number | null {
  let min: number | null = null;
  for (const m of panel.metrics) {
    const r = ranks.get(m.metric_id);
    if (r != null && (min === null || r < min)) min = r;
  }
  return min;
}

// §9.1 tier 3: "every limit whose only badge is never exceeded" — a
// non-limit (register) panel is never tier 3, and a limit panel only
// qualifies when *every* one of its sub-metrics (peak_excess,
// time_above_pct, block_s — they always share one readiness, Session
// C's Pass 3) reads no_events.
function isNeverExceeded(panel: TrendsPanel, fleet: FleetAnalysis): boolean {
  if (!panel.limit_id) return false;
  return panel.metrics.every((m) => fleet.metrics[m.metric_id]?.readiness?.kind === "no_events");
}

export function computeTiers(panels: TrendsPanel[], fleet: FleetAnalysis): Tiers {
  const ranks = rankByMetric(fleet);
  const tier1: { panel: TrendsPanel; rank: number }[] = [];
  const tier2: TrendsPanel[] = [];
  const tier3: TrendsPanel[] = [];

  for (const panel of panels) {
    const rank = panelRank(panel, ranks);
    if (rank !== null) {
      tier1.push({ panel, rank });
    } else if (isNeverExceeded(panel, fleet)) {
      tier3.push(panel);
    } else {
      tier2.push(panel);
    }
  }

  tier1.sort((a, b) => a.rank - b.rank);
  return { tier1: tier1.map((t) => t.panel), tier2, tier3 };
}

// §8.4/§8.3 (Session F, replacing the page-level researcher toggle):
// a panel gets the *Show detail strips* affordance when it has a real
// whole-history fit on any metric, or a `_time_above_pct` metric at
// all (always present on an ordinary limit panel, absent on overboost's
// block_s-only one).
export function panelHasDetailStrips(panel: TrendsPanel, fleet: FleetAnalysis): boolean {
  return panel.metrics.some((m) => {
    if (m.metric_id.endsWith("_time_above_pct")) return true;
    return (fleet.metrics[m.metric_id]?.trend?.slope ?? null) !== null;
  });
}
