// The browser host's log folders (Spec 04 v0.7 §9.3, Spec 02 §5.9). The
// page lists a folder and supplies a log's bytes when the engine asks;
// fingerprinting, admission and analysis stay the engine's.
//
// - Where the browser can keep a folder (File System Access: Chrome), the
//   FileSystemDirectoryHandle is persisted in IndexedDB under the
//   manifest's folder_id; on a later visit the page re-checks permission,
//   and when the browser wants a click, the folder row offers Allow access.
// - Elsewhere (Safari), a folder comes from <input webkitdirectory> or a
//   dropped folder and lasts for this session; afterwards the row shows
//   Not connected — reconnect.
//
// Capability by feature, never by user agent.

export const MAX_LOG_BYTES = 100 * 1024 * 1024; // D10: refuse before transfer

export interface ListingEntry {
  relative_path: string;
  size: number;
  last_modified: number; // seconds since the epoch
}

export type FolderState = "connected" | "needs_permission" | "not_connected";

export function canKeepFolders(): boolean {
  return typeof window !== "undefined" && "showDirectoryPicker" in window;
}

const isLog = (name: string) => name.toLowerCase().endsWith(".csv");

// ── The handle store (IndexedDB, keyed by folder_id) ──────────────────────

const DB = "slingology-eis-folders";
const STORE = "handles";

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idb<T>(mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest): Promise<T> {
  const db = await openDb();
  return new Promise((resolve, reject) => {
    const req = run(db.transaction(STORE, mode).objectStore(STORE));
    req.onsuccess = () => resolve(req.result as T);
    req.onerror = () => reject(req.error);
  });
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type DirHandle = any; // FileSystemDirectoryHandle with entries() / queryPermission

async function walk(dir: DirHandle, prefix: string, out: { entry: ListingEntry; get: () => Promise<File> }[]) {
  for await (const [name, h] of dir.entries()) {
    const rel = prefix ? `${prefix}/${name}` : name;
    if (h.kind === "directory") await walk(h, rel, out);
    else if (isLog(name)) {
      const f: File = await h.getFile();
      out.push({ entry: { relative_path: rel, size: f.size, last_modified: f.lastModified / 1000 }, get: () => h.getFile() });
    }
  }
}

export class PageFolders {
  private handles = new Map<string, DirHandle>();
  private sessionFiles = new Map<string, Map<string, File>>();
  private states = new Map<string, FolderState>();
  private readers = new Map<string, Map<string, () => Promise<File>>>();
  // Spec 04 D12: a folder is listed once per session, then again only
  // after invalidate() (Sync, Reconnect/Allow, a folder added) — never
  // because a page was opened. Concurrent requests share one walk.
  private listings = new Map<string, ListingEntry[] | null>();
  private walking = new Map<string, Promise<ListingEntry[] | null>>();

  /** Forget a folder's listing (or every folder's), so the next request walks it again. */
  invalidate(folder_id?: string) {
    if (folder_id === undefined) this.listings.clear();
    else this.listings.delete(folder_id);
  }
  /** Logs refused for size (D10), named for the page to tell the pilot. */
  refused: { folder_id: string; relative_path: string; size: number }[] = [];
  onChange: () => void = () => {};

  /** Chrome: the OS folder picker; the handle is kept for later visits.
   * `folder_id` reconnects a folder already in the workspace. */
  async choose(folder_id: string = crypto.randomUUID()): Promise<{ folder_id: string; name: string }> {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const handle: DirHandle = await (window as any).showDirectoryPicker({ mode: "read" });
    this.invalidate(folder_id);
    this.handles.set(folder_id, handle);
    await idb("readwrite", (s) => s.put(handle, folder_id));
    this.states.set(folder_id, "connected");
    return { folder_id, name: handle.name };
  }

  /** A folder's files from <input webkitdirectory> or a dropped folder
   * (this session only). `folder_id` reconnects a folder already in the
   * workspace. */
  addFiles(files: (File | { file: File; path: string })[], folder_id: string = crypto.randomUUID()): { folder_id: string; name: string } {
    const map = new Map<string, File>();
    let name = "Logs";
    for (const item of files) {
      const f = item instanceof File ? item : item.file;
      const path = item instanceof File ? ((f as File & { webkitRelativePath?: string }).webkitRelativePath || f.name) : item.path;
      const parts = path.split("/");
      if (parts.length > 1) name = parts[0];
      const rel = parts.length > 1 ? parts.slice(1).join("/") : parts[0];
      if (isLog(rel)) map.set(rel, f);
    }
    this.sessionFiles.set(folder_id, map);
    this.invalidate(folder_id);
    this.states.set(folder_id, "connected");
    this.onChange();
    return { folder_id, name };
  }

  /** Whether this page can supply a folder now. */
  async state(folder_id: string): Promise<FolderState> {
    if (this.sessionFiles.has(folder_id)) return "connected";
    const handle = await this.handle(folder_id);
    if (!handle) return "not_connected";
    const perm = handle.queryPermission ? await handle.queryPermission({ mode: "read" }) : "granted";
    const s: FolderState = perm === "granted" ? "connected" : "needs_permission";
    this.states.set(folder_id, s);
    return s;
  }

  /** Chrome, after a restart: the one click the browser asks for. */
  async allowAccess(folder_id: string): Promise<boolean> {
    const handle = await this.handle(folder_id);
    if (!handle) return false;
    const perm = await handle.requestPermission({ mode: "read" });
    this.invalidate(folder_id);
    this.states.set(folder_id, perm === "granted" ? "connected" : "needs_permission");
    this.onChange();
    return perm === "granted";
  }

  async forget(folder_id: string): Promise<void> {
    this.handles.delete(folder_id);
    this.sessionFiles.delete(folder_id);
    await idb("readwrite", (s) => s.delete(folder_id)).catch(() => undefined);
  }

  async forgetAll(): Promise<void> {
    this.handles.clear();
    this.sessionFiles.clear();
    await idb("readwrite", (s) => s.clear()).catch(() => undefined);
  }

  /** The engine's listing request: null when this page can't reach it.
   * One walk per folder per event (see invalidate). */
  async list(folder_id: string): Promise<ListingEntry[] | null> {
    if (this.listings.has(folder_id)) return this.listings.get(folder_id)!;
    const running = this.walking.get(folder_id);
    if (running) return running;
    const walk = this.walkFolder(folder_id).finally(() => this.walking.delete(folder_id));
    this.walking.set(folder_id, walk);
    const listing = await walk;
    this.listings.set(folder_id, listing);
    return listing;
  }

  private async walkFolder(folder_id: string): Promise<ListingEntry[] | null> {
    const found: { entry: ListingEntry; get: () => Promise<File> }[] = [];
    const files = this.sessionFiles.get(folder_id);
    if (files) {
      for (const [rel, f] of files) found.push({ entry: { relative_path: rel, size: f.size, last_modified: f.lastModified / 1000 }, get: async () => f });
    } else {
      if ((await this.state(folder_id)) !== "connected") return null;
      try {
        await walk(await this.handle(folder_id), "", found);
      } catch {
        this.states.set(folder_id, "not_connected");
        return null;
      }
    }
    const keep = new Map<string, () => Promise<File>>();
    const listing: ListingEntry[] = [];
    for (const { entry, get } of found) {
      if (keep.has(entry.relative_path)) continue;   // one entry per file, whatever the walk reported
      if (entry.size > MAX_LOG_BYTES) {
        this.refused.push({ folder_id, relative_path: entry.relative_path, size: entry.size });
        continue;
      }
      keep.set(entry.relative_path, get);
      listing.push(entry);
    }
    this.readers.set(folder_id, keep);
    if (this.refused.length) this.onChange();
    return listing;
  }

  /** The engine's file request: the bytes, or null (an "unavailable" answer). */
  async read(folder_id: string, relative_path: string): Promise<ArrayBuffer | null> {
    let get = this.readers.get(folder_id)?.get(relative_path);
    if (!get && !this.listings.has(folder_id)) {
      await this.list(folder_id);
      get = this.readers.get(folder_id)?.get(relative_path);
    }
    if (!get) return null;
    try {
      const f = await get();
      if (f.size > MAX_LOG_BYTES) return null;
      return await f.arrayBuffer();
    } catch {
      return null;
    }
  }

  private async handle(folder_id: string): Promise<DirHandle | null> {
    if (this.handles.has(folder_id)) return this.handles.get(folder_id);
    if (!canKeepFolders()) return null;
    const h = await idb<DirHandle>("readonly", (s) => s.get(folder_id)).catch(() => undefined);
    if (h) this.handles.set(folder_id, h);
    return h ?? null;
  }
}

// ── A dropped folder (both browsers: webkitGetAsEntry) ─────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Entry = any; // FileSystemEntry

function readAll(reader: Entry): Promise<Entry[]> {
  return new Promise((resolve, reject) => {
    const out: Entry[] = [];
    const next = () => reader.readEntries((batch: Entry[]) => {
      if (!batch.length) resolve(out);
      else { out.push(...batch); next(); }
    }, reject);
    next();
  });
}

async function collect(entry: Entry, prefix: string, out: { file: File; path: string }[]) {
  if (entry.isFile) {
    const file: File = await new Promise((resolve, reject) => entry.file(resolve, reject));
    out.push({ file, path: `${prefix}${entry.name}` });
  } else if (entry.isDirectory) {
    for (const child of await readAll(entry.createReader())) await collect(child, `${prefix}${entry.name}/`, out);
  }
}

/** The folders in a drop, each as {path, file} pairs whose paths start
 * with the folder's name — the shape addFiles takes. Empty when nothing
 * dropped is a folder. */
export async function droppedFolders(dt: DataTransfer): Promise<{ file: File; path: string }[][]> {
  const entries = Array.from(dt.items ?? [])
    .map((i) => (i as DataTransferItem & { webkitGetAsEntry?: () => Entry }).webkitGetAsEntry?.())
    .filter((e) => e && e.isDirectory);
  const folders = [];
  for (const e of entries) {
    const files: { file: File; path: string }[] = [];
    await collect(e, "", files);
    folders.push(files);
  }
  return folders;
}
