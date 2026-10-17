# SlingologyEIS — notes for Claude Code sessions

## How the project is run

- Design is spec-first. Every behaviour is owned by one of `docs/specs/01`–`14`; a change to
  behaviour is a revision of the owning spec (revision-history row, same numbering and scope
  conventions), never a standalone addendum. Prompts to Code are functional; Code owns the
  implementation decisions.
- `README.md`, `CHANGELOG.md`, `BACKLOG.md`, the research paper and this file are updated only
  when the owner asks.
- The engine version (`slingology_eis/__init__.py` and `pyproject.toml`, kept equal) is bumped
  only when a stored flight's analysis could differ from what the current code produces; the
  web UI's Sync uses it to mark flights for re-analysis. Web-only changes don't bump it.
- Rotax Operators Manuals are never stored in the repo; profiles cite them by edition.

## Real flight-log test data

The G3X flight logs used by the characterization, contract and CLI tests are
private and gitignored (`/data/` in `.gitignore`). They live in a separate
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
   tests skip automatically — except `tests/unit/test_workspace.py::TestScanWithRealLogs`,
   which needs specific files from the set and fails rather than skips if only
   some logs are present.

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
npx vitest run        # 129 tests; exits 1 today on a jsdom scrollIntoView error (BACKLOG P5)
npx tsc -b --noEmit   # type check; fails today on EventsTable.test.tsx (BACKLOG P5)
npx vite build        # produces web/dist/, which `slingology-eis serve` serves
```

Verify UI changes live: `slingology-eis serve` and open `http://127.0.0.1:8420/`
against a copy of a real workspace, never the owner's own. Fixtures under
`web/src/fixtures/` are synthetic or scrubbed (`web/scripts/gen_cas_fixture.py`);
they carry no tail number, GPS, airport or real time.

## Changing detection heuristics

Phase detection (`slingology_eis/phases.py`), exceedance checking (`limits.py`),
per-flight metrics (`fleet.py`), ENGINE ECU classification (`cas.py`) and the
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
