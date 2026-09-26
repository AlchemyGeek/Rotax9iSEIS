# Spec 07 — Flight Chart: Channel Registry, Picker, and Presets

**Project:** SlingologyEIS web platform
**Status:** Draft v0.2 — design agreed, ready for implementation when instructed
**Suggested repo path:** `docs/specs/07-flight-chart-channels-and-presets.md`
**Builds on:** Spec 01 v0.4 (§6.4 channel registry, §8.7 SeriesData, insight evidence), Spec 02 (app vs. workspace settings), Spec 03 v0.5 (§5.2 palettes, §6.1 Flight view), Spec 05 v0.2 (§4 overlaid indexed timeline, channel picker)
**Depends on:** the downsampling fix (§11.2), which is tracked and implemented separately
**Numbering:** 06 stays reserved for the tabled research-mode feature (Spec 05 note).

**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial draft. Presets first-class; hard cap of 6 slots; registry as single source of truth. |
| 0.2 | Open questions Q1–Q5 resolved (§15). User presets are app-level. The chart opens on the last-used preset, and chart state carries across flights. Individual cylinder EGTs are offered alongside the group and are mutually exclusive with it. Insight context channels come from registry `companions`, not `insight_rules.json`; the `context_channels` evidence field is dropped. The downsampling fix is split out as a prerequisite. |

---

## 1. Purpose

The Flight view's timeline currently offers 8 hand-picked channels. The engine registry declares 46 channels, and 45 of them load from a real log. This spec makes the full chartable set usable without turning the picker into a wall of chips. It does that through three mechanisms, in the order a pilot meets them:

1. **Presets.** One tap answers a common question ("how are my cylinders?"). This is the primary path.
2. **A grouped, searchable picker** for anything a preset doesn't cover.
3. **Insight-driven channels.** Clicking an insight's evidence shows the channels that explain it.

The design follows the project's minimize-user-input principle. Most chart sessions should take one tap and no channel hunting.

## 2. Decisions

| # | Decision |
|---|---|
| D1 | Presets are a first-class feature. They are defined in a config file, validated, and extensible by users. |
| D2 | A single chart holds at most **6 slots**. The cap is hard: the UI never silently replaces a channel to make room. |
| D3 | Cylinder EGTs 1–4 form a **channel group** that occupies one slot. Individual cylinders are also offered, one slot each, and are mutually exclusive with the group (§7.1). |
| D4 | The engine's channel registry is the single source of truth for which channels exist and can be charted. The UI keeps no parallel list. |
| D5 | Series data is fetched lazily, per channel, as channels become active (as Spec 03 §6.1 already requires). |
| D6 | There is **one set of presets for the whole app**: the same in every flight and every workspace. User presets are stored in app-level settings. |
| D7 | The Flight view opens on the **last-used preset**. Chart state (a preset or a Modified channel set) **carries across flights** within a session. No flight has its own view. |
| D8 | Insight context channels come from each channel's **`companions`** in the registry. Display hints stay out of `insight_rules.json`, so editing them never changes the rules hash or makes analyses look stale. |
| D9 | The downsampling fix (§11.2) is a separate change that lands before this spec is implemented. |

## 3. Findings from the current code (webui @ 06270da)

1. **Hard-coded list.** `web/src/lib/channels.ts` defines 8 channels. `ChannelPicker.tsx` renders exactly those. The set matches the channels in `flight-kacv-series.json`, not any spec.
2. **Registry flags are ignored.** `channels.py` marks 19 channels `charted_by_default`. Eleven of them (`power_pct`, `egt1_f`–`egt4_f`, `baro_alt_ft`, `oat_c`, `da_ft`) can't be charted today.
3. **Defaults are written three times.** The default channel list appears in `channels.ts` and twice in `server.py` (`op_get_series`, `op_get_flight_series`).
4. **Fetching is eager.** `FlightView.tsx` requests `ALL_CHANNEL_IDS` up front.
5. **Evidence channels are ignored.** `handleEvidenceClick` zooms to a `series_window` but doesn't use its `channels`. The only producer found, `limit_exceedances` in `operations.py`, sets `channels` to the single exceeded parameter.
6. **Downsampling loses peaks (bug; fixed separately per D9).** `_downsample_series` samples every channel at the rows of one reference channel's min/max envelope. Measured on `log_20260423_200615_KACV.csv` at 400 buckets:

   | Channel | Full-res max | Charted max |
   |---|---|---|
   | co_ppm | 238.0 | 34.0 |
   | egt_spread_f | 180.0 | 170.0 |
   | map_inhg | 48.6 | 48.2 |
   | egt4_f | 1610.0 | 1605.0 |

   RPM's charted minimum is 1,730 against a true 0, which also suggests a NaN-handling problem in the envelope.

