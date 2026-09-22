# Spike harness (Spec 04, Part A)

Tests whether the **real** engine code — `load_log`, `detect_phases`,
`build_flight_metrics` — runs correctly and fast enough inside Pyodide
(Python compiled to WebAssembly, running in a browser). This is the
follow-up to the synthetic pandas benchmark: this harness runs your actual
Python modules against a real flight log, in the browser, and diffs the
result against a native golden output field by field.

Covers spike questions S1 (parity), S2 (speed), S3 (memory), and gives a
crash signal for S8. It does **not** yet cover S5 (offline), S6 (main-thread
responsiveness — the worker architecture is used, but no frame-gap sampler
is wired up), or S7 (persistence). Those are a follow-up if this run looks
good.

## 1. Place this folder

Put this `spike/` folder at the **root of the repo**, next to
`slingology_eis/`, `engines/`, `config.json`, and `insight_rules.json`. The
harness fetches those files relative to its own location, so it must sit
one level below them.

```
Rotax9iSEIS/
├── slingology_eis/
├── engines/
├── config.json
├── insight_rules.json
├── notebooks/
└── spike/              <- this folder
    ├── index.html
    ├── worker.js
    ├── native_reference.py
    └── README.md
```

**Do not commit this folder to the public repo yet.** It's a local testing
tool; if you want to keep it in git, that's a separate decision (Spec 04
§10, Q5) and the log files it touches must never be committed unscrubbed.

## 2. Produce the native golden (once, on your Mac)

```bash
source ~/venvs/eis/bin/activate   # the venv with pandas/numpy, from Part 1
cd Rotax9iSEIS                    # repo root
python3 spike/native_reference.py /path/to/log_20260423_200615_KACV.csv
```

This writes `golden.json` at the repo root. It prints a one-line summary;
keep the file, you'll load it into the browser page in step 4.

## 3. Serve the repo and open the harness

Pyodide needs the page loaded over HTTP (not `file://`), so it can fetch
the engine source and the log you pick.

```bash
cd Rotax9iSEIS       # repo root
python3 -m http.server 8000
```

Then open, on **macOS Chrome** and **macOS Safari**:

```
http://localhost:8000/spike/
```

For the **iPad**, the iPad needs to reach your Mac over the local network,
not `localhost`. Find your Mac's LAN IP (System Settings → Wi-Fi → Details,
or `ipconfig getifaddr en0` in Terminal), bind the server to all
interfaces, and make sure both devices are on the same Wi-Fi:

```bash
python3 -m http.server 8000 --bind 0.0.0.0
```

Then on the iPad, open `http://<your-macs-lan-ip>:8000/spike/`.

## 4. Run it

1. Click **Initialize Pyodide**. Watch the log underneath — it should end
   with `ready` and show no `MISSING FILES` warning. If it does, the
   `spike/` folder probably isn't at the repo root (step 1).
2. Drag your log CSV onto the drop zone, or use the file picker.
3. Click **Run pipeline**. It runs `load_log` → `detect_phases` →
   `build_flight_metrics` for real, inside the browser, on that log.
4. Optionally, load the `golden.json` from step 2 under "Compare against a
   native golden" — the page will show a field-by-field match/differ table
   for all 35 metrics.
5. Click **Download results JSON** and save it somewhere you'll find again.
   It contains timings, the browser's user agent, and the parity-relevant
   output — never the log itself.

Repeat on macOS Chrome, macOS Safari, and iPad Safari. If a run seems to
freeze or the page reloads on its own, reload it: a banner at the top will
say the previous run didn't complete cleanly, which is the crash signal
for that platform.

## 5. What to send back

For each platform:

- The **timing table** from the downloaded JSON (`init.t_runtime_s`,
  `t_packages_s`, `t_mount_s`, `t_ready_s`, and `result.steps_s` /
  `result.total_wall_s`).
- The **heap_mb** figures from init and from the run.
- Whether the **golden diff** showed "All metric fields match" or listed
  differences (send the differing rows if any).
- Any crash banner, and which step it happened on.

## Known limitations of this first cut

- Pyodide is loaded from `cdn.jsdelivr.net`, not self-hosted. That's fine
  for this local test; self-hosting is a step for the real deployment
  (Spec 04 §4.4 offline test still needs a proper build).
- No frame-gap sampler yet — we're not measuring UI responsiveness while
  the worker runs, only that it *is* a worker.
- No persistence probes (OPFS/IndexedDB) — Spec 02 territory once this
  passes.
- The harness mounts source files individually over HTTP rather than as a
  single archive (Spec 04 §8 describes an archive; this is a simpler stand-in
  that's fine for a spike of this size).
