import { describe, it, expect, beforeEach } from "vitest";
import { BrowserWorkerClient } from "./browserClient";
import { EngineRpcError } from "./engineClient";

// Spec 04 v0.7 §9.2: the browser host's client over a fake engine worker.

type Msg = Record<string, unknown>;

class FakeWorker {
  sent: Msg[] = [];
  onmessage: ((ev: { data: Msg }) => void) | null = null;
  onerror: (() => void) | null = null;
  terminated = false;
  postMessage(msg: Msg) { this.sent.push(msg); }
  terminate() { this.terminated = true; }
  reply(data: Msg) { this.onmessage?.({ data }); }
  requests() { return this.sent.filter((m) => m.type === "request").map((m) => m.envelope as { op: string; request_id: string; params: unknown }); }
}

const RUNTIME = { host: "browser" as const, pyodide: "0.28.0", pyodide_url: "pyodide/", engine_wheel: "engine/x.whl" };
const tick = () => new Promise((r) => setTimeout(r, 0));

let workers: FakeWorker[];
function make() {
  workers = [];
  const client = new BrowserWorkerClient(RUNTIME, () => {
    const w = new FakeWorker();
    workers.push(w);
    return w as unknown as Worker;
  });
  return client;
}
const ready = (w: FakeWorker) => w.reply({ type: "ready", engine_version: "1.0.1", pyodide_version: "0.28.0", registry_present: true });

