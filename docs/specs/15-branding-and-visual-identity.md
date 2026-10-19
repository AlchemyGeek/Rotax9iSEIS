# Spec 15 — Branding & Visual Identity

**Status:** v0.5 — the family mark and lockup in the app's top bar; v0.4 — use classification approved, light tint for lines and text, `TAXI` recoloured, docs URL confirmed (2026-10-19)
**Depends on:** Spec 13 (Documentation System — §11 Q1 hosting), Spec 03 (§4 nav, §5.2 phase palette, §5.7 Settings/gear icon placement)
**Scope:** SlingologyEIS's place in the Slingology app family — shared identity elements, this app's color, and how both the web UI and the docs website apply them.

---

## 1. Family identity (shared across every Slingology app, not ours to change)

- One icon — a low-wing aircraft silhouette, two-tone fill, circular field, small motion-trail flourish — reused as-is across every app. Never redrawn or re-posed per app.
- One wordmark lockup — **SLINGOLOGY** (bold) with the individual app name (e.g. **XC**, **EIS**) smaller underneath. The family name carries the weight; the app name is the only thing that changes in the type.
- One saturation level — every sibling app's color is muted/desaturated, not a vivid "app icon" hue. This is what makes the family read as one thing: brand color differs by hue, not by intensity.

This app's job is only to supply its hue. Icon artwork, layout, and desaturation level are fixed by the family and are not EIS's to adjust.

## 2. EIS's color

**`#3D5A73`** (muted slate-blue) — chosen over a bronze/copper alternative because it has no collision risk against EIS's own functional color systems (§3), where bronze sits close to the existing `ENGINE_START`/`WARMUP` phase browns. Slate-blue also fits the app's subject: an instrument/avionics information system.

**Checked against the phase and severity palettes (v0.4, measured).** The nearest *chromatic* functional color was not `TAKEOFF_ROLL` (ΔE 69, CIELAB) but `TAXI` (`#5B7290`, ΔE 11 — the same muted slate-blue family, hue 214° vs 208°). `TAXI` is therefore recoloured to `#84CC16` (lime, ΔE 106; Spec 03 v0.26 §5.2), the one free saturated hue between the ground browns and `TAKEOFF_ROLL` indigo, which it sits next to in time. The other near colors are neutral greys — `PRE_START` `#4B5563` (ΔE 9), `severity info` `#64748B` (ΔE 12), `SHUTDOWN` `#374151` (ΔE 12) — kept as they are and separated by role (§3).

**Light tint for lines and text.** On the app's dark theme `#3D5A73` has 2.6:1 contrast against the page and 2.4:1 against a panel — below WCAG's 3:1 for UI graphics and 4.5:1 for text. It is used only as a **fill under light text** (`#e8eaed` on it: 6.0:1). Wherever the brand must be a line, an outline or text on dark, the app uses the **brand tint `#7FA3C2`** — the same hue (208°), lighter (7.1:1 on the page, 6.5:1 on a panel). The two are one brand color at two lightnesses, not two colors.

## 3. Why this needs its own rule, not just a hue pick

EIS's UI already has two saturated color systems doing real work — severity (red/amber/yellow) and 11 phase colors spanning most of the wheel. A brand color chosen just to avoid today's exact hues is fragile, since the palette is packed enough that most hues collide with something. The real guarantee is **saturation, not hue**: every chromatic functional color in this app is vivid; the brand color is muted. That difference is what keeps a user from ever reading the brand accent as a signal (a phase or a severity), regardless of which hue either system uses next.

**Standing rule:** the brand accent is reserved out of both the severity and phase palettes permanently. Any future phase or severity color must avoid `#3D5A73` and stay at the saturated end of its own system — it should never be muted down to brand-accent territory, and the brand accent should never be chosen at phase/severity saturation.

**Greys are the exception, separated by role (v0.4).** The palettes also hold neutral greys (`PRE_START`, `SHUTDOWN`, `UNKNOWN`, `severity info`) that are near the brand in lightness. They carry no hue to confuse with, and they never share a role with the brand: greys appear only as phase bands and severity dots/labels, the brand never does.

