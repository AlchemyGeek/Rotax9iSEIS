// The browser host's client (Spec 04 v0.7 §9.2): the same EngineClient as
// LocalServerClient, over postMessage to the engine worker instead of
// POST /rpc. Every operation method is inherited; only the transport and
// the few calls that move bytes or poll progress differ.

import { EngineRpcError, LocalServerClient, type SeriesResult, type UploadFile } from "./engineClient";
import { PageFolders, MAX_LOG_BYTES, type FolderState } from "./pageFolders";
import type { DataLocationProgress, ScanProgress, WorkspaceManifest } from "../types/contract";

export interface BrowserRuntime {
  host: "browser";
  pyodide: string;        // the pinned version (PYODIDE_VERSION)
  pyodide_url: string;    // its folder on this site, relative to the page
  engine_wheel: string;
}

import { EVICTION_MARKER, PERSIST_OUTCOME, type EngineStatus } from "./hostState";

export { EVICTION_MARKER, PERSIST_OUTCOME, type EngineStatus };

interface Pending {
  resolve: (v: unknown) => void;
  reject: (e: unknown) => void;
}

function unpackSeries(packed: Record<string, { t: Float64Array; v: Float64Array }>): SeriesResult {
  const out: SeriesResult = {};
  for (const [ch, { t, v }] of Object.entries(packed)) {
    const pairs: [number, number | null][] = new Array(t.length);
    for (let i = 0; i < t.length; i++) pairs[i] = [t[i], Number.isNaN(v[i]) ? null : v[i]];
    out[ch] = pairs;
  }
  return out;
}

const store = {
  get(key: string) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key: string, value: string) { try { localStorage.setItem(key, value); } catch { /* private mode */ } },
  remove(key: string) { try { localStorage.removeItem(key); } catch { /* private mode */ } },
};

/** What the views use of the browser client, where `choose_folder`. */
export interface FolderPicking {
  chooseFolder(): Promise<WorkspaceManifest>;
  addFolderFiles(files: (File | { file: File; path: string })[]): Promise<WorkspaceManifest>;
  reconnectFolder(folder_id: string, files?: (File | { file: File; path: string })[]): Promise<FolderState>;
  folderState(folder_id: string): Promise<FolderState>;
  deleteAllData(): Promise<void>;
}

export class BrowserWorkerClient extends LocalServerClient implements FolderPicking {
  readonly folders = new PageFolders();
  private worker!: Worker;
  private ready!: Promise<void>;
  private markReady!: () => void;
  private pending = new Map<string, Pending>();
  private queue: Promise<unknown> = Promise.resolve();
  private seq = 1;
  private busy = 0;
  private scanProgress: ScanProgress = { active: false };
  private downloads = new Map<string, string>();
  private uploads = new Map<string, Pending>();
  private statusListeners = new Set<(s: EngineStatus) => void>();
  status: EngineStatus = { phase: "loading", step: "starting", done: 0, total: 4 };
  private restartNotice = false;
  private memoryWaits = new Map<number, Pending>();
  /** [log number, heap bytes] at each log analysed — Spec 04 §7's growth figure. */
  heapTrace: [number, number][] = [];

  private runtime: BrowserRuntime;
  private makeWorker: () => Worker;

  constructor(runtime: BrowserRuntime, makeWorker: () => Worker = defaultWorker) {
    super("");
    this.runtime = runtime;
    this.makeWorker = makeWorker;
    this.start();
    if (typeof window !== "undefined") {
      // §9.2: warn on navigate-away while an operation runs.
      window.addEventListener("beforeunload", (e) => {
        if (this.busy > 0) { e.preventDefault(); e.returnValue = "Analysis in progress"; }
      });
    }
  }

  onStatus(fn: (s: EngineStatus) => void): () => void {
    this.statusListeners.add(fn);
    fn(this.status);
    return () => this.statusListeners.delete(fn);
  }

  private setStatus(s: EngineStatus) {
    this.status = s;
    for (const fn of this.statusListeners) fn(s);
  }

  private start() {
    this.ready = new Promise((resolve) => { this.markReady = resolve; });
    this.worker = this.makeWorker();
    this.worker.onmessage = (ev) => this.onMessage(ev.data);
    this.worker.onerror = () => this.restart();
    const wheelUrl = new URL(this.runtime.engine_wheel, document.baseURI).href;
    const pyodideUrl = new URL(this.runtime.pyodide_url.replace(/\/?$/, "/"), document.baseURI).href;
    this.worker.postMessage({ type: "init", pyodideUrl, wheelUrl });
  }