describe("BrowserWorkerClient", () => {
  beforeEach(() => localStorage.clear());

  it("starts the worker with the site's own Pyodide and wheel, and queues requests until ready", async () => {
    const client = make();
    const w = workers[0];
    expect(w.sent[0]).toMatchObject({ type: "init" });
    expect(String(w.sent[0].wheelUrl)).toMatch(/engine\/x\.whl$/);
    // Same site as the page — never a CDN (Spec 04 §9.7).
    expect(new URL(String(w.sent[0].pyodideUrl)).origin).toBe(window.location.origin);
    expect(String(w.sent[0].pyodideUrl)).toMatch(/\/pyodide\/$/);
    const caps = client.getCapabilities();
    await tick();
    expect(w.requests()).toHaveLength(0);                        // not ready yet
    ready(w);
    await tick();
    const [req] = w.requests();
    expect(req.op).toBe("get_capabilities");
    w.reply({ type: "reply", request_id: req.request_id, reply: { ok: true, result: { host: "browser" } } });
    expect(await caps).toEqual({ host: "browser" });
  });

  it("sends one request at a time, in order", async () => {
    const client = make();
    const w = workers[0];
    ready(w);
    const a = client.listWorkspaces();
    const b = client.getActiveWorkspace();
    await tick();
    expect(w.requests().map((r) => r.op)).toEqual(["list_workspaces"]);
    w.reply({ type: "reply", request_id: w.requests()[0].request_id, reply: { ok: true, result: [] } });
    await a;
    await tick();
    expect(w.requests().map((r) => r.op)).toEqual(["list_workspaces", "get_active_workspace"]);
    w.reply({ type: "reply", request_id: w.requests()[1].request_id, reply: { ok: false, error: { code: "NO_ACTIVE_WORKSPACE", message: "none" } } });
    await expect(b).rejects.toMatchObject({ code: "NO_ACTIVE_WORKSPACE" });
  });

  it("answers scan progress from the worker's progress messages, as the views poll it", async () => {
    const client = make();
    const w = workers[0];
    ready(w);
    const scan = client.scanWorkspace();
    await tick();
    expect(await client.getScanProgress()).toEqual({ active: true, phase: "starting" });
    const { request_id } = w.requests()[0];
    w.reply({ type: "progress", request_id, stream: "scan", heap: 1, update: { active: true, phase: "analyzing", current: 3, total: 9, filename: "a.csv" } });
    expect(await client.getScanProgress()).toEqual({ active: true, phase: "analyzing", current: 3, total: 9, filename: "a.csv" });
    w.reply({ type: "reply", request_id, reply: { ok: true, result: { new_flight_ids: [] } } });
    await scan;
    expect(await client.getScanProgress()).toEqual({ active: false });
  });

  it("answers the worker's listing and file requests from the page's folders", async () => {
    const client = make();
    const w = workers[0];
    ready(w);
    const file = new File(["Date,Time\n"], "log_20260101_120000_TEST.csv");
    Object.defineProperty(file, "webkitRelativePath", { value: "logs/log_20260101_120000_TEST.csv" });
    const { folder_id } = client.folders.addFiles([file]);
    w.reply({ type: "need-listing", request_id: "b-1", req: 7, folder_id });
    await tick(); await tick();
    const listing = w.sent.find((m) => m.type === "listing") as { req: number; listing: { relative_path: string }[] };
    expect(listing.req).toBe(7);
    expect(listing.listing.map((e) => e.relative_path)).toEqual(["log_20260101_120000_TEST.csv"]);
    w.reply({ type: "need-file", request_id: "b-1", req: 8, folder_id, relative_path: "log_20260101_120000_TEST.csv" });
    await new Promise((r) => setTimeout(r, 20));
    const sent = w.sent.find((m) => m.type === "file") as { req: number; bytes: ArrayBuffer };
    expect(sent.req).toBe(8);
    expect(new TextDecoder().decode(sent.bytes)).toBe("Date,Time\n");
    w.reply({ type: "need-file", request_id: "b-1", req: 9, folder_id: "nope", relative_path: "x.csv" });
    await new Promise((r) => setTimeout(r, 20));
    expect((w.sent.find((m) => m.type === "file" && m.req === 9) as { bytes: unknown }).bytes).toBeNull();   // unavailable
  });

  it("restarts a worker that died; the request in flight fails with HOST_RESTARTED, once", async () => {
    const client = make();
    const w = workers[0];
    ready(w);
    const pending = client.listWorkspaces();
    await tick();
    w.onerror?.();
    const err = await pending.catch((e) => e);
    expect(err).toBeInstanceOf(EngineRpcError);
    expect(err.code).toBe("HOST_RESTARTED");
    expect(w.terminated).toBe(true);
    expect(workers).toHaveLength(2);                              // a new engine
    const w2 = workers[1];
    expect(w2.sent[0]).toMatchObject({ type: "init" });
    ready(w2);
    const next = client.listWorkspaces();
    await tick();
    w2.reply({ type: "reply", request_id: w2.requests()[0].request_id, reply: { ok: true, result: [] } });
    expect(await next).toEqual([]);
  });

  it("turns typed-array series back into [t, value|null] pairs", async () => {
    const client = make();
    const w = workers[0];
    ready(w);
    const series = client.getFlightSeries("f1", ["rpm"]);
    await tick();
    w.reply({ type: "reply", request_id: w.requests()[0].request_id,
              reply: { ok: true, packed: "series", result: { rpm: { t: new Float64Array([0, 1]), v: new Float64Array([5000, NaN]) } } } });
    expect(await series).toEqual({ rpm: [[0, 5000], [1, null]] });
  });

  it("refuses a log over 100 MB before transferring it", async () => {
    const client = make();
    ready(workers[0]);
    const big = { content: new ArrayBuffer(101 * 1024 * 1024), filename: "huge.csv" };
    await expect(client.importFiles([big])).rejects.toMatchObject({ code: "FILE_TOO_LARGE" });
    expect(workers[0].sent.some((m) => m.type === "upload")).toBe(false);
  });

  it("serves a delivered export as a download URL", async () => {
    const client = make();
    const w = workers[0];
    ready(w);
    w.reply({ type: "deliver", request_id: "b-1", token: "delivered:1", filename: "W.zip", bytes: new ArrayBuffer(3) });
    expect(client.downloadUrl("delivered:1")).toMatch(/^blob:/);
  });
});
