/// <reference lib="webworker" />
// The browser host (Spec 04 v0.7 §9.2, step 4): Pyodide, the engine wheel
// and the transport-neutral host, in one dedicated worker, against a data
// root mounted from OPFS. The page never runs Python.
//
// Page → worker:
//   {type:"init", pyodide, wheelUrl}
//   {type:"request", envelope}                 one Spec 01 §7 envelope
//   {type:"upload", upload_id, filename, bytes} a dropped file / export zip
//   {type:"listing", req, listing|null}        answers a need-listing
//   {type:"file", req, bytes|null}             answers a need-file
// Worker → page:
//   {type:"loading", phase, done, total}       runtime download progress
//   {type:"ready", engine_version, pyodide_version, registry_present}
//   {type:"failed", message}
//   {type:"reply", request_id, reply}          series as typed arrays
//   {type:"progress", request_id, stream, update}
//   {type:"need-listing"|"need-file", request_id, req, folder_id, relative_path?}
//   {type:"release", folder_id, relative_path}
//   {type:"deliver", request_id, token, filename, bytes}
//   {type:"uploaded", upload_id}
//   {type:"memory", req, bytes}               the WebAssembly heap, on request

declare const self: DedicatedWorkerGlobalScope;

const DATA_ROOT = "/data";
const OPFS_DIR = "slingology-eis";       // the app's folder inside the origin's OPFS

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Py = any;
let pyodide: Py = null;
let host: Py = null;
let nativefs: { syncfs: () => Promise<void> } | null = null;
let currentRequest: string | null = null;
let nextReq = 1;
const waiting = new Map<number, (value: unknown) => void>();

function post(msg: unknown, transfer: Transferable[] = []) {
  self.postMessage(msg, transfer);
}

function ask(kind: "need-listing" | "need-file", body: Record<string, unknown>): Promise<unknown> {
  const req = nextReq++;
  return new Promise((resolve) => {
    waiting.set(req, resolve);
    post({ type: kind, request_id: currentRequest, req, ...body });
  });
}

// What Python calls back into (browser_host.start's `bridge`).
const bridge = {
  request_listing(folderId: string) {
    // undefined, not null: Pyodide turns JS null into JsNull, undefined into None.
    return ask("need-listing", { folder_id: folderId }).then((listing) => (listing == null ? undefined : pyodide.toPy(listing)));
  },
  request_file(folderId: string, relativePath: string) {
    return ask("need-file", { folder_id: folderId, relative_path: relativePath }).then((bytes) =>
      bytes == null ? undefined : new Uint8Array(bytes as ArrayBuffer));
  },
  release_file(folderId: string, relativePath: string) {
    post({ type: "release", folder_id: folderId, relative_path: relativePath });
  },
  emit_progress(stream: string, updateJson: string) {
    post({ type: "progress", request_id: currentRequest, stream, update: JSON.parse(updateJson),
           heap: pyodide._module.HEAP8.length });
  },
  deliver_file(path: string, filename: string) {
    const data: Uint8Array = pyodide.FS.readFile(path);
    const token = `delivered:${crypto.randomUUID()}`;
    const bytes = data.buffer.slice(data.byteOffset, data.byteOffset + data.byteLength);
    post({ type: "deliver", request_id: currentRequest, token, filename, bytes }, [bytes]);
    return token;
  },
};

// Series ({channel: [[t, v|null], …]}) cross as two Float64Arrays per
// channel, NaN for null (Spec 01 §8.7); the client turns them back.
function packSeries(result: Record<string, [number, number | null][]>) {
  const packed: Record<string, { t: Float64Array; v: Float64Array }> = {};
  const transfer: Transferable[] = [];
  for (const [ch, pairs] of Object.entries(result)) {
    if (!Array.isArray(pairs)) return { packed: null, transfer: [] };
    const t = new Float64Array(pairs.length);
    const v = new Float64Array(pairs.length);
    pairs.forEach(([x, y], i) => { t[i] = x; v[i] = y == null ? NaN : y; });
    packed[ch] = { t, v };
    transfer.push(t.buffer, v.buffer);
  }
  return { packed, transfer };
}
const SERIES_OPS = new Set(["get_series", "get_flight_series", "get_excluded_log_series"]);

