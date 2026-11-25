import { useEffect, useState } from "react";
import { useCapabilities } from "../lib/capabilities";
import { getEngineClient } from "../lib/engineClient";
import { LOCAL_EIS, movedAt, moveWorkspace, probeLocalEis, type MoveStep } from "../lib/moveWorkspace";
import { DOCS_URL } from "./NavShell";

// Spec 16 D17 — on the website (Research home, Settings → App): when EIS
// answers on this computer, one button moves this workspace there.

const STEP: Record<MoveStep, string> = {
  exporting: "Exporting this workspace…",
  sending: "Sending it to EIS on this computer…",
  opening: "Opening EIS on this computer…",
};

const BOX: React.CSSProperties = {
  background: "var(--panel)", border: "1px solid var(--brand-tint)", borderRadius: 12, padding: "12px 16px",
  display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", fontSize: 12,
};

// Spec 03 v0.34: on Research home the banner can be dismissed (per workspace,
// in this browser); after that it is offered only in Settings → App.
const DISMISSED = "slingology-eis.move-banner-dismissed.";

export function moveBannerDismissed(workspaceId: string): boolean {
  try { return localStorage.getItem(DISMISSED + workspaceId) === "1"; } catch { return false; }
}

function Dismiss({ onClick }: { onClick: () => void }) {
  return (
    <button type="button" aria-label="Dismiss" title="Hide this here; it stays in Settings → App" onClick={onClick} data-testid="move-dismiss"
      style={{ background: "none", border: "none", color: "var(--text-tertiary)", fontSize: 16, lineHeight: 1, cursor: "pointer", padding: "0 2px" }}>×</button>
  );
}

export function MoveWorkspaceBanner({ dismissable = false }: { dismissable?: boolean }) {
  const caps = useCapabilities();
  const [dismissed, setDismissed] = useState(false);
  const offered = caps?.features.move_workspace === true;
  const [workspaceId, setWorkspaceId] = useState<string | null>(null);
  const [local, setLocal] = useState(false);
  const [step, setStep] = useState<MoveStep | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!offered) return;
    let cancelled = false;
    void getEngineClient().getActiveWorkspace().then((a) => {
      if (cancelled || !a.active || !a.manifest) return;
      setWorkspaceId(a.manifest.id);
      // Only someone with a workspace here is asked about this computer.
      void probeLocalEis().then((ok) => { if (!cancelled) setLocal(ok); });
    }, () => undefined);
    return () => { cancelled = true; };
  }, [offered]);

  if (!offered || !workspaceId) return null;
  if (dismissable && (dismissed || moveBannerDismissed(workspaceId))) return null;
  const dismiss = dismissable ? () => {
    try { localStorage.setItem(DISMISSED + workspaceId, "1"); } catch { /* private mode: for this visit */ }
    setDismissed(true);
  } : null;
  const moved = movedAt(workspaceId);
  if (moved) {
    return (
      <div style={{ ...BOX, borderColor: "var(--border)" }} data-testid="move-copy">
        <span><strong>This is now the copy.</strong> You moved this workspace to EIS on this computer on {new Date(moved).toLocaleDateString()}; work there from now on.</span>
        <a href={`${LOCAL_EIS}/`} data-testid="move-open-local">Open EIS on this computer</a>
        {dismiss && <Dismiss onClick={dismiss} />}
      </div>
    );
  }
  if (!local) return null;

  async function onMove() {
    setError(null);
    try {
      const url = await moveWorkspace(workspaceId!, setStep);
      window.location.assign(url);
    } catch (e) {
      setStep(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div style={BOX} data-testid="move-workspace">
      <div style={{ flexGrow: 1, minWidth: 260 }}>
        <div style={{ fontWeight: 600, fontSize: 13 }}>EIS is running on this computer</div>
        <div style={{ color: "var(--text-secondary)" }}>
          Move this workspace there — your questions and marks, notes, journal and decisions — and work with Claude on it.
          Your logs stay where they are: you link their folder there and Sync.{" "}
          <a href={`${DOCS_URL}walkthroughs/install-extension/`} target="_blank" rel="noreferrer">How it works</a>
        </div>
        {step && <div style={{ color: "var(--text-tertiary)", marginTop: 4 }} data-testid="move-step">{STEP[step]}</div>}
        {error && <div role="alert" style={{ color: "var(--severity-warning)", marginTop: 4 }} data-testid="move-error">{error}</div>}
      </div>
      <button type="button" onClick={() => void onMove()} disabled={step !== null} data-testid="move-workspace-button"
        style={{ padding: "6px 14px", borderRadius: 6, background: "var(--brand)", border: "none", color: "var(--on-brand)", fontSize: 12, fontWeight: 600, cursor: step ? "default" : "pointer" }}>
        {step ? "Moving…" : "Move my workspace to EIS on this computer"}
      </button>
      {dismiss && !step && <Dismiss onClick={dismiss} />}
    </div>
  );
}
