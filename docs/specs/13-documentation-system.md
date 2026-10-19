# Spec 13 — Documentation System

**Status:** Draft v0.2, 2026-10-19 — §11 Q1 (hosting) resolved by Spec 15 §7. v0.1, 2026-10-06: design only; no code written.
**Audience:** two readers — the *pilot* (non-technical, wants to get a result quickly) and the *researcher* (wants to understand and challenge how the analytics work). A third, the *contributor*, is served by the existing specs and is only linked, not written for here.
**Depends on:** Spec 02 (results bundle — for the demo workspace), Spec 10 (topic register — drives generated reference pages), Spec 12 (Trends — the UI the pictorial tier documents). Should be written against the UI as it stands after Session B.

---

## 1. Goals

1. A pilot can install, create a workspace and read their first report in under ten minutes, following pictures.
2. A researcher can find, for any number the app shows, the page that says how it was computed, what it is compared against, and where the OM limit comes from.
3. Every page is keyword-searchable in the browser.
4. The whole corpus can be handed to an AI assistant (Claude, ChatGPT, NotebookLM) in one file so users can ask questions in their own words.
5. The parts of the documentation that describe the engine (topics, limits, settings) cannot drift from the code — they are generated from it.
6. One source of truth: the same concept text appears in the docs site and in the app's contextual help.

## 2. Non-goals (v1)

- An "Ask" chatbot embedded in the app. Needs an API key and a server path, which conflicts with the logs-never-leave-the-device promise. Revisit once the content is stable (§10).
- Translations.
- Documenting the legacy notebooks beyond a one-page "where they went".
- Video.

## 3. Structure — four kinds of page

Follows the Diátaxis split. Each page declares its kind in front matter and is written to that kind's rules; this is what keeps the quick start from turning into a design document.

| Kind | Reader | Shape | Rule |
|---|---|---|---|
| **Start** (tutorial) | pilot | one guided path, screenshots every step | exactly one tutorial; no options, no theory, no links out mid-flow |
| **Guides** (how-to) | pilot | one task per page, 3–8 numbered steps, one screenshot where the UI is non-obvious | title is a verb phrase; assumes the tutorial is done |
| **Explain** | researcher | prose, diagrams, worked numbers from the demo workspace | each page links to the spec it summarises and to the paper section if one exists |
| **Reference** | both | tables; generated where possible | no advice, no narrative |

Proposed tree (docs site root = `docs/`; `docs/specs/` stays where it is):

```
docs/
├── index.md                       landing: who this is for, the two paths
├── start/
│   ├── install.md                 browser (Chrome / Safari) and local install
│   ├── first-workspace.md         pick a folder, scan, what the Flights tab shows
│   └── first-report.md            read one flight report end to end
├── guides/
│   ├── add-logs.md                SD card vs Garmin Pilot export, where to put them
│   ├── compare-flights.md
│   ├── pin-a-reference.md         Spec 12 pinning
│   ├── add-a-filter.md            Spec 09
│   ├── acknowledge-an-insight.md
│   ├── exclude-a-flight.md        baseline exclusion with reason
│   ├── switch-engine.md           916iS / 915iS, what "placeholder" means
│   ├── export-and-share.md        results bundle; what leaves your machine (nothing raw)
│   └── backup-on-ipad.md          Safari storage caveats (Spec 02 §2.8)
├── explain/
│   ├── why-fadec-is-different.md
│   ├── flight-phases.md
│   ├── baselines-and-shift.md     recent window vs reference, σ, the ranking statistic
│   ├── filters-vs-om-limits.md
│   ├── egt-spread-and-balance.md
│   ├── engine-ecu-alerts.md       POWERUP / LANE_CHECK / SHUTDOWN / IN_FLIGHT
│   ├── overboost.md
│   ├── fuel-and-efficiency.md
│   ├── turbo-health-map.md        takeoff-MAP residual
│   ├── how-insights-are-worded.md Analysis line / Insight line
│   └── the-research-paper.md      intro + link to the paper
├── paper/                         research paper, markdown, one file per edition
├── reference/
│   ├── topics.md                  GENERATED from the Spec 10 register
│   ├── limits/<engine>.md         GENERATED from engines/*.json
│   ├── settings.md                GENERATED from the settings/rules schema where possible
│   ├── log-format.md              G3X columns used, both export formats
│   ├── cli.md                     GENERATED from argparse help
│   ├── glossary.md                hand-written
│   └── whats-new.md               GENERATED from CHANGELOG.md
├── specs/                         existing; surfaced under "Developer" in the nav
└── img/                           screenshots, named <page>--<step>.png
```

