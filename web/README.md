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

`npm run build` is `tsc -b && vite build`. `npx vitest run` exits 0 (the jsdom
`scrollIntoView` error of BACKLOG P5 is guarded in Trends).

## Two hosts, one build (Spec 04 v0.8 §9.5, §9.7)

The page reads `runtime.json` first and talks to whichever host it names:

| Mode | `runtime.json` | Where the engine runs | Built and run with |
|---|---|---|---|
| Local server | `{"host": "server"}`, answered by `slingology-eis serve` itself | The Python process on your machine | `pip install` the wheel (it carries this UI), then `slingology-eis serve`. In a checkout, `npm run build` and `serve` uses `web/dist` |
| In the browser | `{"host": "browser", "pyodide", "pyodide_url", "engine_wheel"}`, written by the site build | A Web Worker running Pyodide, data in the browser's OPFS | `python ../scripts/build_site.py --out DIR` (or `npm run build:site` → `../_site/`), then serve that folder as plain files, e.g. `python -m http.server -d DIR 8000` |

### The static site
The site folder works on any static host, including GitHub Pages: relative paths, and no custom headers. It holds:
- `index.html` and `assets/`;
- `runtime.json`;
- `pyodide/`: the release pinned in `../PYODIDE_VERSION`, with only numpy, pandas and the packages they need. `MANIFEST.json` lists every file with its SHA-256 (`../scripts/stage_pyodide.py`);
- `engine/`: the engine wheel.

A built site loads nothing from any other server; even the fonts are bundled (`@fontsource`).

### The engine wheel
`python ../scripts/build_engine_wheel.py --out DIR` is a standard setuptools build. `../setup.py` adds the runtime files (engine profiles, rules, presets, config, the topic register) as `slingology_eis/_data/`, and this folder's `dist/` as `slingology_eis/_web/`.
- **Build the UI first.** For a wheel that carries a current UI, run `npm run build` before building it. CI does this.
- **Where files are looked up:** in a checkout the repo-root files and `web/dist` are used directly; anywhere else, the packaged copies (`slingology_eis/resources.py`).

### Development
```bash
npm run dev            # local-server mode: the app talks to `slingology-eis serve` on 127.0.0.1:8420
npm run engine         # once (and after engine changes): the wheel → public/engine/, Pyodide → public/pyodide/
npm run dev:browser    # browser mode under Vite (runs `engine` first)
npm run build:browser  # the browser site, in place in dist/
```

A missing or unreadable `runtime.json` shows "This installation is incomplete" rather than guessing a host.

### Browser host, in brief
- `src/worker/engine.worker.ts` loads the site's own Pyodide and the wheel, and mounts OPFS at `/data`.
- It runs `slingology_eis.browser_host`, and syncs the filesystem after every operation, before answering.
- `src/lib/browserClient.ts` (`BrowserWorkerClient`) is `LocalServerClient`'s twin over `postMessage`.
- `src/lib/pageFolders.ts` lists each folder once per session (and again on Sync, Reconnect/Allow or Add), and supplies log bytes when the engine asks:
  - Chrome: `showDirectoryPicker`, with handles kept in IndexedDB;
  - Safari: `<input webkitdirectory>` or a dropped folder.
- The UI gates on `get_capabilities` (`src/lib/capabilities.ts`), never on which host it is.

### Checks
- `../spike/browser-host/run_parity.py` needs a site built with `--e2e`, which adds the test hook. It syncs the test logs in headless Chrome and compares every analysis and the export with server mode, with memory and timings.
- `run_walkthrough.py --site DIR` drives a shipped site through its UI and checks that nothing loads from elsewhere.
- `run_server_walkthrough.py --url … --logs …` does the same for `slingology-eis serve`.
- The conformance tests also run under Pyodide in Node (`tests/unit/test_server.py`, call path `pyodide_node`; needs `npm ci` here).
- CI (`../.github/workflows/ci.yml`) runs all of it and keeps the wheel and the site as artifacts.

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
