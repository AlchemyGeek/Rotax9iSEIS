import { useMemo, useRef, useState } from "react";
import type { ChannelRegistryEntry, SlotGroupEntry } from "../types/contract";

// Spec 07 §4 group order — matches the fixed table in the spec, not an
// alphabetical or registry-insertion order.
const GROUP_ORDER = ["engine", "egt", "fuel", "electrical", "flight", "conditions", "cabin"];
const GROUP_LABEL: Record<string, string> = {
  engine: "Engine", egt: "EGT", fuel: "Fuel", electrical: "Electrical",
  flight: "Flight", conditions: "Conditions", cabin: "Cabin",
};

function groupRank(g: string): number {
  const idx = GROUP_ORDER.indexOf(g);
  return idx === -1 ? GROUP_ORDER.length : idx;
}

interface PickerItem {
  id: string; // registry channel id, or a slot-group id (e.g. "egt_cyl")
  label: string;
  unit: string;
  description: string;
  group: string;
  isSlotGroup: boolean;
}

interface Props {
  registry: ChannelRegistryEntry[];
  slotGroups: SlotGroupEntry[];
  maxSlots: number;
  activeSlots: string[];
  availableChannels: string[] | null; // null = unknown (don't grey anything out)
  colorFor: (id: string) => string;
  onToggle: (slotId: string) => void;
  // The current preset's own registry group(s) (e.g. Cylinders -> egt +
  // engine) — every chartable channel in these groups shows as a tag in
  // the row, active or not, so a deselected topic-relevant channel is a
  // click away rather than a trip through "+ Add channel". null for
  // Overview (and when there's no base preset at all), which keeps its
  // original minimal row of only the active channels.
  expandGroups: Set<string> | null;
}

