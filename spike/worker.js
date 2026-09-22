// spike/worker.js
//
// Runs inside a Web Worker. Loads Pyodide + numpy/pandas, fetches the
// project's own Python source (relative to this file, i.e. from ../slingology_eis
// etc.), mounts it into Pyodide's virtual filesystem, and runs the real
// pipeline (load_log -> detect_phases -> build_flight_metrics) on a log
// the main thread hands over as raw bytes.
//
// Spec: docs/specs/04-runtime-adapters-and-pyodide-spike.md, Part A / §8.

const PYODIDE_VERSION = "0.28.0";
const PYODIDE_CDN = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

// Files mounted into the Pyodide FS under /repo, fetched relative to this
// worker's own location (spike/../<path>), i.e. assumes this folder lives
// at <repo-root>/spike/.
const ENGINE_FILES = [
  "slingology_eis/__init__.py",
  "slingology_eis/loader.py",
  "slingology_eis/phases.py",
  "slingology_eis/limits.py",
  "slingology_eis/egt.py",
  "slingology_eis/fuel.py",
  "slingology_eis/cas.py",
  "slingology_eis/climb.py",
  "slingology_eis/fleet.py",
  "engines/912iS.json",
  "engines/914iS.json",
  "engines/915iS.json",
  "engines/916iS.json",
  "config.json",
  "insight_rules.json",
];

let pyodideReadyPromise = null;

function heapMB() {
  try {
    // self.pyodide exposes the underlying emscripten module once loaded.
    return Math.round(self.pyodide._module.HEAP8.length / 1e6);
  } catch (e) {
    return null;
  }
}

function post(type, payload) {
  self.postMessage({ type, ...payload });
}

async function initPyodide(commitLabel) {
  if (pyodideReadyPromise) return pyodideReadyPromise;

  pyodideReadyPromise = (async () => {
    const t0 = performance.now();
    importScripts(PYODIDE_CDN + "pyodide.js");
    self.pyodide = await self.loadPyodide({ indexURL: PYODIDE_CDN });
    const t1 = performance.now();
    post("progress", { stage: "runtime_ready", elapsed_s: (t1 - t0) / 1000 });

    await self.pyodide.loadPackage(["numpy", "pandas"]);
    const t2 = performance.now();
    post("progress", { stage: "packages_ready", elapsed_s: (t2 - t1) / 1000 });

    // Fetch and mount the project's own source files.
    self.pyodide.FS.mkdirTree("/repo/slingology_eis");
    self.pyodide.FS.mkdirTree("/repo/engines");
    self.pyodide.FS.mkdirTree("/repo/data/logs");

    const base = new URL("../", self.location.href); // spike/ -> repo root
    const missing = [];
    for (const rel of ENGINE_FILES) {
      const url = new URL(rel, base).href;
      let res;
      try {
        res = await fetch(url);
      } catch (e) {
        missing.push(rel);
        continue;
      }
      if (!res.ok) {
        missing.push(rel);
        continue;
      }
      const text = await res.text();
      self.pyodide.FS.writeFile("/repo/" + rel, text);
    }
    const t3 = performance.now();
    post("progress", {
      stage: "engine_mounted",
      elapsed_s: (t3 - t2) / 1000,
      missing,
    });
    if (missing.length) {
      post("warning", {
        message:
          "Could not fetch these files relative to spike/ (serve this " +
          "folder from the repo root, e.g. `python3 -m http.server` run " +
          "at the repo root, and open spike/index.html through it): " +
          missing.join(", "),
      });
    }

    const pyVersions = self.pyodide.runPython(`
import sys, numpy, pandas
f"{sys.version.split()[0]}|{numpy.__version__}|{pandas.__version__}"
`);
    const [pyVer, npVer, pdVer] = pyVersions.split("|");

    const t4 = performance.now();
    post("progress", { stage: "ready", elapsed_s: (t4 - t3) / 1000 });
    return {
      t_runtime_s: (t1 - t0) / 1000,
      t_packages_s: (t2 - t1) / 1000,
      t_mount_s: (t3 - t2) / 1000,
      t_ready_s: (t4 - t0) / 1000,
      pyodide_version: PYODIDE_VERSION,
      python_version: pyVer,
      numpy_version: npVer,
      pandas_version: pdVer,
      heap_mb: heapMB(),
    };
  })();

  return pyodideReadyPromise;
}

async function runPipeline(bytes, filename) {
  const py = self.pyodide;
  py.FS.writeFile("/repo/data/logs/" + filename, new Uint8Array(bytes));

  const code = `
import sys, time, json, warnings, math
warnings.filterwarnings("ignore")
sys.path.insert(0, "/repo")

import pandas as pd

results = {"steps_s": {}}

t0 = time.perf_counter()
from slingology_eis.loader import load_log
from slingology_eis.phases import detect_phases, phase_summary
from slingology_eis.fleet import build_flight_metrics
results["steps_s"]["import"] = time.perf_counter() - t0

t0 = time.perf_counter()
df, info = load_log("/repo/data/logs/${filename}")
results["steps_s"]["load_log"] = time.perf_counter() - t0
results["rows"] = len(df)
results["cols"] = len(df.columns)

t0 = time.perf_counter()
df = detect_phases(df)
results["steps_s"]["detect_phases"] = time.perf_counter() - t0

t0 = time.perf_counter()
summary = phase_summary(df)
results["steps_s"]["phase_summary"] = time.perf_counter() - t0

t0 = time.perf_counter()
metrics_df = build_flight_metrics([(df, info)], verbose=False)
results["steps_s"]["build_flight_metrics"] = time.perf_counter() - t0

def clean(v):
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return str(v)
    if pd.isna(v) if not isinstance(v, (list, dict)) else False:
        return None
    return v

row = metrics_df.iloc[0].to_dict()
results["metrics"] = {k: clean(v) for k, v in row.items()}

phases_out = []
for _, r in summary.reset_index().iterrows():
    d = r.to_dict()
    phases_out.append({k: clean(v) for k, v in d.items()})
results["phases"] = phases_out

results["source_format"] = getattr(info, "source_format", None)

json.dumps(results)
`;

  const t_total0 = performance.now();
  const resultJson = await py.runPythonAsync(code);
  const t_total1 = performance.now();
  const result = JSON.parse(resultJson);
  result.total_wall_s = (t_total1 - t_total0) / 1000;
  result.heap_mb = heapMB();
  return result;
}

self.onmessage = async (ev) => {
  const { type } = ev.data;
  try {
    if (type === "init") {
      const info = await initPyodide();
      post("init_done", { info });
    } else if (type === "run") {
      const { bytes, filename } = ev.data;
      post("progress", { stage: "run_start" });
      const result = await runPipeline(bytes, filename);
      post("run_done", { result });
    }
  } catch (err) {
    post("error", { message: String(err && err.stack ? err.stack : err) });
  }
};