  /** The worker died (out of memory, an uncaught error): start a new one;
   * the request in flight fails with HOST_RESTARTED, once. */
  private restart() {
    this.worker.terminate();
    const failed = [...this.pending.values()];
    this.pending.clear();
    for (const p of failed) {
      p.reject(new EngineRpcError("HOST_RESTARTED", this.restartNotice
        ? "The analysis engine restarted."
        : "The analysis engine stopped and was restarted. What you were doing didn't finish; try it again."));
    }
    this.restartNotice = true;
    this.busy = 0;
    this.scanProgress = { active: false };
    this.start();
  }

  private onMessage(msg: Record<string, any>) { // eslint-disable-line @typescript-eslint/no-explicit-any
    switch (msg.type) {
      case "loading":
        if (msg.phase !== "ready") this.setStatus({ phase: "loading", step: msg.phase, done: msg.done, total: msg.total });
        break;
      case "ready":
        this.setStatus({ phase: "ready", engineVersion: msg.engine_version, pyodideVersion: msg.pyodide_version,
                         registryPresent: msg.registry_present });
        this.markReady();
        break;
      case "failed":
        this.setStatus({ phase: "failed", message: msg.message });
        break;
      case "reply": {
        const p = this.pending.get(msg.request_id);
        this.pending.delete(msg.request_id);
        if (!p) break;
        const reply = msg.reply;
        if (!reply.ok) p.reject(new EngineRpcError(reply.error?.code ?? "UNKNOWN", reply.error?.message ?? "request failed"));
        else p.resolve(reply.packed === "series" ? unpackSeries(reply.result) : reply.result);
        break;
      }
      case "progress":
        if (msg.stream === "scan") {
          this.scanProgress = msg.update;
          if (msg.update.phase === "analyzing") this.heapTrace.push([msg.update.current, msg.heap]);
        }
        break;
      case "need-listing":
        this.folders.list(msg.folder_id).then(
          (listing) => this.worker.postMessage({ type: "listing", req: msg.req, listing }),
          () => this.worker.postMessage({ type: "listing", req: msg.req, listing: null }));
        break;
      case "need-file":
        this.folders.read(msg.folder_id, msg.relative_path).then(
          (bytes) => this.worker.postMessage({ type: "file", req: msg.req, bytes }, bytes ? [bytes] : []),
          () => this.worker.postMessage({ type: "file", req: msg.req, bytes: null }));
        break;
      case "deliver": {
        const url = URL.createObjectURL(new Blob([msg.bytes], { type: "application/zip" }));
        this.downloads.set(msg.token, url);
        break;
      }
      case "memory": {
        const p = this.memoryWaits.get(msg.req);
        this.memoryWaits.delete(msg.req);
        p?.resolve(msg.bytes);
        break;
      }
      case "uploaded": {
        const p = this.uploads.get(msg.upload_id);
        this.uploads.delete(msg.upload_id);
        p?.resolve({ upload_id: msg.upload_id, filename: msg.filename, size: msg.size });
        break;
      }
    }
  }

  /** One request at a time (§9.2: the worker is single-threaded), queued
   * until the engine is ready. */
  protected rpc<T>(op: string, params: unknown): Promise<T> {
    const run = async () => {
      await this.ready;
      const request_id = `b-${this.seq++}`;
      this.busy++;
      if (op === "scan_workspace") {
        this.scanProgress = { active: true, phase: "starting" };
        // Sync looks at the folders afresh (Spec 04 D12).
        this.folders.invalidate();
      }
      try {
        return await new Promise<T>((resolve, reject) => {
          this.pending.set(request_id, { resolve: resolve as (v: unknown) => void, reject });
          this.worker.postMessage({ type: "request", envelope: { op, request_id, params } });
        });
      } finally {
        this.busy--;
        if (op === "scan_workspace") this.scanProgress = { active: false };
      }
    };
    const next = this.queue.then(run, run);
    this.queue = next.catch(() => undefined);
    return next;
  }

  // Progress is answered here: the worker is busy with the operation
  // itself, and the views poll exactly as they poll the server.
  async getScanProgress(): Promise<ScanProgress> {
    return this.scanProgress;
  }

  async getDataLocationProgress(): Promise<DataLocationProgress> {
    return { active: false };
  }

  /** The engine worker's WebAssembly heap, in bytes (Spec 04 §7). */
  engineMemory(): Promise<number> {
    const req = this.seq++;
    return new Promise((resolve, reject) => {
      this.memoryWaits.set(req, { resolve: resolve as (v: unknown) => void, reject });
      this.worker.postMessage({ type: "memory", req });
    });
  }

  downloadUrl(token: string): string {
    return this.downloads.get(token) ?? token;
  }