// The active-channel chip row doubles as the chart legend (Spec 05 §4,
// carried into Spec 07 §8) — a final "+ Add channel" chip opens the full
// browsable picker (search + grouped sections), which is where anything
// outside the current preset's own topic lives.
export function ChannelPicker({ registry, slotGroups, maxSlots, activeSlots, availableChannels, colorFor, onToggle, expandGroups }: Props) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const containerRef = useRef<HTMLDivElement>(null);

  const groupById = useMemo(() => new Map(slotGroups.map((sg) => [sg.id, sg])), [slotGroups]);
  // A channel's parent group, if it belongs to one — used for the §7.1
  // group/individual mutual-exclusivity swap and the "replaces X" hint.
  const parentGroupOf = useMemo(() => {
    const map = new Map<string, SlotGroupEntry>();
    for (const sg of slotGroups) for (const m of sg.members) map.set(m, sg);
    return map;
  }, [slotGroups]);

  const items = useMemo<PickerItem[]>(() => {
    const out: PickerItem[] = [];
    for (const sg of slotGroups) {
      const first = registry.find((c) => sg.members.includes(c.id));
      out.push({ id: sg.id, label: sg.label, unit: first?.unit ?? "", description: "All four cylinder EGTs together, one slot", group: first?.group ?? "egt", isSlotGroup: true });
    }
    // Individual channels — including slot-group members (Spec 07 §7.1:
    // offered alongside the group, not only through it, v0.2 reversing
    // the earlier "not in v0.1" call).
    for (const c of registry) {
      out.push({ id: c.id, label: c.label, unit: c.unit ?? "", description: c.description, group: c.group, isSlotGroup: false });
    }
    return out;
  }, [registry, slotGroups]);

  function itemFor(id: string): PickerItem | undefined {
    return items.find((i) => i.id === id);
  }

  function isUnavailable(item: PickerItem): boolean {
    if (!availableChannels) return false;
    const sg = groupById.get(item.id);
    const ids = sg ? sg.members : [item.id];
    return !ids.some((cid) => availableChannels.includes(cid));
  }

  // Would picking this item swap out an already-active sibling (the
  // group for one of its members, or vice versa) rather than add a new
  // slot outright? A swap frees at least as many slots as it uses
  // (§7.1), so it should never be blocked by a full chart.
  function replaces(item: PickerItem): string | undefined {
    if (item.isSlotGroup) {
      const sg = groupById.get(item.id);
      const activeMember = sg?.members.find((m) => activeSlots.includes(m));
      return activeMember ? itemFor(activeMember)?.label : undefined;
    }
    const parent = parentGroupOf.get(item.id);
    return parent && activeSlots.includes(parent.id) ? parent.label : undefined;
  }

  const chartFull = activeSlots.length >= maxSlots;

  // The row: just the active channels (Overview, or no base preset), or
  // every tag in the current preset's own groups plus any active channel
  // from outside them (picked via the popover), topic-sorted rather than
  // activation-ordered once the row is showing more than just actives.
  const rowTags = useMemo<PickerItem[]>(() => {
    if (!expandGroups) {
      return activeSlots.map((id) => itemFor(id)).filter((i): i is PickerItem => Boolean(i));
    }
    const activeSet = new Set(activeSlots);
    return items
      .filter((i) => expandGroups.has(i.group) || activeSet.has(i.id))
      .sort((a, b) => groupRank(a.group) - groupRank(b.group) || items.indexOf(a) - items.indexOf(b));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandGroups, items, activeSlots]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const matches = (i: PickerItem) => !q || i.label.toLowerCase().includes(q) || i.description.toLowerCase().includes(q) || i.id.toLowerCase().includes(q);
    const byGroup = new Map<string, PickerItem[]>();
    for (const item of items) {
      if (!matches(item)) continue;
      if (!byGroup.has(item.group)) byGroup.set(item.group, []);
      byGroup.get(item.group)!.push(item);
    }
    return GROUP_ORDER.map((g) => ({ group: g, items: byGroup.get(g) ?? [] })).filter((g) => g.items.length > 0);
  }, [items, search]);

  function renderTag(item: PickerItem) {
    const isActive = activeSlots.includes(item.id);
    const color = colorFor(item.id === "egt_cyl" ? "egt1_f" : item.id);
    if (isActive) {
      return (
        <span
          key={item.id}
          onClick={() => onToggle(item.id)}
          style={{
            display: "flex", alignItems: "center", gap: 5, padding: "5px 11px", borderRadius: 14,
            fontSize: 11, fontWeight: 600, cursor: "pointer",
            background: `${color}26`, border: `1px solid ${color}`, color,
          }}
        >
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: color }} />
          {item.label} ✕
        </span>
      );
    }
    const unavailable = isUnavailable(item);
    const replacesLabel = replaces(item);
    const disabled = !replacesLabel && (chartFull || unavailable);
    return (
      <span
        key={item.id}
        onClick={() => !disabled && onToggle(item.id)}
        title={unavailable ? "Not recorded in this log" : replacesLabel ? `replaces ${replacesLabel}` : undefined}
        style={{
          display: "flex", alignItems: "center", gap: 5, padding: "5px 11px", borderRadius: 14,
          fontSize: 11, cursor: disabled ? "default" : "pointer", background: "transparent",
          border: "1px dashed var(--border)", color: "var(--text-secondary)", opacity: disabled ? 0.45 : 1,
        }}
      >
        {item.label}
      </span>
    );
  }

  return (
    <div ref={containerRef} style={{ position: "relative", marginBottom: 14 }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
        {rowTags.map(renderTag)}
        <span
          onClick={() => setOpen((v) => !v)}
          style={{
            display: "flex", alignItems: "center", gap: 5, padding: "5px 11px", borderRadius: 14,
            fontSize: 11, cursor: "pointer", background: "transparent",
            border: "1px dashed var(--border)", color: "var(--text-secondary)",
          }}
        >
          + Add channel
        </span>
      </div>

      {open && (
        <>
          <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 20 }} />
          <div
            style={{
              position: "absolute", top: "calc(100% + 8px)", left: 0, zIndex: 21,
              width: 360, maxHeight: 420, overflowY: "auto",
              background: "var(--panel-control)", border: "1px solid var(--border)", borderRadius: 10,
              boxShadow: "0 8px 24px rgba(0,0,0,0.4)", padding: 10,
            }}
          >
            <input
              autoFocus
              type="text"
              placeholder="Search channels…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: "100%", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6,
                padding: "7px 10px", color: "var(--text-primary)", fontSize: 12, marginBottom: 8, boxSizing: "border-box",
              }}
            />
            {chartFull && (
              <div style={{ fontSize: 11, color: "var(--severity-warning)", marginBottom: 8 }}>
                Chart is full — remove a channel to add another.
              </div>
            )}
            {filtered.map(({ group, items: groupItems }) => (
              <div key={group} style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", marginBottom: 4 }}>
                  {(GROUP_LABEL[group] ?? group).toUpperCase()}
                </div>
                {groupItems.map((item) => {
                  const isActive = activeSlots.includes(item.id);
                  const unavailable = isUnavailable(item);
                  const replacesLabel = replaces(item);
                  const disabled = !isActive && !replacesLabel && (chartFull || unavailable);
                  return (
                    <div
                      key={item.id}
                      onClick={() => !disabled && onToggle(item.id)}
                      title={unavailable ? "Not recorded in this log" : undefined}
                      style={{
                        display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8,
                        padding: "6px 8px", borderRadius: 6, cursor: disabled ? "default" : "pointer",
                        background: isActive ? "rgba(79,195,176,0.12)" : "transparent",
                        opacity: disabled ? 0.45 : 1,
                      }}
                    >
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: isActive ? 600 : 400 }}>
                          {item.label} {item.unit && <span style={{ color: "var(--text-tertiary)" }}>({item.unit})</span>}
                        </div>
                        <div style={{ fontSize: 10, color: "var(--text-tertiary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                          {unavailable ? "Not recorded in this log" : replacesLabel ? `replaces ${replacesLabel}` : item.description}
                        </div>
                      </div>
                      {isActive && <span style={{ fontSize: 11, color: "var(--accent)", flexShrink: 0 }}>✓</span>}
                    </div>
                  );
                })}
              </div>
            ))}
            {filtered.length === 0 && (
              <div style={{ fontSize: 12, color: "var(--text-tertiary)", padding: "8px 4px" }}>No channels match.</div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
