# SlingologyEIS web UI

The browser front end of SlingologyEIS: React 19 + TypeScript, Vite, React Router, ECharts.
It talks to the local server (`slingology-eis serve`, `POST /rpc`) through one client,
`src/lib/engineClient.ts`, and renders a sample workspace from `src/fixtures/` whenever no
server is reachable. The engine itself is Python (`../slingology_eis/`); this app holds no
analysis logic, only presentation and the decision workflows the specs describe.

Design and behaviour are owned by the specs in `../docs/specs/`: 03 (information
architecture), 05 (bootstrap), 07 (flight chart), 09 (filters), 12 (Trends), 14 (Settings,
Journal, rule editing on the card). Change the spec first.

## Build and run

```bash
npm ci
npm run build              # tsc -b + vite build → dist/, served by `slingology-eis serve`
npm run dev                # Vite dev server with HMR, proxied to nothing — start
                           # `slingology-eis serve` separately; the client calls 127.0.0.1:8420
npx vitest run             # unit/component tests (jsdom)
npx tsc -b --noEmit        # type check
npm run lint               # oxlint
```

`npm run build` is `tsc -b && vite build`. `npx vitest run` exits 0 (the jsdom `scrollIntoView`
error of BACKLOG P5 is guarded in Trends).

## Two hosts, one build (Spec 04 v0.9 §9.5, §9.7)

The page reads `runtime.json` first and talks to whichever host it names:

| Mode | `runtime.json` | Where the engine runs | How to run it |
|---|---|---|---|
| Local server | `{"host": "server"}`, served by `slingology-eis serve` itself | The Python process on your machine | `npm run build`, then `slingology-eis serve` (in a checkout it serves `web/dist`; an installed wheel carries its own copy of the UI) |
| In the browser | `{"host": "browser", "pyodide": …, "pyodide_url": …, "engine_wheel": …}`, written by the site build | A Web Worker running Pyodide, data in the browser's OPFS | `npm run build:browser`, then serve `dist/` as plain files, e.g. `python -m http.server -d dist 8000` |

The browser fields: `pyodide` is the pinned version (`../PYODIDE_VERSION`), `pyodide_url` the folder
holding that release (`pyodide/`), `engine_wheel` the engine wheel's path (`engine/slingology_eis-….whl`);
both paths are relative to the app's own folder.

**npm scripts:**

| Script | What it does |
|---|---|
| `npm run dev` | Vite with HMR, local-server mode: the app talks to `slingology-eis serve` on 127.0.0.1:8420 |
| `npm run dev:browser` | Browser mode under Vite: runs `engine` first, then Vite with `EIS_HOST=browser` |
| `npm run engine` | The engine wheel → `public/engine/`, the pinned Pyodide → `public/pyodide/`; again after engine changes |
| `npm run build` | `tsc -b` + `vite build` → `dist/`, the UI alone (local-server mode). It empties `dist/` first — a browser site built there is replaced |
| `npm run build:browser` | The whole browser site in `dist/` (`../scripts/build_site.py --out dist`) |
| `npm run build:site` | The same site in `../_site/` (what CI builds and keeps) |
| `npm test`, `npm run lint` | `vitest run`, `oxlint` |

The build scripts run `python3`; they need no packages of their own (`setuptools` is fetched by pip if
that Python lacks it).

**The static site** works on any static host, including GitHub Pages (relative paths, no custom
headers; `../docs/hosting.md` says how it is published). It holds `index.html` and `assets/`,
`runtime.json`, `pyodide/` (the pinned release with numpy, pandas and what they need, and a
`MANIFEST.json` of SHA-256s), `engine/` (the wheel), and `sw.js`. Nothing loads from any other
server; even the fonts are bundled (`@fontsource`).

- **Offline (step 6).** `sw.js` is `./sw.js` with the release's file list prepended by the site
  build. The page registers it only in browser mode; it caches the whole release on the first visit,
  so the site opens and analyses with no network after that. A new build installs into its own cache
  in the background and takes over when the engine is idle; the page reloads into it and says
  *Updated to version …* once. `npm run build`, `vite` dev and server mode have no service worker.
- **The engine wheel** (`../scripts/build_engine_wheel.py`) is a build artefact (`public/engine/`,
  `dist/engine/`), not committed. `../setup.py` adds the runtime files (engine profiles, rules, presets,
  config, the topic register) as `slingology_eis/_data/` and the built UI as `slingology_eis/_web/` —
  run `npm run build` first for a wheel with a current UI (the site build does). In a checkout the
  repo-root files and `web/dist` are used directly (`../slingology_eis/resources.py`).
