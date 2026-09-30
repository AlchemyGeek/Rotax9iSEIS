// Weather-band colours, shared by the Trends view's stratified charts and
// the Notes page's filter charts. Same cool->warm gradient regardless of
// band_kind — cold/low both read as "the calm end," hot/very_high both as
// "the extreme end," so the color means the same thing whichever band_kind
// is actually active for a given metric (Spec 01 §8.4 v0.10's real band
// sets, never a mixed vocabulary the pilot has to relearn per metric).
export const BAND_ORDER: Record<string, number> = { cold: 0, low: 0, mild: 1, moderate: 1, warm: 2, high: 2, hot: 3, very_high: 3 };
const BAND_PALETTE = ["#38BDF8", "#4FC3B0", "#F5A524", "#E5484D"];

export function bandColor(name: string): string {
  const idx = BAND_ORDER[name];
  return idx !== undefined ? BAND_PALETTE[idx] : "#94A3B8";
}

export function bandLabel(name: string): string {
  return name.replace(/_/g, " ");
}
