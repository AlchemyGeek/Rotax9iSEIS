# Slingology EIS — notes for Claude Code sessions

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
   pip install -e . pytest jsonschema
   python -m pytest -q
   ```
   With the logs present the full suite runs the real-data tests too and takes
   well over 10 minutes; run it in the background. Without the logs those
   tests skip automatically.

Rules for the data:

- Never commit flight logs, or anything derived from them (reports, golden
  fixtures, workspace caches), to this repo. They contain the tail number,
  times and airports.
- Treat `EIS-Test-Data` as read-only; the owner adds new flights to it.