**Enforced by a test (v0.4).** `web/src/theme/brand.test.ts` measures CIELAB ΔE between each brand value (`#3D5A73`, `#7FA3C2`) and every phase and severity color: a chromatic color (HSL saturation ≥ 20%) must be at least ΔE 20 away, a grey at least ΔE 8; the brand itself must stay muted (saturation 20–45%). A second check fails on any hard-coded copy of an accent color outside the token files.

## 4. Where it's used in the app

The brand color is the **one accent**, applied consistently wherever the UI needs a single "this is active / this is the primary action" color — not a palette of its own:

- Active nav tab
- Primary buttons / CTAs
- Synced cursor marker on charts
- Minimap's current-view outline
- *(v0.4)* Other selected tabs, chips and segmented controls — the same "this is the active one" meaning as the nav tab
- *(v0.4)* "Live right now" states — a running progress bar, a drag-over drop target, the Journal entry just jumped to, a prompt waiting for an answer

*Zoom controls* (v0.1–0.3) is dropped: the charts zoom by drag and wheel, with no zoom buttons to color.

This replaces today's placeholder teal (`accent: "#4fc3b0"` in `theme/colors.ts`). No other screen element picks up the brand color — it's reserved for these "this is the live, active thing" roles, the same way it's reserved from severity and phase.

**Every other former use of the placeholder teal (v0.4).** The teal was used about 80 times, well beyond the roles above. Each use moves to a token of its own:

| Former use | Examples | Now |
|---|---|---|
| Active nav tab, selected tabs/chips/segmented controls | nav, Settings and Journal tabs, Flights group-by, active preset, filter and phase chips, active picker/table row | **Brand**: tint text on a 15% brand fill |
| Primary buttons | Apply, Save, Sync, Import, Include… | **Brand** fill, **light** text (previously dark text, which would be 2.6:1) |
| Synced cursor, minimap view outline, "live" outlines and progress | chart cursor, minimap window, drag-over, jumped-to entry, prompt banner, engine-loading bar | **Brand tint** |
| Text links and inline actions | every `<a>`, *Edit rules…*, *Revert*, *Show all phases*, help toggles | **Link** token: light neutral text, underlined — no brand color |
| Status meaning "fine / done / added" | ✓ marks, STABLE, VERIFIED, *added* in rule diffs, *Needs analysis*, a note present, the current workspace | **OK** token: keeps the former teal `#4fc3b0`, now meaning only this |
| Chart data roles | the highlighted flight and an active event marker; the reference line/border/label, Filter-health's flight points and the recent-window fill | Chart tokens: **highlight** (white) for the first two; **chart data** (the former teal `#4fc3b0`, as its own token) for the rest, so Trends reads as before — a data series never carries brand meaning (§3) |
| Decoration | idle drop-zone border, icon circles, notice tints | **Neutral** border and panel tones |

**`chartRpm`** — the RPM series on the flight chart — shared the placeholder teal by coincidence, not meaning. It keeps `#4fc3b0` as its own token, independent of the brand, so the RPM line looks as it always has and never reads as the brand.

**Top bar (v0.5).** The app's top bar opens with the family mark (the icon alone, cropped from the delivered logo) and the §1 lockup — **SLINGOLOGY** bold, **EIS** smaller underneath — in place of the plain *SlingologyEIS* text. The mark keeps its own artwork colors; it is identity, not one of the accent roles above.

## 5. Instructions for Code

- Add the brand color as its own named token group in `theme/colors.ts` (`brand.accent`, `brand.tint`, `brand.fill15`) and in `index.css`, separate from the `severity` and `phase` token groups — not folded into either.
- Swap `accent` to the new tokens per §4's table; add the link, OK, chart highlight and chart data tokens; replace every hard-coded copy of the teal with a token. Give `chartRpm` its own value (§4).
- **Replace `web/public/favicon.svg`** — it's currently a generic framework-default icon, not ours. This is a replacement, not an addition alongside it.
- Functional outcome to preserve: a reader should never be able to mistake the brand accent for a severity or phase signal. Enforced by the test in §3.