## 4. Channel registry changes (`slingology_eis/channels.py`, Spec 01 §6.4)

Add fields to `ChannelDef`:

| Field | Type | Purpose |
|---|---|---|
| `label` | str | Short UI label ("Oil Temp", "MAP"). The existing `description` stays as the long form, shown in the picker and tooltips. |
| `group` | str | Picker section: `engine`, `egt`, `fuel`, `electrical`, `flight`, `conditions`, `cabin`. |
| `chartable` | bool | False for channels that don't belong on an indexed line chart. |
| `slot_group` | str \| None | Membership of a slot group (D3). v0.2 has only `egt_cyl` (egt1_f–egt4_f). |
| `companions` | list[str] | Channels that give context when this channel is the subject of an insight (§10). They must be chartable registry ids. |
| `unit_variant_of` | str \| None | Marks metric/imperial twins (for example `oil_temp_c` → `oil_temp_f`), so the app's `units` setting can choose one later instead of offering both. |

`charted_by_default` is retired. Presets (§6) replace it.

Slot groups are declared separately:

```python
SLOT_GROUPS = {
    "egt_cyl": SlotGroup(id="egt_cyl", label="Cylinder EGTs (1–4)",
                         members=["egt1_f", "egt2_f", "egt3_f", "egt4_f"]),
}
MAX_CHART_SLOTS = 6
```

**Group assignment (36 chartable channels):**

| Group | Channels |
|---|---|
| engine | rpm, power_pct, map_inhg, oil_press_psi, oil_temp_f, coolant_temp_f |
| egt | egt1_f–egt4_f (slot group `egt_cyl`), egt_spread_f, egt_max_f, egt_min_f, egt_mean_f |
| fuel | fuel_flow_gph, fuel_press_psi, fuel_qty_l_gal, fuel_qty_r_gal |
| electrical | main_volts, batt_amps |
| flight | baro_alt_ft, press_alt_ft, gps_alt_ft, vs_fpm, ias_kt, tas_kt, gnd_spd_kt, pitch_deg, roll_deg, lat_g, norm_g |
| conditions | oat_c, da_ft, baro_inhg, wind_spd_kt |
| cabin | co_ppm |

**Not chartable:** `lat`, `lon` (map), `track_deg` and `wind_dir_deg` (wrap at 360°, which breaks the 0–100% index), `phase` (drawn as the background band), and the unit variants `oil_temp_c`, `coolant_temp_c`, `oat_f`, `map_hpa`, `fuel_flow_lph`.

**Companions (v0.2).** These cover every parameter that has a limit in `engines/916iS.json`, since limit exceedances are today's only producer of `series_window` evidence:

| Channel | Companions | Why |
|---|---|---|
| rpm | map_inhg, power_pct | Power setting context for idle-low and over-limit RPM |
| map_inhg | rpm, power_pct | Overboost read against the power demand |
| oil_press_psi | oil_temp_f, rpm | Pressure depends on temperature and RPM |
| oil_temp_f | coolant_temp_f, oat_c | Thermal context and ambient |
| coolant_temp_f | oil_temp_f, oat_c | Thermal context and ambient |
| egt1_f–egt4_f | egt_spread_f, power_pct | Cylinder against its peers and power |
| fuel_press_psi | fuel_flow_gph, rpm | Demand context; pump test at low RPM |
| main_volts | batt_amps, rpm | Charging state; alternator speed |