  private async send(bytes: ArrayBuffer, filename: string): Promise<{ upload_id: string; filename: string; size: number }> {
    await this.ready;
    const upload_id = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      this.uploads.set(upload_id, { resolve: resolve as (v: unknown) => void, reject });
      this.worker.postMessage({ type: "upload", upload_id, filename, bytes }, [bytes]);
    });
  }

  private refuseIfTooLarge(size: number, filename: string) {
    if (size > MAX_LOG_BYTES) {
      throw new EngineRpcError("FILE_TOO_LARGE", `${filename} is ${Math.round(size / 1048576)} MB — larger than any engine log (the limit is 100 MB), so it wasn't read.`);
    }
  }

  async uploadFile(file: File) {
    return this.send(await file.arrayBuffer(), file.name);
  }

  async importFiles(files: UploadFile[], engine?: string) {
    const items = [];
    for (const f of files) {
      this.refuseIfTooLarge(f.content.byteLength, f.filename);
      items.push({ upload_id: (await this.send(f.content.slice(0), f.filename)).upload_id, filename: f.filename });
    }
    return this.rpc<Awaited<ReturnType<LocalServerClient["importFiles"]>>>("import_files", { files: items, engine });
  }

  async ingestLog(file: UploadFile) {
    this.refuseIfTooLarge(file.content.byteLength, file.filename);
    const up = await this.send(file.content.slice(0), file.filename);
    return this.rpc<Awaited<ReturnType<LocalServerClient["ingestLog"]>>>("ingest_log", { upload_id: up.upload_id, filename: file.filename });
  }

  async analyzeFlight(file: UploadFile, engine?: string) {
    this.refuseIfTooLarge(file.content.byteLength, file.filename);
    const up = await this.send(file.content.slice(0), file.filename);
    return this.rpc<Awaited<ReturnType<LocalServerClient["analyzeFlight"]>>>("analyze_flight", { upload_id: up.upload_id, filename: file.filename, engine });
  }

  async getSeries(file: UploadFile, channels: string[]) {
    this.refuseIfTooLarge(file.content.byteLength, file.filename);
    const up = await this.send(file.content.slice(0), file.filename);
    return this.rpc<SeriesResult>("get_series", { upload_id: up.upload_id, filename: file.filename, channels });
  }

  /** §9.2 / Spec 02 §9: ask for durable storage when the first workspace
   * is created, and set the eviction marker (§9.4). */
  async createWorkspace(name: string, engineModel: string, tailNumber?: string): Promise<WorkspaceManifest> {
    const manifest = await super.createWorkspace(name, engineModel, tailNumber);
    store.set(EVICTION_MARKER, new Date().toISOString());
    if (store.get(PERSIST_OUTCOME) == null && navigator.storage?.persist) {
      const granted = await navigator.storage.persist().catch(() => false);
      store.set(PERSIST_OUTCOME, granted ? "granted" : "denied");
    }
    return manifest;
  }

  // ── Folders the page holds (Spec 04 §9.3) ───────────────────────────────

  /** Chrome: Choose folder… (the OS picker). */
  async chooseFolder(): Promise<WorkspaceManifest> {
    const { folder_id, name } = await this.folders.choose();
    return this.rpc<WorkspaceManifest>("register_log_folder", { name, folder_id });
  }

  /** Safari, or a dropped folder: its files, for this session. */
  async addFolderFiles(files: (File | { file: File; path: string })[]): Promise<WorkspaceManifest> {
    const { folder_id, name } = this.folders.addFiles(files);
    return this.rpc<WorkspaceManifest>("register_log_folder", { name, folder_id });
  }

  /** Allow access (Chrome, after a restart) or Not connected — reconnect:
   * the same folder_id, so the workspace's flights stay matched. With
   * `files`, the folder as picked again (Safari); without, the browser's
   * permission prompt, or the picker if the folder was never kept here. */
  async reconnectFolder(folder_id: string, files?: (File | { file: File; path: string })[]): Promise<FolderState> {
    if (files) this.folders.addFiles(files, folder_id);
    else if ((await this.folders.state(folder_id)) === "needs_permission") await this.folders.allowAccess(folder_id);
    else await this.folders.choose(folder_id);
    return this.folders.state(folder_id);
  }

  folderState(folder_id: string): Promise<FolderState> {
    return this.folders.state(folder_id);
  }

  /** Settings → App → Delete all data on this device. */
  async deleteAllData(): Promise<void> {
    const workspaces = await this.listWorkspaces();
    for (const w of workspaces) await this.deleteWorkspace(w.id);
    await this.folders.forgetAll();
    store.remove(EVICTION_MARKER);
    store.remove(PERSIST_OUTCOME);
  }
}

function defaultWorker(): Worker {
  return new Worker(new URL("../worker/engine.worker.ts", import.meta.url), { type: "module" });
}