## 6. Docs button in the top bar

A new top-bar icon, placed next to Settings, linking out to the docs site (`https://alchemygeek.github.io/Rotax9iSEIS/` — confirmed permanent, v0.4).

- **Icon color:** the default secondary/muted icon color — the same as Settings — not the brand accent. The brand color (§4) means "this is the active, live thing in the app"; a static link to an external site isn't that, and giving it the brand color would blur the one rule §3/§4 depend on.
- **Opens in a new tab.** Every other nav icon stays inside the app; this one leaves it, and should look and behave like it does.
- **Icon choice:** a book/docs glyph (distinct from the Settings gear), consistent with the icon set already in `public/icons.svg`.

## 7. For the docs website

Same token, same rule, applied to a different surface:

- Header lockup: icon + "SLINGOLOGY EIS" wordmark, same layout convention as the app (and as sibling apps' sites).
- Primary links / buttons / any "active" indicator on the site use the same `#3D5A73`, for the same reason it's the one accent in the app — one brand color, one meaning, wherever it appears. On the site's light scheme `#3D5A73` reads well (7:1 on white); its dark scheme uses a lighter tint for links, as the app does.
- Favicon: the shared icon, recolored to this app's hue, transparent background — same asset logic as the in-app icon, exported at favicon sizes (16/32/180/512px; final logo files in hand, icon cropped tight from the wordmark).
- The site has no severity/phase systems of its own, so §3's reservation rule doesn't carry over — the accent is free to use more broadly on the site than it is in the app.
- **Resolves Spec 13 §11 Q1 (hosting):** that question weighed same-host `/docs/` against a separate `docs.` subdomain. The actual URL, `alchemygeek.github.io/Rotax9iSEIS`, is neither — it's GitHub's own Pages domain. Spec 13 v0.2 marks Q1 resolved, pointing here.

## 8. Outstanding before this is final

None (v0.4): the docs URL is confirmed (§6), `chartRpm` keeps its teal (§4), the favicons are in hand (§7), and Spec 13 §11 Q1 is marked resolved (§7).

## Changelog

| Version | Change |
|---|---|
| 0.1 | Initial draft — color decision, reservation rule, and application points for app + docs site, carried over from the branding discussion. |
| 0.2 | §2: phase-legend check done — `#3D5A73` confirmed distinct from `TAKEOFF_ROLL` indigo, no longer an open item. Added §6: Docs button next to Settings in the top bar, muted icon color (not brand accent, per §3/§4's reservation rule), opens in a new tab, links to the GitHub Pages docs site. |
| 0.3 | Renumbered 07 → 15 after checking the real repo: 07–14 are already in use (01–05, 07–10, 12–14; 06 and 11 are reserved, not free). Added the `chartRpm` token finding (§4/§5 — a second, previously-missed use of the placeholder teal, this one a chart series rather than a UI accent). Added the existing `web/public/favicon.svg` replacement note (§5 — it's a generic framework default, not ours). Added the Spec 13 §11 Q1 cross-reference (§7) — the real docs URL resolves that spec's open hosting question. |
| 0.4 | From the implementation review (2026-10-19). §2: measured distances — the nearest chromatic color was `TAXI`, not `TAKEOFF_ROLL`, so `TAXI` becomes `#84CC16` (Spec 03 v0.26); a light tint `#7FA3C2` of the same hue for lines and text, since `#3D5A73` is 2.4–2.6:1 on the dark theme; primary buttons take light text. §3: greys are separated by role; the rule is enforced by a ΔE test. §4: roles widened to selected tabs/chips/segmented controls and "live" states; *zoom controls* dropped (none exist); every other former teal use classified (link, OK, chart highlight/data, neutral); `chartRpm` keeps `#4fc3b0`. §6: URL confirmed. §8: nothing outstanding. |
| 0.5 | §4: the family mark and §1 lockup open the app's top bar, replacing the plain *SlingologyEIS* text (2026-10-19). |
