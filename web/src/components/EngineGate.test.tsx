import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Spec 03 v0.24 §6.3, Spec 04 v0.7 §9.4–§9.5: what shows before the app.

type Status = Record<string, unknown>;
const state = vi.hoisted(() => ({ runtime: null as unknown, status: null as Status | null }));

vi.mock("../lib/engineClient", () => ({
  getRuntime: async () => ({
    runtime: state.runtime,
    client: { onStatus: (fn: (s: Status) => void) => { if (state.status) fn(state.status); return () => {}; } },
  }),
}));

import { EngineGate } from "./EngineGate";
import { EVICTION_MARKER } from "../lib/hostState";

const BROWSER = { host: "browser", pyodide: "0.28.0", pyodide_url: "pyodide/", engine_wheel: "engine/x.whl" };

describe("EngineGate", () => {
  beforeEach(() => localStorage.clear());

  it("shows the engine loading on a slow first start, with the once-only wording", async () => {
    state.runtime = BROWSER;
    state.status = { phase: "loading", step: "numpy and pandas", done: 1, total: 4 };
    render(<EngineGate><div>app</div></EngineGate>);
    const loading = await screen.findByTestId("engine-loading", {}, { timeout: 2000 });
    expect(loading.textContent).toContain("Downloading the analysis engine… (about 30 MB, once)");
    expect(screen.queryByText("app")).toBeNull();
  });

  it("a later visit served by the offline cache says it loads from this device", async () => {
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { controller: {} } });
    try {
      state.runtime = BROWSER;
      state.status = { phase: "loading", step: "numpy and pandas", done: 1, total: 4 };
      render(<EngineGate><div>app</div></EngineGate>);
      const loading = await screen.findByTestId("engine-loading", {}, { timeout: 2000 });
      expect(loading.textContent).toContain("Loading the analysis engine from this device");
      expect(loading.textContent).not.toContain("Downloading");
    } finally {
      delete (navigator as unknown as { serviceWorker?: unknown }).serviceWorker;
    }
  });

  it("after a switch to a new release, says so once", async () => {
    let release = "aaaa1111";
    vi.stubGlobal("caches", { match: async () => new Response(JSON.stringify({ release, version: "1.0.2" })) });
    try {
      localStorage.setItem("slingology-eis-site-release", JSON.stringify({ release: "old0000", version: "1.0.1" }));
      state.runtime = BROWSER;
      state.status = { phase: "ready", engineVersion: "1.0.2", pyodideVersion: "0.28.0", registryPresent: true };
      const { unmount } = render(<EngineGate><div>app</div></EngineGate>);
      expect((await screen.findByTestId("update-notice")).textContent).toContain("Updated to version 1.0.2");
      unmount();
      render(<EngineGate><div>app</div></EngineGate>);             // the next load: nothing new
      await screen.findByText("app");
      await new Promise((r) => setTimeout(r, 50));
      expect(screen.queryByTestId("update-notice")).toBeNull();
      release = "aaaa1111";
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("a first visit's cache is recorded silently, not announced", async () => {
    vi.stubGlobal("caches", { match: async () => new Response(JSON.stringify({ release: "r1", version: "1.0.1" })) });
    try {
      state.runtime = BROWSER;
      state.status = { phase: "ready", engineVersion: "1.0.1", pyodideVersion: "0.28.0", registryPresent: true };
      render(<EngineGate><div>app</div></EngineGate>);
      await screen.findByText("app");
      await new Promise((r) => setTimeout(r, 50));
      expect(screen.queryByTestId("update-notice")).toBeNull();
      expect(localStorage.getItem("slingology-eis-site-release")).toContain("r1");
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("says the installation is incomplete when runtime.json is missing", async () => {
    state.runtime = { host: "incomplete", message: "runtime.json: HTTP 404" };
    render(<EngineGate><div>app</div></EngineGate>);
    expect((await screen.findByTestId("installation-incomplete")).textContent).toContain("HTTP 404");
  });

  it("tells the pilot when the browser cleared the data a workspace was created in", async () => {
    localStorage.setItem(EVICTION_MARKER, "2026-10-19");
    state.runtime = BROWSER;
    state.status = { phase: "ready", engineVersion: "1.0.1", pyodideVersion: "0.28.0", registryPresent: false };
    render(<EngineGate><div>app</div></EngineGate>);
    expect((await screen.findByTestId("data-gone")).textContent).toContain("isn't on this device any more");
    expect(screen.getByRole("button", { name: "Import a workspace" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add your log folders" })).toBeTruthy();
  });

  it("a first run (no marker) and a ready engine: the app", async () => {
    state.runtime = BROWSER;
    state.status = { phase: "ready", engineVersion: "1.0.1", pyodideVersion: "0.28.0", registryPresent: false };
    render(<EngineGate><div>app</div></EngineGate>);
    expect(await screen.findByText("app")).toBeTruthy();
  });

  it("the server host: the app, no gate", async () => {
    state.runtime = { host: "server" };
    state.status = null;
    render(<EngineGate><div>app</div></EngineGate>);
    expect(await screen.findByText("app")).toBeTruthy();
  });
});