- **A missing or unreadable `runtime.json`** shows "This installation is incomplete", naming the URL
  that was tried, rather than guessing a host.

**Browser host, in brief:**
- `src/worker/engine.worker.ts` loads the site's own Pyodide and the wheel, and mounts OPFS at `/data`.
- It runs `slingology_eis.browser_host`, and syncs the filesystem after every operation, before answering.
- `src/lib/browserClient.ts` (`BrowserWorkerClient`) is `LocalServerClient`'s twin over `postMessage`.
  The engine answers one request at a time: an identical read already waiting is shared, and the
  nav badges wait behind the page's own requests (`src/lib/pageRequests.ts`).
- `src/lib/pageFolders.ts` lists each folder once per session (and again on Sync, Reconnect/Allow or
  Add), and supplies log bytes when the engine asks:
  - Chrome: `showDirectoryPicker`, with handles kept in IndexedDB;
  - Safari: `<input webkitdirectory>` or a dropped folder.
- The UI gates on `get_capabilities` (`src/lib/capabilities.ts`), never on which host it is.

**Checks** (`../spike/browser-host/`, headless Chrome; run with `.venv/bin/python`):
- `run_parity.py` needs a site built with `--e2e` (the test hook); it syncs the test logs and compares
  the export and every analysis with server mode, with memory and timings.
- `run_walkthrough.py --site DIR` drives a shipped site through its UI and checks that nothing loads
  from elsewhere; `run_server_walkthrough.py --url … --logs …` does the same for `slingology-eis serve`.
- `run_offline.py --site DIR`: the first visit caches the release; offline the site opens, a dropped
  log is analysed and a flight opens; a rebuilt site is announced once.
- `run_flights_profile.py --site DIR` (an `--e2e` site): how long Flights takes to open, per request.
- The conformance tests also run under Pyodide in Node (`tests/unit/test_server.py`, call path
  `pyodide_node`; needs `npm ci` here for the `pyodide` package).
- The manual Chrome and Safari release checks: `../docs/specs/browser-support-checklist.md`.
- CI (`../.github/workflows/ci.yml`) runs the automated ones and keeps the wheel and the site as artifacts.

## Layout

```
src/
├── App.tsx            # Routes: /flights, /flights/:id, /logs/:file, /trends, /journal, /settings
│                      # (old /baselines, /annotations, /ecu, /skipped/* redirect)
├── views/             # One file per screen: Flights, FlightView, LogPreview, Trends, Journal, Settings
├── components/        # Chart (ChannelTimeline, PhaseMinimap, EventStrip…), cards (InsightCard,
│                      # EventsTable, FlightFacts), dialogs (ExcludeDialog, PinDialogs, RuleEditorPanel,
│                      # FilterEditor, ImportWorkspaceDialog, DataLocation), NavShell, ErrorBoundary,
│                      # InlineHelp, ScopeCaption
├── lib/               # engineClient (RPC + /upload), fixtures fallback, phases, scope wording,
│                      # inline help registry, topic roster rule, flight facts allow-list, trends
│                      # tiers/units, sourceFormat, dataLocation, importWorkspace
├── types/contract.ts  # TypeScript mirror of the engine contract (keep in step with ../contract/schema/)
├── fixtures/          # Sample workspace: synthetic or scrubbed, no tail/GPS/airport/real time
└── theme/             # Colour tokens (dark theme), mirrored for ECharts canvases
scripts/gen_cas_fixture.py   # Regenerates the synthetic CAS/Events fixture flights
```

## Conventions

- Every decision control states its scope before use (`lib/scope.ts`, `ScopeCaption`): *This
  flight only* or *All flights in this workspace*, repeated on the Apply button.
- User-facing text says **reference**, never "baseline"; internal identifiers keep their names.
- Help sentences live in one registry (`lib/inlineHelp.ts`); a test checks every id is used
  exactly where the spec lists it.
- Readiness, suppression reasons and event classes come from the engine; the UI never infers
  one from raw numbers.
- Pages show "Loading…" until the server's first answer; the bundled samples appear only when no
  server answers, never as a flash before real data.
- Tested on macOS Chrome, macOS Safari and iPad Safari only.