Other chartable channels start with an empty `companions`. They can be filled in when a producer of insight evidence starts referencing them.

## 5. Per-flight channel availability

Older or Garmin Pilot exports may lack columns. The picker needs to know before the user taps.

- Add `available_channels: string[]` to `FlightAnalysis`: the chartable registry ids present and not entirely NaN in the loaded frame. It is computed at ingest and cached with the analysis, so no extra re-parse is needed.
- An unavailable channel appears greyed in the picker with the reason "Not recorded in this log".
- A preset containing an unavailable channel applies the rest and shows a quiet note ("Fuel Press not recorded in this log"). The preset itself stays selected, so the chart keeps the same state as you move on to a flight that does record the channel (D7).

## 6. Presets

### 6.1 Where they live

- **Shipped presets:** `chart_presets.json` at the repo root, next to `insight_rules.json`. They are engine-agnostic, because all four iS engines log the same channels.
- **User presets:** `AppSettings.chart_presets` (Spec 02 §6.6), shared by every workspace (D6).
- Shipped presets are read-only in the UI. "Duplicate and edit" creates a user preset.

### 6.2 Schema

```json
{
  "version": 1,
  "presets": [
    {
      "id": "cylinders",
      "label": "Cylinders",
      "description": "Per-cylinder EGT against power — balance and outliers",
      "channels": ["egt_cyl", "egt_spread_f", "power_pct"]
    }
  ]
}
```

- `channels` holds registry ids or slot-group ids, in legend order.
- `id` is unique across shipped and user presets. User preset ids get a `user.` prefix to avoid collisions.

### 6.3 Validation (engine side, one function used by both loader and save)

A preset is rejected on save, or skipped on load with a diagnostic, if it:
- references an unknown id or a `chartable: false` channel,
- exceeds 6 slots (a slot group counts once),
- contains both a slot group and one of its members (§7.1),
- is empty, or has a duplicate id.

New diagnostic: `PRESET_INVALID` (warning level). It fires on load and never blocks the app.

### 6.4 Shipped set

| id | Label | Channels | Slots |
|---|---|---|---|
| overview | Overview | rpm, ias_kt, oil_temp_f, egt_spread_f | 4 |
| cylinders | Cylinders | egt_cyl, egt_spread_f, power_pct | 3 |
| thermal | Thermal | oil_temp_f, coolant_temp_f, oat_c, vs_fpm | 4 |
| power | Power | rpm, map_inhg, power_pct, fuel_flow_gph | 4 |
| fuel | Fuel system | fuel_press_psi, fuel_flow_gph, fuel_qty_l_gal, fuel_qty_r_gal | 4 |
| electrical | Electrical | main_volts, batt_amps, rpm | 3 |

`overview` matches today's `DEFAULT_ACTIVE_CHANNELS`. It is the first-run default and the fallback.

### 6.5 Chart state

The chart is always in exactly one of three states. The preset bar shows which.

| State | Entered by | Preset bar shows |
|---|---|---|
| **Preset** | Tapping a preset | That preset highlighted |
| **Modified** | Adding or removing a channel while in a preset | "Cylinders (modified)" with **Revert** and **Save as preset…** |
| **Insight** | Clicking insight evidence (§10) | "Showing: <insight title>" with **Back to <previous>** |

Rules:
- **Across flights (D7).** Moving to another flight keeps the current state exactly, whether a preset or a Modified set. Insight is the exception: moving to another flight leaves Insight and restores the state before it, because an insight belongs to one flight.
- **On opening the Flight view.** Select `AppSettings.flight_chart.last_preset_id`. Only the preset is persisted, never a Modified set, so a one-off tweak doesn't carry into the next session. If the stored id no longer exists (a deleted user preset) or fails validation, fall back to `overview`.
- **Leaving Insight** restores the exact prior state, including a Modified set.
- `last_preset_id` is written whenever the user taps a preset. Entering Modified or Insight doesn't change it.

### 6.6 Managing user presets

Managing presets happens in Settings, not on the Flight view. It covers the list of user presets, rename, reorder, delete, and duplicating a shipped preset. Creation happens on the Flight view through "Save as preset…", which asks only for a name. Sharing a preset with others is out of scope (§14); the JSON shape is deliberately small so export and import stay easy later.

