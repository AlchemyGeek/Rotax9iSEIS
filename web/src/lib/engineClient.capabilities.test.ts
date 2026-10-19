import { describe, it, expect, vi, afterEach } from "vitest";
import { LocalServerClient } from "./engineClient";

// Spec 04 v0.4 §9.5: get_capabilities, over the same envelope as every op.

afterEach(() => vi.unstubAllGlobals());

describe("LocalServerClient.getCapabilities", () => {
  it("sends get_capabilities and returns the host's answer", async () => {
    const caps = {
      host: "server", engine_version: "1.0.1", host_version: "1.0.1",
      features: { data_location: true, add_folder_by_path: true, choose_folder: false,
        persistent_storage_status: false, download_url: true, folder_watching: false },
    };
    const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true, result: caps }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    expect(await new LocalServerClient("http://x").getCapabilities()).toEqual(caps);
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(JSON.parse(String(init.body)).op).toBe("get_capabilities");
  });
});
