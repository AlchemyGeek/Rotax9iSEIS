import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getEngineClient } from "../lib/engineClient";
import type { DataLocationTarget } from "../lib/engineClient";
import { OUTCOME_KEY, assessmentText, outcomeText, plural } from "../lib/dataLocation";
import type { DataLocation, DataLocationAssessment, DataLocationProgress } from "../types/contract";

// Spec 14 v0.12 §5.2 — where the pilot's data lives, and moving it
// (behaviour: Spec 02 v0.10 §5.8.1). Two surfaces share the chooser: the
// Settings → App panel, and the notice that replaces every page when the
// chosen location can't be reached.

const client = getEngineClient();

const SOURCE_TEXT: Record<DataLocation["source"], (loc: DataLocation) => string> = {
  default: () => "Default location",
  chosen: () => "Chosen by you",
  environment: (loc) => `Set by the environment (${loc.env_var})`,
};

const CONFIRM_LABEL: Record<Exclude<DataLocationAssessment["action"], "refused">, string> = {
  move: "Move data",
  use_existing: "Use this location",
  start_fresh: "Start fresh here",
};

function progressText(p: DataLocationProgress | null) {
  if (p?.phase === "copying" && p.total) return `Copying your data — ${p.done} of ${p.total} files`;
  if (p?.phase === "checking") return "Checking the copy…";
  return "Moving your data…";
}

const BUTTON: React.CSSProperties = { fontSize: 11, padding: "5px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", cursor: "pointer" };
const PRIMARY: React.CSSProperties = { ...BUTTON, background: "var(--brand)", border: "none", color: "var(--on-brand)", fontWeight: 600 };

// The path field, what choosing it would do, and the confirm button.
// `target` set from outside (Use default location) skips the field.
function Chooser({ fixedTarget, onCancel }: { fixedTarget?: DataLocationTarget; onCancel: () => void }) {
  const [path, setPath] = useState("");
  // Answers are kept with the path they answer, so a confirm is never
  // offered against an answer for a different path.
  const [answer, setAnswer] = useState<{ key: string; assessment?: DataLocationAssessment; error?: string } | null>(null);
  const [changing, setChanging] = useState(false);
  const [progress, setProgress] = useState<DataLocationProgress | null>(null);
  const [changeError, setChangeError] = useState<string | null>(null);

  const key = fixedTarget ? "default" : path.trim();
  const assessment = answer?.key === key ? answer.assessment ?? null : null;
  const error = changeError ?? (answer?.key === key ? answer.error ?? null : null);

  useEffect(() => {
    if (!key) return;
    const target: DataLocationTarget = key === "default" && fixedTarget ? fixedTarget : key;
    const t = window.setTimeout(() => {
      client.assessDataLocation(target)
        .then((a) => setAnswer({ key, assessment: a }))
        .catch((e) => setAnswer({ key, error: e instanceof Error ? e.message : String(e) }));
    }, fixedTarget ? 0 : 300);
    return () => window.clearTimeout(t);
  }, [key, fixedTarget]);

  async function confirm() {
    if (!key) return;
    const target: DataLocationTarget = fixedTarget ?? key;
    setChanging(true);
    setChangeError(null);
    const poll = window.setInterval(() => {
      client.getDataLocationProgress().then((p) => p.active && setProgress(p)).catch(() => {});
    }, 400);
    try {
      const result = await client.changeDataLocation(target);
      try {
        sessionStorage.setItem(OUTCOME_KEY, JSON.stringify({ action: result.action, path: result.path, previous_path: result.previous_path }));
      } catch { /* the message is a convenience; the change has happened */ }
      window.location.reload();
    } catch (e) {
      setChangeError(e instanceof Error ? e.message : String(e));
      setChanging(false);
    } finally {
      window.clearInterval(poll);
    }
  }

  const ready = assessment !== null && assessment.action !== "refused";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 10 }}>
      {!fixedTarget && (
        <input
          autoFocus
          aria-label="Data location folder"
          value={path}
          onChange={(e) => { setPath(e.target.value); setChangeError(null); }}
          placeholder="/Volumes/Drive/SlingologyEIS"
          className="mono"
          disabled={changing}
          style={{ fontSize: 11, padding: "5px 8px", borderRadius: 6, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text-primary)" }}
        />
      )}
      {assessment && (
        <div data-testid="location-assessment" style={{ fontSize: 12, color: assessment.action === "refused" ? "var(--warning, #e0a040)" : "var(--text-primary)" }}>
          {fixedTarget && <span className="mono" style={{ display: "block", color: "var(--text-tertiary)", fontSize: 11, marginBottom: 2 }}>{assessment.path}</span>}
          {assessmentText(assessment)}
        </div>
      )}
      {error && <div role="alert" style={{ fontSize: 12, color: "var(--critical, #e05050)" }}>{error}</div>}
      <span style={{ display: "flex", gap: 6 }}>
        {ready && assessment && (
          <button type="button" style={PRIMARY} disabled={changing} onClick={confirm}>
            {CONFIRM_LABEL[assessment.action as keyof typeof CONFIRM_LABEL]}
          </button>
        )}
        <button type="button" style={BUTTON} disabled={changing} onClick={onCancel}>Cancel</button>
      </span>
      {changing && (
        // Spec 14 §5.2: the rest of the app is unavailable during a move.
        <div role="status" style={{ position: "fixed", inset: 0, zIndex: 1000, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ background: "var(--panel)", borderRadius: 12, padding: "18px 22px", fontSize: 13, color: "var(--text-primary)" }}>
            {progressText(progress)}
          </div>
        </div>
      )}
    </div>
  );
}

