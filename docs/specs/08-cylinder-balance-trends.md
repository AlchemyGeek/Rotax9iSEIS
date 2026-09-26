# Spec 08 — Cylinder Balance Trends (Mini-Spec)

**Project:** SlingologyEIS
**Status:** Draft v0.1 — mini-spec, not yet implemented
**Suggested repo path:** `docs/specs/08-cylinder-balance-trends.md`
**Builds on:** Spec 01 (engine contract, metric registry, insight rules), Spec 03 (Trends view), Spec 05 (frontend bootstrap)
**Revision history**

| Version | Change |
|---|---|
| 0.1 | Initial mini-spec. |

**Note on numbering:** This document is numbered 08. Number 06 stays reserved for the tabled "research mode" feature noted in Spec 05.

---

## 1. Problem

The toolkit assumes cylinder 4 is the hottest cylinder. `egt.py` computes `egt4_elevation_f` (EGT4 minus the mean of EGT1–3) and labels a positive value as "typical for 916iS — turbo exhaust proximity". That assumption is not universal:

- **Engine model.** The cyl-4 explanation is turbo exhaust routing (914/915/916). The naturally aspirated 912iS has no reason to favour cylinder 4.
- **Installation.** Cowling, inlet ducting, baffling, radiator/oil-cooler placement and tractor vs. pusher layout all change which cylinder gets the least cooling air.
- **Individual engine.** Injector flow tolerances and intake distribution shift individual EGTs by tens of °F.
- **Instrumentation.** Probe insertion distance and probe tolerance offset readings independently of combustion.

Meanwhile, a change in which cylinder runs hottest — or one cylinder drifting away from the others — is exactly the early signal for injector clogging/wear (lean, hotter), ignition/plug degradation (cooler), or a failing probe (drift/noise). Today that signal isn't tracked across flights: the `cylinder_rank` insight rule exists in `insight_rules.json` but is not wired (`operations.py`, "Known gap"), and only a boolean `egt_rank_stable` reaches the metric registry.

## 2. Goals

1. Remove the hardcoded "cylinder 4 is hottest" assumption; learn the usual hottest cylinder per aircraft, with an engine-profile default as a prior.
2. Track per-cylinder EGT balance as trendable, baselined metrics.
3. Flag when the hottest cylinder changes away from the aircraft's established pattern.
4. Show all of this in the Trends view under the EGT group.

**Non-goals:** CHT/coolant per-cylinder analysis; diagnosing root cause (injector vs. ignition vs. probe) automatically — the insight text suggests possibilities, the pilot/mechanic decides; changing limit checks.

## 3. Engine profile

Add one optional field to each `engines/*.json`:

```json
"expected_hot_cylinder": 4
```

| Profile | Value | Rationale |
|---|---|---|
| 916iS | `4` | Observed on N117ZS (37 flights); turbo exhaust proximity |
| 915iS | `4` | Same turbo layout family — confirm against fleet data |
| 914iS | `null` | Unverified placeholder |
| 912iS | `null` | No turbo; no expected pattern |

`null` means "no prior — learn from data only". The value is a display/interpretation hint, never a limit.

## 4. Per-flight metrics (engine)

Computed in `egt.egt_health()` over cruise-quality rows only (same filtering as today). For each available cylinder *n* (1–4):

| Metric id | Unit | Definition |
|---|---|---|
| `egt{n}_deviation_f` | °F | mean EGT*n* − mean of the *other* available cylinders |
| `egt_hottest_cyl` | — (int 1–4) | cylinder with the highest cruise-mean EGT |
| `egt_hottest_margin_f` | °F | cruise-mean EGT of hottest − second hottest |
| `egt_rank_order` | — (list[int]) | cylinders sorted hottest → coldest by cruise mean |

Register the numeric ones in `registry.py` (`egt` group, phase `CRUISE`). `egt_rank_order` must also be carried on `FlightAnalysis` so `cylinder_rank` can be wired (closes the Known gap in `operations.py`).

**Fix while here:** `rank_stable` is currently `len(idxmax().mode()) == 1`, which tests whether the *mode is unique*, not whether one cylinder dominated. Redefine as: the modal hottest cylinder was hottest in ≥ 80 % of cruise samples.

**Compatibility:** `egt4_elevation_f` equals `egt4_deviation_f`. Keep `egt4_elevation_f` (and the `egt4_elevation` topic) as a deprecated alias for one minor version so existing bundles, baselines and fixtures still load; drop its Trends entry in favour of the new chart.

## 5. Fleet baselines & learned hot cylinder

- Add `egt1_deviation` … `egt4_deviation` to `BASELINE_METRIC_DEFS` in `baselines.py`, stratified by `oat_band` like the other EGT metrics.
- Add a fleet-level derived value **`established_hot_cyl`**: the modal `egt_hottest_cyl` across baseline flights, counting only flights with `egt_hottest_margin_f ≥ MARGIN_MIN_F`. Established only when that cylinder wins ≥ 70 % of those flights and n ≥ 10; otherwise fall back to the engine profile's `expected_hot_cylinder` (confidence: "prior"), or "none".
- Surface in `FleetAnalysis` together with its confidence and share (e.g. `{cyl: 4, share: 0.92, n: 34, source: "learned"}`).

