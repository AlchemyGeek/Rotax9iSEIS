import { useEffect, useState, type ReactNode } from "react";
import { getRuntime, type Runtime } from "../lib/engineClient";
import { EVICTION_MARKER, type EngineStatus, type StatusSource } from "../lib/hostState";
import { servedFromDevice, takeUpdateNotice } from "../lib/serviceWorker";

// Spec 03 v0.24 §6.3, Spec 04 v0.7 §9.4–§9.5: what the app shows before a
// page can run — the in-browser engine loading on a first visit, an
// installation with no runtime.json, an engine that couldn't start — and
// the one notice for workspace data the browser has cleared.

const PANEL: React.CSSProperties = { background: "var(--panel)", borderRadius: 12, padding: "20px 24px", maxWidth: 520, color: "var(--text-primary)" };
const BUTTON: React.CSSProperties = { padding: "7px 14px", borderRadius: 8, background: "var(--panel-control)", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 12, cursor: "pointer" };

function Screen({ children }: { children: ReactNode }) {
  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      {children}
    </div>
  );
}

function markerSet(): boolean {
  try { return localStorage.getItem(EVICTION_MARKER) != null; } catch { return false; }
}

export function EngineGate({ children }: { children: ReactNode }) {
  const [runtime, setRuntime] = useState<Runtime | null>(null);
  const [status, setStatus] = useState<EngineStatus | null>(null);
  const [slow, setSlow] = useState(false);
  const [evictionDismissed, setEvictionDismissed] = useState(false);
  const [fromDevice] = useState(servedFromDevice);
  const [updatedTo, setUpdatedTo] = useState<string | null>(null);

  useEffect(() => {
    let unsubscribe = () => {};
    // A cached engine is ready in well under a second: only a slower
    // start (a first visit's download) shows the loading screen.
    const t = setTimeout(() => setSlow(true), 400);
    getRuntime().then(({ runtime: r, client }) => {
      setRuntime(r);
      if (r.host === "browser") {
        unsubscribe = (client as unknown as StatusSource).onStatus(setStatus);
        void takeUpdateNotice().then(setUpdatedTo);
      }
    });
    return () => { clearTimeout(t); unsubscribe(); };
  }, []);

  if (runtime?.host === "incomplete") {
    return (
      <Screen>
        <div role="alert" data-testid="installation-incomplete" style={PANEL}>
          <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>This installation is incomplete</div>
          <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
            The page couldn't tell where its analysis engine runs ({runtime.message}). Reinstall or rebuild the app; if you run it
            from a terminal, start it with <span className="mono">slingology-eis serve</span>.
          </div>
        </div>
      </Screen>
    );
  }

  if (runtime?.host === "browser") {
    if (status?.phase === "failed") {
      return (
        <Screen>
          <div role="alert" data-testid="engine-failed" style={PANEL}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>The analysis engine couldn't start</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>{status.message}</div>
            <button type="button" style={BUTTON} onClick={() => window.location.reload()}>Try again</button>
          </div>
        </Screen>
      );
    }
    if (status?.phase !== "ready") {
      if (!slow) return null;
      const done = status?.phase === "loading" ? status.done : 0;
      const total = status?.phase === "loading" ? status.total : 4;
      return (
        <Screen>
          <div role="status" data-testid="engine-loading" style={PANEL}>
            {fromDevice ? (
              <>
                <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Starting the analysis engine…</div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
                  Loading from this device — no download needed. Everything runs in this browser; your logs never leave your computer.
                </div>
              </>
            ) : (
              <>
                <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Setting up the analysis engine…</div>
                <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
                  Downloading about 30 MB, once — after this it opens from this device in a few seconds, with or without a network.
                  Everything runs in this browser; your logs never leave your computer.
                </div>
              </>
            )}
            <div style={{ height: 6, borderRadius: 3, background: "var(--panel-control)", overflow: "hidden" }}>
              <div style={{ width: `${Math.round((100 * done) / total)}%`, height: "100%", background: "var(--brand-tint)", transition: "width .3s" }} />
            </div>
            <div className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 6 }}>
              {status?.phase === "loading" ? status.step : "starting"}
            </div>
          </div>
        </Screen>
      );
    }
    if (!status.registryPresent && markerSet() && !evictionDismissed) {
      // §9.4: the browser cleared this site's storage since a workspace
      // was created here — say so, rather than a silent first run.
      return (
        <Screen>
          <div role="alert" data-testid="data-gone" style={PANEL}>
            <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Your workspace data isn't on this device any more</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 14 }}>
              This browser has cleared the app's storage — for example after you cleared site data, or after a long time without a visit.
              Your logs weren't touched. Import a workspace export you saved, or add your log folders again.
            </div>
            <span style={{ display: "flex", gap: 6 }}>
              <button type="button" style={BUTTON} onClick={() => { clearMarker(); setEvictionDismissed(true); window.location.hash = "#/settings?tab=app"; }}>
                Import a workspace
              </button>
              <button type="button" style={BUTTON} onClick={() => { clearMarker(); setEvictionDismissed(true); window.location.hash = "#/flights"; }}>
                Add your log folders
              </button>
            </span>
          </div>
        </Screen>
      );
    }
  }

  return (
    <>
      {children}
      {updatedTo && (
        // Step 6: said once, after the page has switched to a new release.
        <div role="status" data-testid="update-notice" style={{ position: "fixed", bottom: 16, left: "50%", transform: "translateX(-50%)", zIndex: 1000,
          ...PANEL, padding: "10px 14px", display: "flex", alignItems: "center", gap: 14, fontSize: 12, boxShadow: "0 4px 18px rgba(0,0,0,0.4)", border: "1px solid var(--border)" }}>
          <span>Updated to version {updatedTo}</span>
          <button type="button" style={{ ...BUTTON, padding: "4px 10px", fontSize: 11 }} onClick={() => setUpdatedTo(null)}>Dismiss</button>
        </div>
      )}
    </>
  );
}

function clearMarker() {
  try { localStorage.removeItem(EVICTION_MARKER); } catch { /* private mode */ }
}
