# SlingologyEIS — notes for Claude Code sessions

## How the project is run

- Design is spec-first. Every behaviour is owned by one of `docs/specs/01`–`15`; a change to
  behaviour is a revision of the owning spec (revision-history row, same numbering and scope
  conventions), never a standalone addendum. Prompts to Code are functional; Code owns the
  implementation decisions.
- `README.md`, `CHANGELOG.md`, `BACKLOG.md`, the research paper and this file are updated only
  when the owner asks.
- The engine version (`slingology_eis/__init__.py` and `pyproject.toml`, kept equal) is bumped
  only when a stored flight's analysis could differ from what the current code produces; the
  web UI's Sync uses it to mark flights for re-analysis. Web-only changes don't bump it.
- Rotax Operators Manuals are never stored in the repo; profiles cite them by edition.

## Branches

- `main` — releasable. Bug fixes are committed here directly.
- `webui` (merged at 1.0.0) and `pyodide` (merged at 1.0.1) — kept for history, no new work.
  Feature work of that size goes on a branch off `main`, merged back as a release; `main` is
  merged into it along the way to pick up fixes, and a bug found on the branch is fixed on
  `main` first.

## Two hosts, one engine

The host (`slingology_eis/host.py`) owns the operations and knows nothing about transport;
`server.py` is HTTP, `browser_host.py` is the Pyodide Web Worker entry. A new operation goes in
the host, is gated in the UI by `get_capabilities` (never by which host it is), and is covered
by the operations tests, which run three ways — in-process, over HTTP, and under Pyodide in
Node.js (`web/scripts/node-host.mjs`; needs `npm ci` in `web/`). Anything that reads raw logs
goes through a `LogSource` and must stay a resumable coroutine (one file outstanding), since in
the browser the page supplies the bytes. `PYODIDE_VERSION` pins the runtime; a change there
means re-running the browser parity and persistence checks under `spike/`.

## Real flight-log test data

The flight logs (G3X, and from October 2026 Garmin AXIS) used by the
characterization, contract and CLI tests are private and gitignored (`/data/` in `.gitignore`). They live in a separate
private repo: **`AlchemyGeek/EIS-Test-Data`** (CSV files at the repo root).

At the start of any session that develops or tests the engine, CLI or web UI:

1. Attach the data repo to the session (cloud sessions: the `add_repo` tool
   with owner `AlchemyGeek`, repo `EIS-Test-Data`), then clone it next to this
   checkout:
   ```bash
   git clone --depth 1 https://github.com/AlchemyGeek/eis-test-data ../eis-test-data
   ```
   It is ~200 MB; give the clone a long timeout (~10 min).
2. Link it in as the logs folder, so the default `--logs data/logs/` finds it:
   ```bash
   mkdir -p data && ln -sfn "$(cd ../eis-test-data && pwd)" data/logs
   ```
3. Install and run the tests:
   ```bash
   pip install -e ".[dev]"
   python -m pytest -q
   ```
   With the logs present the full suite runs the real-data tests too and takes
   well over 10 minutes; run it in the background. Without the logs those
   tests skip automatically. With only *some* of the logs present they fail
   rather than skip (`TestScanWithRealLogs` needs specific files; the
   contract tests assert on the full set's counts) — link the whole set or
   none.

Rules for the data:

- Never commit flight logs, or anything derived from them (reports, golden
  fixtures, workspace caches, phase snapshots, per-run ECU lists), to this repo.
  They contain the tail number, times and airports. Aggregate counts in a commit
  message are fine; per-flight detail goes in the session report.
- Treat `EIS-Test-Data` as read-only; the owner adds new flights to it.
- The characterization goldens (`tests/characterization/golden/`, gitignored) are
  regenerated per `tests/characterization/README.md` only when new output is
  intended; diff old vs new first and confirm every change is additive or intended.

## Web UI

```bash
cd web
npm ci
npx vitest run        # 198 tests; exits 1 today on a jsdom scrollIntoView error (BACKLOG P5)
npm run build         # server-mode UI → web/dist/, which `slingology-eis serve` serves
npm run build:browser # the static site for the browser mode (UI, runtime.json, Pyodide, wheel)
npm run dev:browser   # browser mode under Vite, engine wheel built into public/engine/
```

Verify UI changes live in both modes: `slingology-eis serve` and open
`http://127.0.0.1:8420/` against a copy of a real workspace, never the owner's
own — point `SLINGOLOGY_EIS_HOME` at a throwaway data root so nothing touches
the real registry; and the static build in headless Chrome via
`spike/browser-host/run_parity.py` (byte-identical to server mode) and
`run_walkthrough.py`. A server started before a code change serves the old RPC
surface; restart it before blaming the page. Fixtures under
`web/src/fixtures/` are synthetic or scrubbed (`web/scripts/gen_cas_fixture.py`);
they carry no tail number, GPS, airport or real time.

## Changing detection heuristics

Phase detection (`slingology_eis/phases.py`), exceedance checking (`limits.py`),
per-flight metrics (`fleet.py`), ENGINE ECU classification (`cas.py`), the
loader's source normalisation (`loader.py`, incl. the AXIS 1-second grid) and the
topic/insight layer are heuristics tuned on the real logs; a fix for one flight
can quietly change others. Before changing them, snapshot, then compare after the
change and confirm every reported difference is intended (include the aggregate
comparison in the commit message):

```bash
python notebooks/06_phase_regression.py --save before
# ...make the change...
python notebooks/06_phase_regression.py --compare before
```

Snapshots go to `data/phase_snapshots/` (gitignored — derived from flight data).
For changes to insight evaluation, also diff `evaluate_insights()` per flight and
topic (trigger, severity, rule id) before and after, and state the count of
differences.

Limit-saturation guards (Spec 10 D6, acceptance 8–10): a nominal synthetic flight
must raise zero events on every profile, and no limit may fire on more than the
allowed share of real flights unless `docs/specs/topics/register.json` allowlists
it with a diagnosed cause. A profile or phase-rule change must keep these green;
a limit fix must trace to the OM, Rotax documentation or sensor physics, never to
clearing a test.