## 7. Slot cap

- 6 slots, counting `egt_cyl` once.
- When the chart is full, the picker disables the entries that aren't active, with the note "Chart is full — remove a channel to add another". Active entries stay tappable so they can be removed.
- The cap is enforced in three places from `MAX_CHART_SLOTS`: the picker, preset validation (§6.3), and the Insight state. For Insight, if subject plus companions exceed 6 slots, the subject channels are kept first, then companions in declared order, and a note says some were left out.
- The cap is exposed to the UI through `get_channel_registry`. It isn't a user setting.

### 7.1 Group vs. individual cylinders

- The group (`egt_cyl`) and its members are mutually exclusive on the chart.
- Adding an individual cylinder while the group is active replaces the group with that cylinder. Adding the group while one or more individual cylinders are active replaces them with the group. Neither case needs a confirmation. A swap within the EGT set frees or uses at most as many slots as it removes, except group → individual, which is slot-neutral.
- Several individual cylinders can be active at once (for example EGT3 and EGT4), each taking one slot.
- In the Insight state, an EGT exceedance on `egt4_f` shows `egt4_f` alone plus its companions, not the group.

## 8. Picker

- The chip row shows only active channels and doubles as the legend (Spec 05 §4 is unchanged in spirit). Each chip has a remove ✕. A final **+ Add channel** chip opens the picker.
- The picker opens as a popover on desktop and a bottom sheet on iPad. It contains a search field (matching label, description and id) followed by sections in registry `group` order. Each row shows the label, unit, description, and its state: active, available, unavailable (§5), or disabled because the chart is full (§7).
- The EGT section lists "Cylinder EGTs (1–4)" first, then EGT1–EGT4, then spread, max, min and mean. A row that would swap out the current group or cylinders says so ("replaces Cylinder EGTs").
- The preset bar sits above the chip row as a single horizontally scrollable row of preset buttons, with shipped presets first, then user presets.

## 9. Colors

- The 8 current channels keep their fixed tokens in `theme/colors.ts`, so users learn them.
- Other channels are assigned a color from a **6-color slot palette** when activated. The first free slot color is used and released on removal, and a channel keeps its color for as long as it stays active.
- Cylinders 1–4 use one hue family in four lightness steps, ordered 1→4. An individual cylinder always uses its own step from that family, whether shown alone or as part of the group, so EGT4 looks the same everywhere.
- The slot palette must not collide with the phase palette or the severity palette (Spec 03 §5.2). It should also be checked in both light and dark themes.

## 10. Insight-driven channels

- Clicking `series_window` evidence enters the Insight state (§6.5). The chart shows the evidence `channels` (the subject) plus each subject channel's registry `companions`, de-duplicated and capped (§7). It also zooms to the evidence window and highlights it, as it does today.
- The UI resolves companions from the registry. The evidence contract doesn't change, and insights carry no display hints.
- If evidence carries no channels, the click zooms and highlights only, and the chart state doesn't change.
- **Future extension (not v0.2):** a topic-level view hint that overrides companions where context depends on the situation, for example oil temp on the ground wanting OAT but in climb wanting vertical speed.

## 11. Series fetching and downsampling

### 11.1 Lazy fetch

- On flight open, fetch the current state's channels only.
- On add, fetch only the missing channels, and cache them per flight for the life of the view. A preset switch fetches whatever isn't already in the cache.
- `op_get_flight_series` requires an explicit `channels` list, and a slot-group id expands to its members on the server. The hard-coded defaults in `server.py` are removed (finding 3).

### 11.2 Downsampling (prerequisite, D9)

Tracked and implemented separately. This spec relies on these properties of the fixed downsampler:
- Each channel has its own min/max envelope over fixed time buckets, so peaks are preserved per channel (Spec 01 §8.7).
- Bucket edges depend only on the flight's length, so channels fetched at different times align.
- NaN rows are excluded from the envelope.
- The cursor readout finds the nearest point in each active series, instead of relying on shared x values.

