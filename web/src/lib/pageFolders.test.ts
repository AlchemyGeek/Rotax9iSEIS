import { describe, it, expect } from "vitest";
import { PageFolders } from "./pageFolders";

// Spec 04 v0.8 D12 and step 4's acceptance (A1): after Allow access, one
// folder yields one listing per event — Sync, Reconnect/Allow, a folder
// added — and opening pages doesn't list it again.

function fakeHandle(names: string[], opts: { duplicate?: boolean } = {}) {
  let granted = false;
  const h = {
    walks: 0,
    async queryPermission() { return granted ? "granted" : "prompt"; },
    async requestPermission() { granted = true; return "granted"; },
    async *entries() {
      h.walks++;
      const list = opts.duplicate ? [...names, names[0]] : names;
      for (const n of list) {
        yield [n, { kind: "file", getFile: async () => new File(["x"], n) }];
      }
    },
  };
  return h;
}

function folders(handle: ReturnType<typeof fakeHandle>) {
  const f = new PageFolders();
  (f as unknown as { handles: Map<string, unknown> }).handles.set("f1", handle);
  return f;
}

describe("PageFolders listing", () => {
  it("after Allow access: one walk, shared by concurrent requests; none on later page loads", async () => {
    const h = fakeHandle(["a.csv", "b.CSV", "notes.txt"]);
    const f = folders(h);
    expect(await f.state("f1")).toBe("needs_permission");
    expect(await f.list("f1")).toBeNull();              // no access yet: nothing walked
    expect(h.walks).toBe(0);

    await f.allowAccess("f1");                           // the one click after a browser restart
    const [x, y] = await Promise.all([f.list("f1"), f.list("f1")]);   // e.g. Flights' two calls
    expect(h.walks).toBe(1);
    expect(x).toEqual(y);
    expect(x!.map((e) => e.relative_path)).toEqual(["a.csv", "b.CSV"]);

    await f.list("f1");                                  // navigating back to Flights
    expect(h.walks).toBe(1);

    f.invalidate();                                      // Sync
    await f.list("f1");
    expect(h.walks).toBe(2);
  });

  it("a walk that reports a file twice still lists it once", async () => {
    const h = fakeHandle(["a.csv", "b.csv"], { duplicate: true });
    const f = folders(h);
    await f.allowAccess("f1");
    expect((await f.list("f1"))!.map((e) => e.relative_path)).toEqual(["a.csv", "b.csv"]);
  });

  it("adding a folder's files lists it afresh", async () => {
    const f = new PageFolders();
    const file = new File(["x"], "a.csv");
    Object.defineProperty(file, "webkitRelativePath", { value: "Logs/a.csv" });
    const { folder_id } = f.addFiles([file]);
    expect((await f.list(folder_id))!.length).toBe(1);
    const more = new File(["y"], "b.csv");
    Object.defineProperty(more, "webkitRelativePath", { value: "Logs/b.csv" });
    f.addFiles([file, more], folder_id);                 // reconnect with the folder as it is now
    expect((await f.list(folder_id))!.length).toBe(2);
  });
});
