import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetCapabilities } from "../lib/capabilities";
import { MOVE_URL, PROBE_URL, resetProbe } from "../lib/moveWorkspace";
import { MoveWorkspaceBanner } from "./MoveWorkspace";
import { NavShell } from "./NavShell";

// Spec 16 D17 — Move my workspace: on the website, when EIS answers on this
// computer, one button exports the workspace (no logs), posts it to the
// local server's move route and opens the local pages; the website's copy
// is then marked as the copy. On the local pages, a note to link the log
// folder and Sync. Synthetic data.

const state = vi.hoisted(() => ({ move: true, exports: [] as unknown[] }));

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const overrides: Record<string, unknown> = {
    getCapabilities: async () => ({ host: state.move ? "browser" : "server", engine_version: "1.0.2", host_version: "1.0.2",
      features: { research: true, investigations: true, bench: !state.move, move_workspace: state.move } }),
    getActiveWorkspace: async () => ({ active: true, manifest: { id: "ws-1", name: "My Sling", log_folders: [] } }),
    listWorkspaces: async () => [{ id: "ws-1", name: "My Sling", flight_count: 2, log_folder_count: 1 }],
    filterHealth: async () => ({ health: [], attention_count: 0 }),
    getFleet: async () => ({ shift_history: [] }),
    exportWorkspace: async (o: unknown) => { state.exports.push(o); return { filename: "My Sling.eisworkspace", download_url: "tok", size: 3 }; },
    downloadUrl: (t: string) => `blob:export-${t}`,
  };
  const client = new Proxy({}, { get: (_t, k: string) => overrides[k] ?? (async () => ({})) });
  return { ...actual, getEngineClient: () => client };
});

type Call = { url: string; init?: RequestInit };
let calls: Call[] = [];
let probeAnswers = true;
const assign = vi.fn();

beforeEach(() => {
  state.move = true;
  state.exports = [];
  calls = [];
  probeAnswers = true;
  resetProbe();
  resetCapabilities();
  window.localStorage.clear();
  window.sessionStorage.clear();
  assign.mockReset();
  Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, assign, search: "", pathname: "/", hash: "" } });
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (url === PROBE_URL) {
      if (!probeAnswers) throw new TypeError("Failed to fetch");
      return new Response(JSON.stringify({ app: "SlingologyEIS", move_workspace: true }));
    }
    if (url.startsWith("blob:")) return new Response("zip");
    if (url.startsWith(MOVE_URL)) {
      return new Response(JSON.stringify({ ok: true, result: { workspace_id: "ws-9", name: "My Sling (imported)", open_url: "http://127.0.0.1:8420/?moved=ws-9#/flights" } }));
    }
    throw new Error(`unexpected fetch ${url}`);
  }));
});

afterEach(() => vi.unstubAllGlobals());

describe("Move my workspace (D17)", () => {
  it("offers the move when EIS answers, exports without logs, posts it and opens the local pages", async () => {
    render(<MoveWorkspaceBanner />);
    const button = await screen.findByTestId("move-workspace-button");
    expect(button.textContent).toBe("Move my workspace to EIS on this computer");
    fireEvent.click(button);
    await waitFor(() => expect(screen.queryByTestId("move-error")?.textContent ?? assign.mock.calls[0]?.[0]).toBe("http://127.0.0.1:8420/?moved=ws-9#/flights"));
    expect(state.exports).toEqual([{ include_logs: false, anonymise: false }]);
    const post = calls.find((c) => c.url.startsWith(MOVE_URL))!;
    expect(post.url).toBe(`${MOVE_URL}?filename=My%20Sling.eisworkspace`);
    expect(post.init?.method).toBe("POST");
    expect(window.localStorage.getItem("slingology-eis.moved.ws-1")).toBeTruthy();
  });

  it("asks this computer once per visit, and shows nothing when EIS doesn't answer", async () => {
    probeAnswers = false;
    const { container } = render(<MoveWorkspaceBanner />);
    await waitFor(() => expect(calls.filter((c) => c.url === PROBE_URL)).toHaveLength(1));
    expect(container.textContent).toBe("");
    render(<MoveWorkspaceBanner />);
    await new Promise((r) => setTimeout(r, 20));
    expect(calls.filter((c) => c.url === PROBE_URL)).toHaveLength(1);
  });

  it("marks the website's workspace as the copy after the move", async () => {
    window.localStorage.setItem("slingology-eis.moved.ws-1", "2026-11-18T10:00:00Z");
    render(<MoveWorkspaceBanner />);
    expect((await screen.findByTestId("move-copy")).textContent).toContain("This is now the copy.");
    expect(screen.queryByTestId("move-workspace-button")).toBeNull();
  });

  it("is not offered by EIS on this computer itself", async () => {
    state.move = false;
    const { container } = render(<MoveWorkspaceBanner />);
    await new Promise((r) => setTimeout(r, 20));
    expect(container.textContent).toBe("");
    expect(calls).toHaveLength(0);
  });

  it("the local pages, just after the move: link the log folder and Sync", async () => {
    state.move = false;
    window.location.search = "?moved=ws-9";
    window.history.replaceState = vi.fn();
    render(<MemoryRouter><NavShell><div /></NavShell></MemoryRouter>);
    const note = await screen.findByTestId("moved-note");
    expect(note.textContent).toContain("Link your log folder on Flights and Sync");
    fireEvent.click(screen.getByLabelText("Dismiss"));
    expect(screen.queryByTestId("moved-note")).toBeNull();
  });
});
