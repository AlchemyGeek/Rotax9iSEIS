import { colors } from "../theme/colors";

// Spec 07 §12: channel metadata (label/unit/group/chartable/slot_group)
// now comes from the backend registry (get_channel_registry) — the
// engine's CHANNEL_REGISTRY is the single source of truth (D4), this
// file keeps only what's inherently a frontend concern: color.

// The 8 channels charted before this spec keep their fixed tokens
// (Spec 07 §9) so returning users don't see their usual lines repainted
// a different color on the same flights they already know.
export const FIXED_CHANNEL_COLORS: Record<string, string> = {
  rpm: colors.chartRpm,
  ias_kt: colors.chartIas,
  oil_temp_f: colors.chartOilTemp,
  egt_spread_f: colors.chartEgtSpread,
  coolant_temp_f: colors.chartCoolantTemp,
  map_inhg: colors.chartMap,
  fuel_flow_gph: colors.chartFuelFlow,
  vs_fpm: colors.chartVs,
};

// Any other channel gets a color from this 6-slot palette when activated
// (Spec 07 §9) — chosen to stay clear of the severity palette (reds/
// oranges/yellows) and the phase-tint palette (theme/colors.ts, lib/
// phases.ts), in both light and dark themes.
export const SLOT_PALETTE = ["#38BDF8", "#34D399", "#A78BFA", "#F472B6", "#22D3EE", "#818CF8"];

// egt_cyl (Spec 07 D3): one hue family, four lightness steps, cylinder 1→4.
export const EGT_CYL_COLORS = ["#FDE68A", "#FBBF24", "#D97706", "#92400E"];

function egtCylinderIndex(id: string): number | null {
  const m = /^egt([1-4])_f$/.exec(id);
  return m ? Number(m[1]) - 1 : null;
}

// Stable, identity-based slot-color assignment (Spec 07 §9): a channel
// keeps its color for as long as it stays active, and a color is only
// reused once the channel holding it is deactivated ("released on
// removal") — not reassigned from scratch every render, which would
// make an unrelated add/remove reshuffle colors already on screen.
export function assignChannelColors(activeIds: string[], prev: Record<string, string>): Record<string, string> {
  const next: Record<string, string> = {};
  const usedSlotColors = new Set<string>();

  for (const id of activeIds) {
    if (FIXED_CHANNEL_COLORS[id]) {
      next[id] = FIXED_CHANNEL_COLORS[id];
      continue;
    }
    const cylIdx = egtCylinderIndex(id);
    if (cylIdx !== null) {
      next[id] = EGT_CYL_COLORS[cylIdx] ?? SLOT_PALETTE[0];
    }
  }
  for (const id of activeIds) {
    if (next[id]) continue;
    const carried = prev[id];
    if (carried && SLOT_PALETTE.includes(carried) && !usedSlotColors.has(carried)) {
      next[id] = carried;
      usedSlotColors.add(carried);
    }
  }
  for (const id of activeIds) {
    if (next[id]) continue;
    const free = SLOT_PALETTE.find((c) => !usedSlotColors.has(c));
    next[id] = free ?? colors.textSecondary;
    if (free) usedSlotColors.add(free);
  }
  return next;
}
