// Spec 16 D17 — Move my workspace: the website's workspace, exported in
// this page (browser storage belongs to the website's origin, so only the
// page can read it) and posted to EIS running on this computer.
import { getEngineClient } from "./engineClient";

// The extension and `slingology-eis serve` listen on 8420. A walkthrough
// against a throwaway server sets another address in this origin's
// storage (slingology-eis.local-eis).
function localEis(): string {
  try {
    const o = window.localStorage.getItem("slingology-eis.local-eis");
    if (o && /^http:\/\/127\.0\.0\.1:\d+$/.test(o)) return o;
  } catch {
    // no storage: the default
  }
  return "http://127.0.0.1:8420";
}
export const LOCAL_EIS = localEis();
export const PROBE_URL = `${LOCAL_EIS}/eis/probe`;
export const MOVE_URL = `${LOCAL_EIS}/eis/move-workspace`;

let probe: Promise<boolean> | null = null;

/** Is EIS running on this computer? Asked once per visit (page load). */
export function probeLocalEis(): Promise<boolean> {
  if (!probe) {
    probe = (async () => {
      try {
        const init: RequestInit & { targetAddressSpace?: string } = {
          mode: "cors",
          // Chrome's Local Network Access: this request is meant for this machine.
          targetAddressSpace: "loopback",
          signal: AbortSignal.timeout ? AbortSignal.timeout(2500) : undefined,
        };
        const res = await fetch(PROBE_URL, init);
        if (!res.ok) return false;
        const body = await res.json();
        return body?.move_workspace === true;
      } catch {
        return false;
      }
    })();
  }
  return probe;
}

/** For tests: forget the cached probe. */
export function resetProbe() {
  probe = null;
}

const MARK = (workspaceId: string) => `slingology-eis.moved.${workspaceId}`;

/** When this browser workspace was moved (it is now the copy), or null. */
export function movedAt(workspaceId: string): string | null {
  try {
    return window.localStorage.getItem(MARK(workspaceId));
  } catch {
    return null;
  }
}

export type MoveStep = "exporting" | "sending" | "opening";

/** Export (no logs: pins, questions, journal, decisions), post, mark this
 * workspace as the copy; returns the local page to open. */
export async function moveWorkspace(workspaceId: string, onStep: (s: MoveStep) => void): Promise<string> {
  const client = getEngineClient();
  onStep("exporting");
  const res = await client.exportWorkspace({ include_logs: false, anonymise: false });
  const blob = await (await fetch(client.downloadUrl(res.download_url))).blob();
  onStep("sending");
  const init: RequestInit & { targetAddressSpace?: string } = {
    method: "POST", mode: "cors", headers: { "Content-Type": "application/octet-stream" }, body: blob,
    targetAddressSpace: "loopback",
  };
  let reply: { ok: boolean; result?: { open_url: string }; error?: { message?: string } };
  try {
    reply = await (await fetch(`${MOVE_URL}?filename=${encodeURIComponent(res.filename)}`, init)).json();
  } catch (e) {
    throw new Error(`EIS on this computer didn't answer (${e instanceof Error ? e.message : String(e)}). Is Claude Desktop with the extension, or slingology-eis serve, running?`);
  }
  if (!reply.ok || !reply.result) throw new Error(reply.error?.message ?? "EIS on this computer couldn't import the workspace.");
  try {
    window.localStorage.setItem(MARK(workspaceId), new Date().toISOString());
  } catch {
    // private mode: the move still happened
  }
  onStep("opening");
  return reply.result.open_url;
}

/** On the local pages after a move: the id of the moved workspace, once. */
export function takeMovedNote(): string | null {
  const KEY = "slingology-eis.moved-note";
  try {
    const params = new URLSearchParams(window.location.search);
    const moved = params.get("moved");
    if (moved) {
      window.sessionStorage.setItem(KEY, moved);
      params.delete("moved");
      const q = params.toString();
      window.history.replaceState(null, "", `${window.location.pathname}${q ? `?${q}` : ""}${window.location.hash}`);
    }
    return window.sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function dismissMovedNote() {
  try {
    window.sessionStorage.removeItem("slingology-eis.moved-note");
  } catch {
    // nothing kept
  }
}