// Settings → App (Spec 14 v0.12 §5.2). Renders nothing when the engine
// isn't a local server that knows about data locations.
export function DataLocationPanel({ panelStyle, titleStyle }: { panelStyle: React.CSSProperties; titleStyle: React.CSSProperties }) {
  const [loc, setLoc] = useState<DataLocation | null>(null);
  const [mode, setMode] = useState<"idle" | "change" | "default">("idle");
  const [outcome] = useState<string | null>(() => {
    try {
      const raw = sessionStorage.getItem(OUTCOME_KEY);
      return raw ? outcomeText(JSON.parse(raw)) : null;
    } catch {
      return null;
    }
  });

  useEffect(() => {
    client.getDataLocation().then(setLoc).catch(() => setLoc(null));
    try { sessionStorage.removeItem(OUTCOME_KEY); } catch { /* shown once is enough */ }
  }, []);

  if (!loc) return null;
  const fixed = loc.source === "environment";

  return (
    <div style={panelStyle} data-testid="data-location-panel">
      <div style={{ ...titleStyle, marginBottom: 4 }}>Data location</div>
      <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 10 }}>
        Where your workspaces, their results and your app settings are kept. Log folders stay where they are.
      </div>
      <div className="mono" style={{ fontSize: 12, color: "var(--text-primary)", wordBreak: "break-all" }}>{loc.path}</div>
      <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 4 }}>
        {SOURCE_TEXT[loc.source](loc)}
        {loc.workspace_count !== null && ` · ${plural(loc.workspace_count, "workspace")}`}
      </div>
      {outcome && (
        <div role="status" style={{ fontSize: 12, color: "var(--text-primary)", marginTop: 10, padding: "8px 10px", borderRadius: 8, background: "var(--tint-neutral)", border: "1px solid var(--border)" }}>
          {outcome}
        </div>
      )}
      {!fixed && mode === "idle" && (
        <span style={{ display: "flex", gap: 6, marginTop: 10 }}>
          <button type="button" style={BUTTON} onClick={() => setMode("change")}>Change…</button>
          {loc.source === "chosen" && (
            <button type="button" style={BUTTON} onClick={() => setMode("default")}>Use default location</button>
          )}
        </span>
      )}
      {!fixed && mode !== "idle" && (
        <Chooser fixedTarget={mode === "default" ? { default: true } : undefined} onCancel={() => setMode("idle")} />
      )}
    </div>
  );
}

// Spec 02 §5.8.1 / Spec 14 §5.2: a chosen location that can't be reached
// replaces every page with a notice — never the defaults' data, never an
// empty app without saying why.
export function DataLocationGate({ children }: { children: ReactNode }) {
  const [loc, setLoc] = useState<DataLocation | null>(null);
  const [choosing, setChoosing] = useState(false);
  const [retrying, setRetrying] = useState(false);

  useEffect(() => {
    client.getDataLocation().then(setLoc).catch(() => setLoc(null));
  }, []);

  if (!loc?.missing) return <>{children}</>;

  async function retry() {
    setRetrying(true);
    try {
      const next = await client.retryDataLocation();
      if (!next.missing) window.location.reload();
      else setLoc(next);
    } finally {
      setRetrying(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--bg)", display: "flex", alignItems: "center", justifyContent: "center", padding: 24 }}>
      <div role="alert" data-testid="data-location-missing" style={{ background: "var(--panel)", borderRadius: 12, padding: "20px 24px", maxWidth: 520, color: "var(--text-primary)" }}>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 8 }}>Your data location can't be reached</div>
        <div style={{ fontSize: 12, color: "var(--text-secondary)", marginBottom: 6 }}>
          SlingologyEIS keeps your workspaces in this folder, and it isn't there right now — for example, a drive that isn't connected.
        </div>
        <div className="mono" style={{ fontSize: 12, wordBreak: "break-all", marginBottom: 14 }}>{loc.path}</div>
        {!choosing ? (
          <span style={{ display: "flex", gap: 6 }}>
            <button type="button" style={PRIMARY} disabled={retrying} onClick={retry}>Try again</button>
            <button type="button" style={BUTTON} onClick={() => setChoosing(true)}>Choose another location</button>
          </span>
        ) : (
          <Chooser onCancel={() => setChoosing(false)} />
        )}
      </div>
    </div>
  );
}
