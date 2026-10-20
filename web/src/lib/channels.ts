import { colors } from "../theme/colors";

// Spec 07 §12: channel metadata (label/unit/group/chartable/slot_group)
// now comes from the backend registry (get_channel_registry) — the
// engine's CHANNEL_REGISTRY is the single source of truth (D4), this
// file keeps only what's inherently a frontend concern: color.

// The 8 channels charted before this spec keep their fixed tokens
// (Spec 07 §9) so returning users don't see their usual lines repainted
// a different color on the same flights they already know.
// Read from the palette in effect each time (Spec 15 §9: the light theme
// has its own values), never copied at load.
const FIXED_CHANNEL_TOKENS: Record<string, keyof typeof colors> = {
  rpm: "chartRpm",
  ias_kt: "chartIas",
  oil_temp_f: "chartOilTemp",
  egt_spread_f: "chartEgtSpread",
  coolant_temp_f: "chartCoolantTemp",
  map_inhg: "chartMap",
  fuel_flow_gph: "chartFuelFlow",
  vs_fpm: "chartVs",
};
export function fixedChannelColor(id: string): string | undefined {
  const token = FIXED_CHANNEL_TOKENS[id];
  return token ? (colors[token] as string) : undefined;
}

// Any other channel gets a color from this 6-slot palette when activated
// (Spec 07 §9) — chosen to stay clear of the severity palette (reds/
// oranges/yellows) and the phase-tint palette (theme/colors.ts, lib/
// phases.ts), in both light and dark themes.
export const SLOT_PALETTE = ["#38BDF8", "#34D399", "#A78BFA", "#F472B6", "#22D3EE", "#818CF8"];

// egt_cyl (Spec 07 D3): one hue family, four lightness steps, cylinder 1→4.
// (theme/colors.ts egtCyl, per theme.)

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
    const fixed = fixedChannelColor(id);
    if (fixed) {
      next[id] = fixed;
      continue;
    }
    const cylIdx = egtCylinderIndex(id);
    if (cylIdx !== null) {
      next[id] = colors.egtCyl[cylIdx] ?? SLOT_PALETTE[0];
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

// Spec 14 v0.14 §5.3: once a raw general-purpose channel is assigned, it
// is offered under its registry name only — the raw id leaves the picker.
export function pickableChannels(
  available: string[] | null | undefined,
  assignments: Record<string, string> | undefined,
): string[] | null | undefined {
  if (!available || !assignments) return available;
  return available.filter((id) => !(id in assignments));
}
