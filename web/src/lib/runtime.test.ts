import { afterEach, describe, it, expect, vi } from "vitest";
import { __loadRuntimeForTest as loadRuntime } from "./engineClient";

// Spec 04 §10 step 6: runtime.json resolved against the app's base, tried
// once more after a failure, and the URL tried named in the message.

const json = (body: unknown) => ({ ok: true, status: 200, json: async () => body });
const missing = { ok: false, status: 404, json: async () => ({}) };

describe("loadRuntime", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("retries once after a 404 and takes the second answer", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(missing).mockResolvedValueOnce(json({ host: "server" }));
    vi.stubGlobal("fetch", fetch);
    expect(await loadRuntime(0)).toEqual({ host: "server" });
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(String(fetch.mock.calls[0][0])).toBe(new URL("/runtime.json", window.location.href).href);
  });

  it("names the URL it tried when both attempts fail", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(missing));
    const r = await loadRuntime(0);
    expect(r).toMatchObject({ host: "incomplete" });
    expect((r as { message: string }).message).toContain("/runtime.json: HTTP 404");
    expect((r as { message: string }).message).toMatch(/^http/);
  });

  it("does not retry a file it read but doesn't understand", async () => {
    const fetch = vi.fn().mockResolvedValue(json({ host: "mainframe" }));
    vi.stubGlobal("fetch", fetch);
    expect(await loadRuntime(0)).toMatchObject({ host: "incomplete" });
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