## 6. Insights

Wire the existing `cylinder_rank` rule with a clarified condition, and add standard triggers to the new deviation metrics.

```json
"cylinder_rank": {
  "enabled": true,
  "triggers": [
    { "type": "threshold", "condition": "hot_cyl_changed",
      "margin_min_f": 15, "consecutive_flights": 2, "severity": "warning" }
  ]
},
"egt_cyl_deviation": {
  "enabled": true,
  "applies_to": ["egt1_deviation", "egt2_deviation", "egt3_deviation", "egt4_deviation"],
  "triggers": [
    { "type": "baseline_deviation", "n_min": 10, "severity": "watch" },
    { "type": "trend", "direction": "either", "r2_min": 0.5, "n_min": 10, "severity": "watch" }
  ]
}
```

- **`hot_cyl_changed`** fires when `egt_hottest_cyl ≠ established_hot_cyl` **and** `egt_hottest_margin_f ≥ margin_min_f` on this flight and the preceding `consecutive_flights − 1` flights. The margin guard suppresses flip-flopping between two near-equal cylinders; the consecutive guard suppresses one-off flights (unusual OAT, power setting).
- Does not fire while `established_hot_cyl` has source "none"; if source is "prior", severity downgrades to `info` ("differs from the typical 916iS pattern", not an anomaly).
- Insight text names the direction and plausible causes, e.g. *"Cylinder 2 ran hottest (+22 °F over cyl 4) for 2 flights; this aircraft's usual hottest is cyl 4. A cylinder rising is consistent with a lean injector; the previous hottest falling can indicate ignition/plug issues or a probe fault."*
- The per-cylinder deviation triggers catch gradual drift before the ranking actually flips.

**New rule-engine features required** (neither exists today): `applies_to` (one rule block shared by several metric ids) and `"direction": "either"` for `trend` triggers (`topics.trend_triggered` currently matches only `increasing`/`decreasing` exactly). The alternative is four copies of the rule and two trend triggers each; `applies_to` is preferred so the rule playground edits all four cylinders at once.

## 7. Trends view (web)

EGT group in `web/src/views/Trends.tsx` becomes:

```ts
{ label: "EGT", metrics: ["egt_spread", "cylinder_balance"] }
```

`cylinder_balance` is a composite chart (not a single-metric scatter):

1. **Main panel** — four series, `egt1_deviation` … `egt4_deviation` vs. date/engine hours, one colour per cylinder, zero line emphasised. Baseline band (mean ± σ) for the selected cylinder on hover/select. Healthy engine: four roughly flat, parallel lines.
2. **Hot-cylinder strip** — a thin categorical row under the main panel, one mark per flight coloured by `egt_hottest_cyl` (same cylinder colours), hollow when `egt_hottest_margin_f < MARGIN_MIN_F` (ambiguous). Changes of hottest cylinder are visible at a glance.
3. **Header chip** — "Usual hottest: Cyl 4 (92 %, 34 flights, learned)" or "(prior: 916iS profile)".
4. Flights that triggered `hot_cyl_changed` are marked on both panels; clicking navigates to the Flight view (existing `?flight=` behaviour).

The Flight view's EGT topic card replaces the "Cyl 4 runs +N °F over 1–3" line with "Hottest: Cyl *n* (+M °F over next)", and notes when *n* differs from the established cylinder.

## 8. Contract / fixtures

- Spec 01 types: add the §4 metrics to the registry listing, `established_hot_cyl` to `FleetAnalysis`, `rank_order` to `FlightAnalysis.metrics` (list-valued metric).
- Regenerate `web/src/fixtures/*` and update `web/src/types/contract.ts`.
- Mirror rule changes into `web/src/fixtures/insight-rules.json`.

## 9. Constants

| Name | Default | Where |
|---|---|---|
| `MARGIN_MIN_F` | 15 °F | `egt.py` (overridable per rule via `margin_min_f`) |
| Established share | 70 % | `baselines.py` |
| Established n_min | 10 flights | `baselines.py` |
| Rank-stable share | 80 % of cruise samples | `egt.py` |

These are initial guesses; tune against the N117ZS dataset and record the result here.

## 10. Acceptance

1. With the 916iS profile and the N117ZS logs, `established_hot_cyl` resolves to 4 (source "learned") and `egt4_deviation` baselines match the existing `egt4_elevation` baselines within rounding.
2. A synthetic fleet where cylinder 2 is hottest learns cyl 2 and raises no `hot_cyl_changed` insight, even on the 916iS profile.
3. A synthetic fleet that switches from cyl 4 to cyl 2 by ≥ 20 °F for two consecutive flights raises exactly one `hot_cyl_changed` warning; a single-flight switch, or a switch with < 15 °F margin, raises none.
4. A 912iS workspace with no learned pattern produces no `hot_cyl_changed` insight and shows "Usual hottest: not yet established".
5. Existing bundles containing only `egt4_elevation_f` still load and render.
6. Trends → EGT → cylinder balance renders the four-line panel, the hot-cylinder strip and the header chip from fixtures.