async function boot(version: string, wheelUrl: string) {
  const base = `https://cdn.jsdelivr.net/pyodide/v${version}/full/`;
  post({ type: "loading", phase: "runtime", done: 0, total: 4 });
  const mod = await import(/* @vite-ignore */ `${base}pyodide.mjs`);
  pyodide = await mod.loadPyodide({ indexURL: base });
  post({ type: "loading", phase: "numpy and pandas", done: 1, total: 4 });
  await pyodide.loadPackage(["numpy", "pandas"]);
  post({ type: "loading", phase: "engine", done: 2, total: 4 });
  const wheel = await (await fetch(wheelUrl)).arrayBuffer();
  pyodide.unpackArchive(wheel, "wheel");
  post({ type: "loading", phase: "your data", done: 3, total: 4 });
  const top = await navigator.storage.getDirectory();
  const dir = await top.getDirectoryHandle(OPFS_DIR, { create: true });
  nativefs = await pyodide.mountNativeFS(DATA_ROOT, dir);
  host = pyodide.pyimport("slingology_eis.browser_host");
  const status = JSON.parse(host.start(bridge, pyodide.toPy({ data_root: DATA_ROOT, host: "browser" })));
  post({ type: "loading", phase: "ready", done: 4, total: 4 });
  post({ type: "ready", engine_version: status.engine_version, pyodide_version: pyodide.version,
         registry_present: status.registry_present });
}

async function handle(envelope: { op: string; request_id: string }) {
  currentRequest = envelope.request_id;
  let reply;
  try {
    reply = JSON.parse(await host.handle(JSON.stringify(envelope)));
  } finally {
    // Python's writes reach OPFS only after a sync (Spec 04 §9.2): every
    // operation's writes are flushed before its answer goes out.
    await nativefs!.syncfs();
    currentRequest = null;
  }
  if (reply.ok && SERIES_OPS.has(envelope.op) && reply.result && typeof reply.result === "object") {
    const { packed, transfer } = packSeries(reply.result);
    if (packed) {
      post({ type: "reply", request_id: envelope.request_id, reply: { ...reply, result: packed, packed: "series" } }, transfer);
      return;
    }
  }
  post({ type: "reply", request_id: envelope.request_id, reply });
}

function upload(uploadId: string, filename: string, bytes: ArrayBuffer) {
  const dir: string = host.scratch_dir();
  const folder = `${dir}/uploads/${uploadId}`;
  pyodide.FS.mkdirTree(folder);
  const safe = filename.split("/").pop() || "upload";
  pyodide.FS.writeFile(`${folder}/${safe}`, new Uint8Array(bytes));
  host.register_upload(uploadId, `${folder}/${safe}`, safe);
  post({ type: "uploaded", upload_id: uploadId, filename: safe, size: bytes.byteLength });
}

self.onmessage = async (ev: MessageEvent) => {
  const msg = ev.data;
  try {
    switch (msg.type) {
      case "init":
        await boot(msg.pyodide, msg.wheelUrl);
        break;
      case "request":
        await handle(msg.envelope);
        break;
      case "upload":
        upload(msg.upload_id, msg.filename, msg.bytes);
        break;
      case "memory":
        // Spec 04 §7: the worker's WebAssembly heap (answered between file
        // requests too — the engine is paused while it waits for one).
        post({ type: "memory", req: msg.req, bytes: pyodide ? pyodide._module.HEAP8.length : 0 });
        break;
      case "listing":
      case "file": {
        const resolve = waiting.get(msg.req);
        waiting.delete(msg.req);
        resolve?.(msg.type === "listing" ? msg.listing : msg.bytes);
        break;
      }
    }
  } catch (e) {
    const message = e instanceof Error ? `${e.name}: ${e.message}` : String(e);
    if (msg.type === "request") {
      post({ type: "reply", request_id: msg.envelope.request_id,
             reply: { request_id: msg.envelope.request_id, ok: false, error: { code: "INTERNAL_ERROR", message } } });
    } else {
      post({ type: "failed", message });
    }
  }
};
