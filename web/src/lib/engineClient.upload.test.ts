import { describe, it, expect, vi, afterEach } from "vitest";
import { LocalServerClient } from "./engineClient";

// An upload to a server started before the page was updated (no /upload)
// says to restart it, instead of the browser's bare "Failed to fetch".

const file = new File(["x"], "N117ZS.zip");
const ok = (result: unknown) => new Response(JSON.stringify({ ok: true, result }), { status: 200 });

afterEach(() => vi.unstubAllGlobals());

describe("LocalServerClient.uploadFile", () => {
  it("a dropped upload with the server still answering: restart it", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url.includes("/upload")) throw new TypeError("Failed to fetch");
      return ok([]);
    }));
    await expect(new LocalServerClient("http://x").uploadFile(file)).rejects.toMatchObject({ code: "SERVER_OUTDATED" });
  });

  it("a 404 from an older server: restart it", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 404 })));
    await expect(new LocalServerClient("http://x").uploadFile(file)).rejects.toMatchObject({ code: "SERVER_OUTDATED" });
  });

  it("no server at all: says it can't be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    await expect(new LocalServerClient("http://x").uploadFile(file)).rejects.toMatchObject({ code: "SERVER_UNREACHABLE" });
  });

  it("a current server: the upload id", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ok({ upload_id: "u1", filename: "N117ZS.zip", size: 1 })));
    expect((await new LocalServerClient("http://x").uploadFile(file)).upload_id).toBe("u1");
  });
});
