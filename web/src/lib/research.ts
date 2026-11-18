// Spec 06 — the web's Research helpers. Nothing here computes a result:
// every number comes from the host (§11, API-first). Since Spec 06 v1.0
// (Spec 16 D15) the pages have no hand studies; what remains is channel
// labels and formatting for the Flight view's Signal read-out.

export const CHANNEL_LABELS: Record<string, string> = {
  rpm: "RPM", map_inhg: "MAP", fuel_flow_gph: "Fuel flow", egt1_f: "EGT 1", egt2_f: "EGT 2", egt3_f: "EGT 3", egt4_f: "EGT 4",
  oil_press_psi: "Oil pressure", oil_temp_f: "Oil temperature", coolant_temp_f: "Coolant temperature",
  fuel_press_psi: "Fuel pressure", main_volts: "Main volts", ias_kt: "IAS", vs_fpm: "Vertical speed", power_pct: "Power",
  egt_spread_f: "EGT spread", egt_mean_f: "EGT mean", batt_amps: "Battery amps", throttle_pct: "Throttle",
};

export function channelLabel(id: string): string {
  return CHANNEL_LABELS[id] ?? id;
}

// ── Formatting ──────────────────────────────────────────────────────────────

export function fmtClock(s: number): string {
  const m = Math.floor(s / 60), r = Math.round(s % 60);
  return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
}

export function fmtNum(v: unknown, nd = 1): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v !== "number" || !isFinite(v)) return String(v);
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return v.toLocaleString(undefined, { maximumFractionDigits: nd });
}

export function fmtRef(r: { value: number | [number, number] | null; unit?: string }): string {
  if (r.value === null || r.value === undefined) return "—";
  const u = r.unit ? ` ${r.unit}` : "";
  if (Array.isArray(r.value)) return `${fmtNum(r.value[0])}–${fmtNum(r.value[1])}${u}`;
  return `${fmtNum(r.value)}${u}`;
}

export function downloadText(filename: string, text: string, type = "text/plain") {
  const blob = new Blob([text], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// Spec 06 D5 / acceptance 9: no verdict words in text we write ourselves.
// The result sentences come from the engine (checked there); this guards
// the page's own labels in a test.
export const FORBIDDEN_UI_WORDS = ["abnormal", "fault", "defect", "cycling detected", "failure"];
