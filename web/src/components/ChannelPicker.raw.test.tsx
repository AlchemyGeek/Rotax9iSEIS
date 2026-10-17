import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { ChannelPicker } from "./ChannelPicker";
import { pickableChannels } from "../lib/channels";
import type { ChannelRegistryEntry } from "../types/contract";

// Spec 01 v0.23 §6.5 / Spec 14 v0.14 §5.3: unassigned general-purpose
// inputs are offered raw under "Raw inputs", only where the log has them;
// an assigned one is offered under its registry name only.

const entry = (id: string, label: string, group: string, unit: string | null = null): ChannelRegistryEntry => ({
  id, label, group, unit, description: "", slot_group: null, companions: [], unit_variant_of: null,
});
const REGISTRY = [
  entry("rpm", "RPM", "engine", "rpm"),
  entry("co_ppm", "CO", "cabin", "ppm"),
  ...[1, 3, 7].map((n) => entry(`gp_analog_${n}`, `Analog ${n}`, "raw")),
];

function openPicker(available: string[] | null) {
  render(
    <ChannelPicker registry={REGISTRY} slotGroups={[]} maxSlots={6} activeSlots={["rpm"]}
      availableChannels={available} colorFor={() => "#fff"} onToggle={() => {}} expandGroups={null} />,
  );
  fireEvent.click(screen.getByText("+ Add channel"));
}

describe("ChannelPicker — raw inputs", () => {
  it("lists only the raw inputs this log carries, under Raw inputs", () => {
    openPicker(["rpm", "gp_analog_3", "gp_analog_7"]);
    expect(screen.getByText("RAW INPUTS")).toBeTruthy();
    expect(screen.getByText("Analog 3")).toBeTruthy();
    expect(screen.getByText("Analog 7")).toBeTruthy();
    expect(screen.queryByText("Analog 1")).toBeNull();
  });

  it("a G3X log: no Raw inputs group at all", () => {
    openPicker(["rpm"]);
    expect(screen.queryByText("RAW INPUTS")).toBeNull();
  });

  it("an assigned input is offered by its registry name, not its raw id", () => {
    openPicker(pickableChannels(["rpm", "gp_analog_3", "gp_analog_7", "co_ppm"], { gp_analog_7: "co_ppm" }) ?? null);
    expect(screen.queryByText("Analog 7")).toBeNull();
    expect(screen.getByText("Analog 3")).toBeTruthy();
    expect(screen.getByText("CO")).toBeTruthy();
  });
});