## 4. Toolchain

- **MkDocs with the Material theme.** Chosen for built-in client-side search, tabs/admonitions, good image handling, and because it publishes as plain static files next to the web app. Config in `mkdocs.yml` at repo root; `docs_dir: docs`.
- **Plugins:** `search` (default), `mkdocs-macros` or a small pre-build script for the generated pages (§5), `glightbox` for click-to-zoom screenshots, `git-revision-date` for "last updated".
- **Build:** `make docs` → runs the generators (§5), then `mkdocs build --strict` (broken link = build failure). CI runs the same on every PR.
- **Publish:** GitHub Pages. Open question whether the site lives at `/docs/` under the app's host or on its own subdomain (§11).

## 5. Generated reference pages

A single script, `tools/gen_docs.py`, importable and unit-tested, writes markdown into `docs/reference/`. Generated files carry a header comment `<!-- generated by tools/gen_docs.py — do not edit -->` and are committed, so the site renders on GitHub without a build and diffs show what changed.

| Page | Source | Content |
|---|---|---|
| `topics.md` | `slingology_eis.registry` (Spec 10 register) | one section per topic: id, plain name, what it measures, unit, phase it is measured in, comparison (baseline / OM / both), which Trends panel it feeds, which rule in `insight_rules.json` triggers its insight, link to the Explain page via a `docs` field in the register |
| `limits/<engine>.md` | `engines/*.json` | every OM limit with value, unit, OM source citation, verification status; placeholder engines carry the warning banner |
| `settings.md` | rules/settings schema | each tunable with default, range, where it is set in the UI |
| `cli.md` | `cli.py` argparse | subcommands, options, exit codes |
| `whats-new.md` | `CHANGELOG.md` | last three versions, user-facing entries only (entries tagged `[internal]` are dropped) |

Register change required: add an optional `docs: {explain: "explain/egt-spread-and-balance.md", summary: "…"}` field to the Spec 10 register entry. `summary` is the one-paragraph help text (§6). The generator fails if any topic lacks `docs.summary`.

Tests: `tests/test_gen_docs.py` builds the reference pages into a temp dir against the real registry and the provided logs' engine profile, and asserts every registered topic and every engine limit appears exactly once.

## 6. Shared help text (docs ↔ app)

The web app shows a "?" on each Trends card, each insight, each filter and each setting. The text behind it is **the same paragraph as the docs**, not a second copy.

- Source of truth: the `docs.summary` field in the register (topics) and the first paragraph under a `<!-- help -->` marker in the relevant Explain or Guide page (everything else).
- Build step: `tools/gen_help.py` extracts these into `web/src/help/help.json`, keyed by stable ids (`topic.egt_spread`, `setting.recent_window_hours`, `concept.shift`). The file is committed.
- Each help popover ends with a "Learn more" link to the docs page, anchored to the section.
- Test: every id the UI requests exists in `help.json`; every id in `help.json` is referenced by the UI or flagged as orphaned.

## 7. Demo workspace and screenshots

Screenshots are the costliest asset to keep honest. Two rules:

1. **All screenshots are taken from one reproducible demo workspace,** never from the author's live data.
2. **Screenshots are regenerated by a script,** not by hand, so a UI change means re-running it rather than re-doing it.

**Demo workspace.** A results bundle (Spec 02 format) built from the project's 50-flight N117ZS dataset with `--anonymize`, shipped at `docs/demo/demo-workspace.bundle`. Because raw logs never enter a bundle, the Flight view's detailed charts need at least one real log: ship two anonymised logs (one normal cruise flight, one with an in-flight ENGINE ECU event) under `docs/demo/logs/`. Decision needed on anonymisation depth — tail number and system ID are already stripped; route/airport hints are the remaining identifiers (§11).

