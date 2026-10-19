# Spec 15 — Branding & Visual Identity

**Status:** Draft v0.3 — for review (no code written)
**Depends on:** Spec 13 (Documentation System — §11 Q1 hosting), Spec 03 (§5.7 Settings/gear icon placement)
**Scope:** SlingologyEIS's place in the Slingology app family — shared identity elements, this app's color, and how both the web UI and the docs website apply them.

---

## 1. Family identity (shared across every Slingology app, not ours to change)

- One icon — a low-wing aircraft silhouette, two-tone fill, circular field, small motion-trail flourish — reused as-is across every app. Never redrawn or re-posed per app.
- One wordmark lockup — **SLINGOLOGY** (bold) with the individual app name (e.g. **XC**, **EIS**) smaller underneath. The family name carries the weight; the app name is the only thing that changes in the type.
- One saturation level — every sibling app's color is muted/desaturated, not a vivid "app icon" hue. This is what makes the family read as one thing: brand color differs by hue, not by intensity.

This app's job is only to supply its hue. Icon artwork, layout, and desaturation level are fixed by the family and are not EIS's to adjust.

## 2. EIS's color

**`#3D5A73`** (muted slate-blue) — chosen over a bronze/copper alternative because it has no collision risk against EIS's own functional color systems (§3), where bronze sits close to the existing `ENGINE_START`/`WARMUP` phase browns. Slate-blue also fits the app's subject: an instrument/avionics information system.

**Checked against the nearest phase color:** `#3D5A73` sits closest to the existing `TAKEOFF_ROLL` phase color (`#6366F1`, indigo) of anything in the phase palette. Compared side by side, they read as distinct — indigo pulls toward violet, the brand color is colder and darker. Settled, no change needed.

## 3. Why this needs its own rule, not just a hue pick

EIS's UI already has two saturated color systems doing real work — severity (red/amber/yellow) and 11 phase colors spanning most of the wheel. A brand color chosen just to avoid today's exact hues is fragile, since the palette is packed enough that most hues collide with something. The real guarantee is **saturation, not hue**: every functional color in this app is vivid; the brand color is muted. That difference is what keeps a user from ever reading the brand accent as a signal (a phase or a severity), regardless of which hue either system uses next.

**Standing rule:** the brand accent is reserved out of both the severity and phase palettes permanently. Any future phase or severity color must avoid `#3D5A73` and stay at the saturated end of its own system — it should never be muted down to brand-accent territory, and the brand accent should never be chosen at phase/severity saturation.

## 4. Where it's used in the app

The brand color is the **one accent**, applied consistently wherever the UI needs a single "this is active / this is the primary action" color — not a palette of its own:

- Active nav tab
- Primary buttons / CTAs
- Zoom controls
- Synced cursor marker on charts
- Minimap's current-view outline

This replaces today's placeholder teal (`accent: "#4fc3b0"` in `theme/colors.ts`) one-for-one. No other screen element should pick up the brand color — it's reserved for these "this is the live, active thing" roles, the same way it's reserved from severity and phase.

**One existing use needs its own decision, not a one-for-one swap:** `colors.ts` also has `chartRpm: "#4fc3b0"` — the same placeholder teal, but used as a chart series color, not a UI accent. Pulling the RPM series along with the brand-color rename would make a data series carry brand meaning, which is exactly what §3's reservation rule is for. My recommendation: give `chartRpm` its own color, independent of whatever the brand accent becomes, rather than let it keep riding along with it by coincidence of having shared a hex value.

## 5. Instructions for Code

- Add the brand color as its own named token in `theme/colors.ts` (e.g. `brand.accent`), separate from the `severity` and `phase` token groups already there — not folded into either.
- Swap `accent` to the new token. Give `chartRpm` its own independent value rather than carrying it along (§4).
- **Replace `web/public/favicon.svg`** — it's currently a generic framework-default icon, not ours. This is a replacement, not an addition alongside it.
- Functional outcome to preserve: a reader should never be able to mistake the brand accent for a severity or phase signal. How that's enforced in code (lint rule, a comment, naming convention) is Code's call.

## 6. Docs button in the top bar

A new top-bar icon, placed next to Settings, linking out to the docs site (`https://alchemygeek.github.io/Rotax9iSEIS/`).

- **Icon color:** the default secondary/muted icon color — the same as Settings — not the brand accent. The brand color (§4) means "this is the active, live thing in the app"; a static link to an external site isn't that, and giving it the brand color would blur the one rule §3/§4 depend on.
- **Opens in a new tab.** Every other nav icon stays inside the app; this one leaves it, and should look and behave like it does.
- **Icon choice:** a book/docs glyph (distinct from the Settings gear), consistent with the icon set already in `public/icons.svg`.
- **Open item:** confirm `https://alchemygeek.github.io/Rotax9iSEIS/` is the permanent docs URL before it's hardcoded — there's no redirect layer here to absorb a future move.

## 7. For the docs website

Same token, same rule, applied to a different surface:

- Header lockup: icon + "SLINGOLOGY EIS" wordmark, same layout convention as the app (and as sibling apps' sites).
- Primary links / buttons / any "active" indicator on the site use the same `#3D5A73`, for the same reason it's the one accent in the app — one brand color, one meaning, wherever it appears.
- Favicon: the shared icon, recolored to this app's hue, transparent background — same asset logic as the in-app icon, exported at favicon sizes (16/32/180/512px; final logo files in hand, icon cropped tight from the wordmark).
- The site has no severity/phase systems of its own, so §3's reservation rule doesn't carry over — the accent is free to use more broadly on the site than it is in the app.
- **Resolves Spec 13 §11 Q1 (hosting):** that question weighed same-host `/docs/` against a separate `docs.` subdomain. The actual URL, `alchemygeek.github.io/Rotax9iSEIS`, is neither — it's GitHub's own Pages domain. Spec 13 should be updated to mark Q1 resolved, pointing here.

## 8. Outstanding before this is final

1. Confirm the docs URL is permanent (§6).
2. Decide `chartRpm`'s new color (§4).
3. Final logo files at favicon sizes (§7) — in hand as of this session; see delivered favicon-16/32/180/512.png.
4. Update Spec 13 §11 Q1 to reference this spec's resolution (§7).

## Changelog

| Version | Change |
|---|---|
| 0.1 | Initial draft — color decision, reservation rule, and application points for app + docs site, carried over from the branding discussion. |
| 0.2 | §2: phase-legend check done — `#3D5A73` confirmed distinct from `TAKEOFF_ROLL` indigo, no longer an open item. Added §6: Docs button next to Settings in the top bar, muted icon color (not brand accent, per §3/§4's reservation rule), opens in a new tab, links to the GitHub Pages docs site. |
| 0.3 | Renumbered 07 → 15 after checking the real repo: 07–14 are already in use (01–05, 07–10, 12–14; 06 and 11 are reserved, not free). Added the `chartRpm` token finding (§4/§5 — a second, previously-missed use of the placeholder teal, this one a chart series rather than a UI accent). Added the existing `web/public/favicon.svg` replacement note (§5 — it's a generic framework default, not ours). Added the Spec 13 §11 Q1 cross-reference (§7) — the real docs URL resolves that spec's open hosting question. |
