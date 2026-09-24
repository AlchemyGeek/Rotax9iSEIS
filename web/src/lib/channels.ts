import { colors } from "../theme/colors";

export interface ChannelDef {
  id: string;
  label: string;
  unit: string;
  color: string;
}

// Subset of the Spec 01 §6.4 channel registry relevant to the timeline —
// ids/units match slingology_eis/channels.py exactly since the server
// re-parses the real log for whatever channels are requested.
export const CHANNEL_REGISTRY: ChannelDef[] = [
  { id: "rpm", label: "RPM", unit: "rpm", color: colors.chartRpm },
  { id: "ias_kt", label: "IAS", unit: "kt", color: colors.chartIas },
  { id: "oil_temp_f", label: "Oil Temp", unit: "°F", color: colors.chartOilTemp },
  { id: "egt_spread_f", label: "EGT Spread", unit: "°F", color: colors.chartEgtSpread },
  { id: "coolant_temp_f", label: "Coolant Temp", unit: "°F", color: colors.chartCoolantTemp },
  { id: "map_inhg", label: "MAP", unit: "inHg", color: colors.chartMap },
  { id: "fuel_flow_gph", label: "Fuel Flow", unit: "gal/hr", color: colors.chartFuelFlow },
  { id: "vs_fpm", label: "Vertical Speed", unit: "ft/min", color: colors.chartVs },
];

export const DEFAULT_ACTIVE_CHANNELS = ["rpm", "ias_kt", "oil_temp_f", "egt_spread_f"];
export const ALL_CHANNEL_IDS = CHANNEL_REGISTRY.map((c) => c.id);

export function channelDef(id: string): ChannelDef {
  return CHANNEL_REGISTRY.find((c) => c.id === id) ?? { id, label: id, unit: "", color: colors.textSecondary };
}
