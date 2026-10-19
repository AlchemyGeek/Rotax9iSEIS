// The browser host's Python entry under Pyodide in Node.js (Spec 04 v0.7
// §9.6 mode 3): the same engine wheel and slingology_eis.browser_host the
// worker loads, run by Node with no browser, driven over stdin/stdout one
// JSON line per message. The conformance tests (tests/unit/test_server.py,
// call path "pyodide_node") start one of these per test session.
//
//   node web/scripts/node-host.mjs --wheel PATH --mount DIR [--mount DIR …]
//
// Each --mount exposes a host folder at the same path inside Pyodide
// (NODEFS), so the tests' temporary folders, logs and exports are the same
// paths on both sides. Messages in:
//   {"cmd":"start", "config":{data_root, workspace_arg, host, sources}, "env":{…}}
//   {"cmd":"request", "envelope_json":"{…}"}
//   {"cmd":"upload", "upload_id", "path", "filename"}
// Messages out: {"ok":true, "result":…} or {"ok":false, "error":"…"}, one per message in.
import { readFileSync, mkdirSync } from "node:fs";
import { createInterface } from "node:readline";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPyodide } from "pyodide";

const args = process.argv.slice(2);
const opt = (name) => args.flatMap((a, i) => (a === name ? [args[i + 1]] : []));
const wheel = opt("--wheel")[0];
const mounts = opt("--mount");
const here = dirname(fileURLToPath(import.meta.url));
const cache = resolve(here, "../node_modules/.pyodide-packages");
mkdirSync(cache, { recursive: true });

const out = (msg) => process.stdout.write(JSON.stringify(msg) + "\n");
const deliveries = new Map();

const pyodide = await loadPyodide({ packageCacheDir: cache, stdout: (s) => process.stderr.write(s + "\n"), stderr: (s) => process.stderr.write(s + "\n") });
await pyodide.loadPackage(["numpy", "pandas"], { messageCallback: () => {} });
pyodide.unpackArchive(new Uint8Array(readFileSync(wheel)), "wheel");
for (const dir of mounts) {
  pyodide.FS.mkdirTree(dir);
  pyodide.FS.mount(pyodide.FS.filesystems.NODEFS, { root: dir }, dir);
}
const host = pyodide.pyimport("slingology_eis.browser_host");
const bridge = {
  emit_progress() {},
  deliver_file(path) {
    const token = `/download/${deliveries.size + 1}`;
    deliveries.set(token, path);
    return token;
  },
};
out({ ok: true, result: { ready: true, pyodide: pyodide.version } });

const lines = createInterface({ input: process.stdin });
for await (const line of lines) {
  if (!line.trim()) continue;
  try {
    const msg = JSON.parse(line);
    if (msg.cmd === "start") {
      const os = pyodide.pyimport("os");
      for (const [k, v] of Object.entries(msg.env || {})) os.environ.set(k, v);
      // Scratch files (exports) land on a mounted folder, readable by the tests.
      if (msg.env?.TMPDIR) pyodide.runPython("import tempfile; tempfile.tempdir = None");
      out({ ok: true, result: JSON.parse(host.start(bridge, pyodide.toPy(msg.config))) });
    } else if (msg.cmd === "request") {
      // The envelope's own JSON text, untouched: re-serialising it in JS
      // would turn 3.0 into 3 before Python sees it.
      out({ ok: true, result: JSON.parse(host.handle_sync(msg.envelope_json)) });
    } else if (msg.cmd === "upload") {
      host.register_upload(msg.upload_id, msg.path, msg.filename);
      out({ ok: true, result: null });
    } else if (msg.cmd === "download") {
      out({ ok: true, result: deliveries.get(msg.token) ?? null });
    } else {
      out({ ok: false, error: `unknown cmd ${msg.cmd}` });
    }
  } catch (e) {
    out({ ok: false, error: String(e && e.message ? e.message : e) });
  }
}
