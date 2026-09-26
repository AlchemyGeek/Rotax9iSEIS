import { type ReactNode, useEffect, useState } from "react";
import { NavLink } from "react-router-dom";
import { getEngineClient } from "../lib/engineClient";
import { appSettings as fixtureAppSettings, workspaceRegistry as fixtureWorkspaceRegistry } from "../lib/fixtures";
import type { WorkspaceRegistryEntry } from "../types/contract";

const client = getEngineClient();

// Mirrors slingology_eis/workspace.py's ENGINE_MODELS — no RPC exposes
// this short a list on its own (list_engines returns full profile
// objects), and it changes rarely enough that duplicating the four
// values here is simpler than a round trip just to populate a picker.
const ENGINE_MODELS = ["912iS", "914iS", "915iS", "916iS"];

const NAV_LINK_STYLE = ({ isActive }: { isActive: boolean }) => ({
  padding: "6px 14px",
  borderRadius: 8,
  fontSize: 13,
  fontWeight: isActive ? 600 : 500,
  color: isActive ? "var(--accent)" : "var(--text-secondary)",
  background: isActive ? "var(--accent-15)" : "transparent",
});

// Active workspace's name, a dropdown to the others, and "+ New workspace"
// (Spec 03 §4) — permanent in the nav because switching workspaces is
// something a pilot managing more than one aircraft does routinely, not
// configuration set once. Live-first with a fixture fallback, same
// convention as FlightView/Trends/Baselines: a genuinely empty registry
// (server reachable, zero workspaces created yet) is real data and shown
// as-is, not covered up with the fixture — only an actual connection
// failure falls back to it.
function WorkspaceSwitcher() {
  const [open, setOpen] = useState(false);
  const [workspaces, setWorkspaces] = useState<WorkspaceRegistryEntry[]>(fixtureWorkspaceRegistry.workspaces);
  const [activeId, setActiveId] = useState<string | null>(fixtureAppSettings.last_active_workspace_id);
  const [usingFixture, setUsingFixture] = useState(true);
  const [busy, setBusy] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newEngine, setNewEngine] = useState("916iS");
  const [newTail, setNewTail] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [active, list] = await Promise.all([client.getActiveWorkspace(), client.listWorkspaces()]);
        if (cancelled) return;
        setWorkspaces(list);
        setActiveId(active.active && active.manifest ? active.manifest.id : null);
        setUsingFixture(false);
      } catch {
        if (!cancelled) {
          setWorkspaces(fixtureWorkspaceRegistry.workspaces);
          setActiveId(fixtureAppSettings.last_active_workspace_id);
          setUsingFixture(true);
        }
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const active = workspaces.find((w) => w.id === activeId) ?? workspaces[0] ?? null;
  const others = workspaces.filter((w) => w.id !== active?.id);

  // A full reload after switching/creating is a deliberately blunt
  // guarantee: every already-mounted view (Flights, Trends, Baselines...)
  // refetches under the new active workspace, with no cross-component
  // state store to keep in sync — there isn't one today, and building
  // one just for this would be a much bigger change than this pass.
  async function handleSwitch(id: string) {
    if (usingFixture || id === active?.id) return;
    setBusy(true);
    try {
      await client.switchWorkspace(id);
      window.location.hash = "#/flights";
      window.location.reload();
    } catch {
      setBusy(false);
    }
  }

  async function handleCreate() {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      await client.createWorkspace(newName.trim(), newEngine, newTail.trim() || undefined);
      window.location.hash = "#/flights";
      window.location.reload();
    } catch {
      setBusy(false);
    }
  }

  if (!active) {
    // Real, empty registry — no fixture stand-in here, the create form
    // below is the actual next step, not a fallback to hide it.
    return (
      <div style={{ position: "relative" }}>
        <button
          onClick={() => setOpen((o) => !o)}
          style={{
            padding: "6px 12px", borderRadius: 8, background: "var(--panel-control)",
            border: "1px dashed var(--border)", color: "var(--text-secondary)", fontSize: 12, cursor: "pointer",
          }}
        >
          + New workspace
        </button>
        {open && (
          <>
            <div onClick={() => setOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 10 }} />
            <div
              style={{
                position: "absolute", top: "calc(100% + 6px)", left: 0, minWidth: 220, zIndex: 11,
                background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 10,
                padding: 10, boxShadow: "0 8px 24px rgba(0,0,0,0.4)", display: "flex", flexDirection: "column", gap: 6,
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <input
                autoFocus
                placeholder="Workspace name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 12 }}
              />
              <select
                value={newEngine}
                onChange={(e) => setNewEngine(e.target.value)}
                style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 12 }}
              >
                {ENGINE_MODELS.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
              <input
                placeholder="Tail number (optional)"
                value={newTail}
                onChange={(e) => setNewTail(e.target.value)}
                style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 12 }}
              />
              <button
                onClick={handleCreate}
                disabled={busy || !newName.trim()}
                style={{ padding: "6px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontSize: 12, fontWeight: 600, cursor: busy ? "default" : "pointer" }}
              >
                {busy ? "Creating…" : "Create"}
              </button>
            </div>
          </>
        )}
      </div>
    );
  }

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setOpen((o) => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 6, padding: "6px 12px", borderRadius: 8,
          background: "var(--panel-control)", border: "1px solid var(--border)", color: "var(--text-primary)",
          fontSize: 12, fontWeight: 600, cursor: "pointer", maxWidth: 220,
        }}
      >
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{active.name}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" style={{ flexShrink: 0 }}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {open && (
        <>
          <div onClick={() => { setOpen(false); setShowCreate(false); }} style={{ position: "fixed", inset: 0, zIndex: 10 }} />
          <div
            style={{
              position: "absolute", top: "calc(100% + 6px)", left: 0, minWidth: 260, zIndex: 11,
              background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 10,
              padding: 6, boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
            }}
          >
            <div style={{ padding: "8px 10px", fontSize: 12, fontWeight: 600, color: "var(--accent)" }}>
              {active.name}
              <div className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)", fontWeight: 400 }}>
                {active.flight_count} flights &middot; {active.log_folder_count} log folder{active.log_folder_count === 1 ? "" : "s"} &middot; active
              </div>
            </div>
            {others.map((w) => (
              <div
                key={w.id}
                onClick={() => handleSwitch(w.id)}
                style={{
                  padding: "8px 10px", fontSize: 12, color: "var(--text-secondary)",
                  cursor: usingFixture ? "default" : "pointer", borderRadius: 6, opacity: busy ? 0.5 : 1,
                }}
                onMouseEnter={(e) => !usingFixture && (e.currentTarget.style.background = "var(--panel-control)")}
                onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                title={usingFixture ? "no local server reachable — start `slingology-eis serve` to switch workspaces" : "switch to this workspace"}
              >
                {w.name}
                <div className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{w.flight_count} flights</div>
              </div>
            ))}
            <div style={{ borderTop: "1px solid var(--border)", marginTop: 4, paddingTop: 4 }}>
              {!showCreate ? (
                <div
                  onClick={() => setShowCreate(true)}
                  style={{ padding: "8px 10px", fontSize: 12, color: usingFixture ? "var(--text-tertiary)" : "var(--accent)", cursor: usingFixture ? "default" : "pointer" }}
                  title={usingFixture ? "no local server reachable" : undefined}
                >
                  + New workspace
                </div>
              ) : (
                <div style={{ padding: "8px 10px", display: "flex", flexDirection: "column", gap: 6 }} onClick={(e) => e.stopPropagation()}>
                  <input
                    autoFocus
                    placeholder="Workspace name"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                    style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 12 }}
                  />
                  <select
                    value={newEngine}
                    onChange={(e) => setNewEngine(e.target.value)}
                    style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 12 }}
                  >
                    {ENGINE_MODELS.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                  <input
                    placeholder="Tail number (optional)"
                    value={newTail}
                    onChange={(e) => setNewTail(e.target.value)}
                    style={{ background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 12 }}
                  />
                  <button
                    onClick={handleCreate}
                    disabled={busy || !newName.trim()}
                    style={{ padding: "6px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontSize: 12, fontWeight: 600, cursor: busy ? "default" : "pointer" }}
                  >
                    {busy ? "Creating…" : "Create"}
                  </button>
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

export function NavShell({ right, children }: { right?: ReactNode; children: ReactNode }) {
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        background: "var(--bg)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          height: 56,
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 24px",
          borderBottom: "1px solid var(--border)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <span style={{ fontWeight: 700, fontSize: 15, letterSpacing: 0.2 }}>SlingologyEIS</span>
          <WorkspaceSwitcher />
          <nav style={{ display: "flex", gap: 4 }}>
            <NavLink to="/flights" end style={NAV_LINK_STYLE}>
              Flights
            </NavLink>
            <NavLink to="/trends" style={NAV_LINK_STYLE}>
              Trends
            </NavLink>
            <NavLink to="/baselines" style={NAV_LINK_STYLE}>
              Baselines
            </NavLink>
            <NavLink to="/ecu" style={NAV_LINK_STYLE}>
              ECU
            </NavLink>
            <NavLink to="/annotations" style={NAV_LINK_STYLE}>
              Notes
            </NavLink>
          </nav>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {right}
          <NavLink
            to="/settings"
            style={({ isActive }) => ({
              width: 32,
              height: 32,
              borderRadius: 8,
              background: isActive ? "var(--accent-15)" : "var(--panel)",
              border: "1px solid var(--border)",
              color: isActive ? "var(--accent)" : "var(--text-secondary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            })}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06a1.65 1.65 0 00.33-1.82 1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 112.83-2.83l.06.06a1.65 1.65 0 001.82.33H9a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 112.83 2.83l-.06.06a1.65 1.65 0 00-.33 1.82V9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" />
            </svg>
          </NavLink>
        </div>
      </div>
      <div style={{ flexGrow: 1, minHeight: 0, display: "flex" }}>{children}</div>
    </div>
  );
}
