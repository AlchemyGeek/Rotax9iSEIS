import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { resetCapabilities } from "../lib/capabilities";
import { NewWorkspaceChoices } from "./NewWorkspace";

// Spec 16 D18 — three ways to start a workspace, side by side: Create from
// logs, Import a workspace, Load from a folder. On this computer the folder
// is linked by path; in a browser, by the folder picker (kept, or for this
// visit), and where a browser has none, the choice says so and offers
// files. Synthetic data.

const state = vi.hoisted(() => ({ host: "server" as "server" | "browser", calls: [] as string[] }));
const reset = vi.hoisted(() => vi.fn());

vi.mock("../lib/appReset", () => ({ resetApp: reset }));
vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const browser = () => state.host === "browser";
  const rec = (s: string) => { state.calls.push(s); };
  const client = {
    getCapabilities: async () => ({ host: state.host, engine_version: "1.0.2", host_version: "1.0.2",
      features: { add_folder_by_path: !browser(), choose_folder: browser(), move_workspace: browser(), research: true, investigations: true } }),
    createWorkspace: async (name: string, engine: string, tail?: string) => { rec(`create ${name} ${engine} ${tail ?? "-"}`); return {}; },
    addLogFolder: async (path: string) => { rec(`folder ${path}`); return {}; },
    pickFolder: async () => { rec("pick"); return { folder_id: "f1", name: "Logs 2026" }; },
    registerPickedFolder: async (p: { name: string }) => { rec(`register ${p.name}`); return {}; },
    addFolderFiles: async (files: File[]) => { rec(`files ${files.length}`); return {}; },
  };
  return { ...actual, getEngineClient: () => client };
});

const reload = vi.fn();
let pickerDescriptor: PropertyDescriptor | undefined;

function setBrowser(kind: "keeps" | "input" | "none") {
  state.host = "browser";
  if (kind === "keeps") (window as unknown as Record<string, unknown>).showDirectoryPicker = () => undefined;
  if (kind === "input") Object.defineProperty(HTMLInputElement.prototype, "webkitdirectory", { configurable: true, get: () => false, set: () => undefined });
}

beforeEach(() => {
  state.host = "server";
  state.calls = [];
  reset.mockReset();
  reload.mockReset();
  resetCapabilities();
  pickerDescriptor = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "webkitdirectory");
  Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, reload, hash: "" } });
});

afterEach(() => {
  delete (window as unknown as Record<string, unknown>).showDirectoryPicker;
  if (pickerDescriptor) Object.defineProperty(HTMLInputElement.prototype, "webkitdirectory", pickerDescriptor);
  else delete (HTMLInputElement.prototype as unknown as Record<string, unknown>).webkitdirectory;
});

describe("three ways to start a workspace (D18)", () => {
  it("shows the three side by side, with the first-run line pointing to the website", async () => {
    render(<NewWorkspaceChoices first onImport={() => undefined} />);
    await screen.findByText("Your first workspace");
    for (const t of ["Create from logs", "Import a workspace", "Load from a folder"]) expect(screen.getByText(t)).toBeTruthy();
    expect((await screen.findByTestId("move-mirror")).textContent).toContain("Been using the website? Open it and press Move my workspace.");
  });

  it("Create from logs needs a name, then creates and opens Flights", async () => {
    render(<NewWorkspaceChoices onImport={() => undefined} />);
    fireEvent.click(await screen.findByTestId("new-ws-create"));
    expect((await screen.findByTestId("new-ws-error")).textContent).toContain("Give the workspace a name");
    fireEvent.change(screen.getByLabelText("Workspace name"), { target: { value: "N117ZS" } });
    fireEvent.change(screen.getByLabelText("Tail number"), { target: { value: "N117ZS" } });
    fireEvent.click(screen.getByTestId("new-ws-create"));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(state.calls).toEqual(["create N117ZS 916iS N117ZS"]);
    expect(window.location.hash).toBe("#/flights");
  });

  it("Import a workspace hands over to the import dialog", async () => {
    const onImport = vi.fn();
    render(<NewWorkspaceChoices onImport={onImport} />);
    fireEvent.click(await screen.findByTestId("new-ws-import"));
    expect(onImport).toHaveBeenCalled();
  });

  it("on this computer, Load from a folder links the folder by path (named after it)", async () => {
    render(<NewWorkspaceChoices onImport={() => undefined} />);
    fireEvent.change(await screen.findByTestId("new-ws-folder-path"), { target: { value: "/Users/me/Logs/N117ZS/" } });
    fireEvent.click(screen.getByTestId("new-ws-folder"));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(state.calls).toEqual(["create N117ZS 916iS -", "folder /Users/me/Logs/N117ZS/"]);
  });

  it("in a browser that keeps folders, the folder is picked first, then the workspace made and the folder kept", async () => {
    setBrowser("keeps");
    render(<NewWorkspaceChoices onImport={() => undefined} />);
    await waitFor(() => expect(screen.getByTestId("new-ws-folder").textContent).toBe("Choose folder…"));
    expect(screen.queryByTestId("move-mirror")).toBeNull();
    fireEvent.click(screen.getByTestId("new-ws-folder"));
    await waitFor(() => expect(reset).toHaveBeenCalled());
    expect(state.calls).toEqual(["pick", "create Logs 2026 916iS -", "register Logs 2026"]);
    expect(reload).not.toHaveBeenCalled();     // the page keeps what it picked
  });

  it("in a browser with only a folder input, the folder's files are read for this visit", async () => {
    setBrowser("input");
    render(<NewWorkspaceChoices onImport={() => undefined} />);
    await screen.findByText(/opens the folder for this visit/);
    const a = new File(["x"], "a.csv"), b = new File(["y"], "b.csv");
    for (const f of [a, b]) Object.defineProperty(f, "webkitRelativePath", { value: `Logs/${f.name}` });
    fireEvent.change(screen.getByTestId("new-ws-folder-input"), { target: { files: [a, b] } });
    await waitFor(() => expect(reset).toHaveBeenCalled());
    expect(state.calls).toEqual(["create Logs 916iS -", "files 2"]);
  });

  it("in a browser that can't open a folder, the choice says so and offers files", async () => {
    setBrowser("none");
    render(<NewWorkspaceChoices onImport={() => undefined} />);
    expect((await screen.findByTestId("new-ws-no-folder")).textContent).toContain("This browser can't open a folder");
    fireEvent.change(screen.getByLabelText("Workspace name"), { target: { value: "N117ZS" } });
    fireEvent.click(screen.getByTestId("new-ws-folder-files"));
    await waitFor(() => expect(reload).toHaveBeenCalled());
    expect(state.calls).toEqual(["create N117ZS 916iS -"]);
  });
});
