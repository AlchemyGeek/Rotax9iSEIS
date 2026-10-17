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

`npm run build` is `tsc -b && vite build`. `npx vitest run` exits non-zero on a jsdom
`scrollIntoView` error although every test passes; tracked in `../BACKLOG.md` (P5).

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