The same demo workspace is what the tutorial tells a new user to load first, so the tutorial can be followed before they have logs of their own, and the Explain pages can quote real numbers from it ("in the demo workspace, cylinder 4 runs 31 °F above the mean of 1–3…").

**Screenshot script.** `tools/shoot.py` (Playwright) loads the app with the demo workspace, walks a list of `(page-id, url, actions, viewport)` entries and writes `docs/img/<page>--<step>.png`. Run per release; the diff is reviewed like code. Annotations (arrows, numbered callouts) are drawn by the script from coordinates in the same list, so they survive re-shoots.

## 8. The AI-askable corpus

Nothing bespoke; make the corpus easy to ingest.

- `docs/llms.txt` at the site root, listing the pages with one-line descriptions, per the llms.txt convention.
- `docs/bundle.md`, generated at build: every Start, Guide, Explain and Reference page concatenated in nav order, each prefixed with its path and kind, images replaced by their alt text. One file a user drops into Claude or NotebookLM. Target under 150 k words; specs and the paper are appended as a second file, `bundle-deep.md`, for researchers.
- Each page's first paragraph answers "what is this page for" in a form that reads well out of context — that is what a retrieval step will see.
- A short page `guides/ask-your-ai.md` tells users how to do this and what to paste.

## 9. Writing rules

- Pilot pages: second person, present tense, no jargon without a glossary link, numbers always with units, one idea per screenshot.
- Explain pages: say what is measured, how, compared against what, and what it does not tell you. Every statistical claim links to the spec or the paper section that supports it. Open questions are stated as open, not hidden.
- Safety framing (standing rule): the tool informs; it does not clear an aircraft to fly or replace the OM. Appears once on the landing page and in `explain/filters-vs-om-limits.md`, not on every page.
- Each page carries front matter: `kind`, `audience`, `spec` (if any), `last-verified-ui-version`.
- README shrinks to: what this is, install in three lines, link to the site, link to CHANGELOG. The current README user manual moves into `start/` and `guides/`.

## 10. Phasing

| Phase | Deliverable | When |
|---|---|---|
| 1 | `mkdocs.yml`, landing page, `gen_docs.py` producing `topics.md` and `limits/*.md`, register `docs` field, tests | can start now; no UI dependency |
| 2 | Explain tier — ten pages, drawn from specs 08–12 and the paper; `help.json` generator and UI wiring | after Session B engine gaps close |
| 3 | Demo workspace, screenshot script, Start tutorial, Guides | after Session B UI stabilises |
| 4 | `bundle.md`, `llms.txt`, `ask-your-ai.md`, `whats-new.md`, README shrink | with the release that ships the web UI |
| later | in-app Ask (needs a key-management story), per-insight deep links from the app into Explain pages | — |

## 11. Open questions

1. ~~**Hosting:** docs at `<app host>/docs/` or a separate `docs.` subdomain? Same-host keeps "Learn more" links trivial.~~ **Resolved (v0.2):** neither — the docs are on GitHub Pages at `https://alchemygeek.github.io/Rotax9iSEIS/`, confirmed permanent; see Spec 15 §6–§7.
2. **Anonymisation depth for the demo logs:** strip airport/route hints too, or keep them so the tutorial can say "KACV"?
3. **Paper location:** `docs/paper/` in this repo (one source, versioned with the code) or kept separate as now? This spec assumes in-repo.
4. **Register field or sidecar:** put `docs.summary` into the Spec 10 register (keeps topic and its text together) or in a parallel `docs/help/topics.yml` (keeps prose out of Python)? This spec assumes in-register, with a test that fails on a missing summary.
5. **Playwright dependency:** acceptable as a dev-only extra (`pip install -e ".[docs]"`), or should screenshots stay manual for v1?

## 12. Acceptance

- `make docs` passes with `--strict` on a clean checkout.
- Every topic in the register and every limit in `engines/916iS.json` and `915iS.json` appears in the reference pages (tested).
- Every "?" in the web UI resolves to a `help.json` entry whose text also appears verbatim on a docs page (tested).
- A new user with no logs can complete `start/` using only the demo workspace.
- `bundle.md` regenerates from the same build and, dropped into Claude, answers "how is shift computed?" and "what is the OM oil temperature limit on a 916iS?" correctly.