## 12. Contract and API changes (summary)

| Area | Change |
|---|---|
| `channels.py` | Add `label`, `group`, `chartable`, `slot_group`, `companions`, `unit_variant_of`; retire `charted_by_default`; add `SLOT_GROUPS` and `MAX_CHART_SLOTS` |
| New op | `get_channel_registry` → chartable channels (with companions), slot groups, max slots |
| New ops | `get_chart_presets` (shipped + user, with validation diagnostics), `save_user_preset`, `delete_user_preset`, `reorder_user_presets` |
| `FlightAnalysis` | Add `available_channels` |
| `AppSettings` | Add `chart_presets` and `flight_chart.last_preset_id` |
| Diagnostics | Add `PRESET_INVALID` |
| `server.py` | Remove default channel lists; expand slot-group ids in `get_flight_series` |
| New file | `chart_presets.json` (shipped presets) |
| UI | `channels.ts` keeps colors only; new `PresetBar`; `ChannelPicker` becomes an active-chip row plus picker panel; chart state per §6.5 held above the flight route so it survives moving between flights; Settings gains preset management |
| JSON Schemas | Regenerate `contract/schema` for the changed types |
| Not changed | Insight evidence shape; `insight_rules.json` |

## 13. Testing against the project logs

All tests run against `log_20260423_200615_KACV.csv`:

1. **Registry.** Every chartable channel is present and not entirely NaN. `available_channels` equals the 36 chartable ids. Every `companions` entry is a chartable id, and no channel lists itself.
2. **Presets.** Every shipped preset validates and resolves to at most 6 slots and to available channels only.
3. **Validation.** Unknown id, non-chartable id, 7 slots, group plus member, empty and duplicate cases are each rejected with `PRESET_INVALID`. `egt_cyl` plus 5 other slots is accepted. So are 4 individual cylinders plus 2 others.
4. **Slot-group expansion.** A `get_flight_series` call for `["egt_cyl"]` returns `egt1_f`–`egt4_f`.
5. **Evidence and companions.** A KACV limit-exceedance insight resolves to its subject channel plus its companions, capped at 6. For MAP that is exactly `map_inhg, rpm, power_pct`.
6. **Last-preset fallback.** A stored `last_preset_id` that names a deleted user preset resolves to `overview`.
7. **Lazy fetch.** Fetching {rpm} and then {map_inhg} yields the same bucket edges as fetching both in one call. This depends on §11.2.

UI checks run on macOS Chrome, macOS Safari and iPad:
- The picker opens as a popover on desktop and a sheet on iPad.
- A full chart disables adding.
- Group ↔ individual cylinder swaps behave per §7.1, and colors stay consistent.
- Chart state carries across flights. Insight → Back restores a Modified state. Moving to another flight while in Insight restores the prior state.
- Reopening the app selects the last-used preset, never a Modified set.
- Slot colors remain distinct from phase bands in both themes.

## 14. Out of scope

- Sharing presets with other users or the community. The small JSON shape keeps this possible later.
- Per-workspace default presets. This could be added later as an optional workspace setting without breaking anything.
- Per-topic overrides of companions (§10).
- Multiple charts or split panes on the Flight view.
- Choosing unit variants from `AppSettings.units`. `unit_variant_of` prepares for it.
- Charting a map or GPS track.
- Research mode (the reserved Spec 06).

## 15. Resolved questions

| # | Question | Decision |
|---|---|---|
| Q1 | User presets: app-level or workspace-level? | **App-level.** One set of presets for all flights and workspaces (D6). |
| Q2 | Which preset does the Flight view open on? | **Last-used preset**, falling back to Overview. Only the preset is persisted, not a Modified set. Chart state carries across flights (D7). |
| Q3 | Individual cylinder EGTs as well as the group? | **Yes.** The group and individuals are mutually exclusive, and colors come from one hue family (§7.1, §9). |
| Q4 | Where do insight context channels live? | **Registry `companions`** per channel. Per-topic overrides are a future extension (D8, §10). |
| Q5 | Downsampling fix before or with this spec? | **Before, as a separate change** (D9). It is being implemented separately. |
