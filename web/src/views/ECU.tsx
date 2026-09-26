import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { NoteSection, NoteToggle } from "../components/NoteEditor";
import { ecuAnalysis as fixtureEcu } from "../lib/fixtures";
import { getEngineClient } from "../lib/engineClient";
import type { Annotation, EcuAnalysis, EcuClassification, EcuRun } from "../types/contract";

const client = getEngineClient();

const CLASS_COLOR: Record<EcuClassification, string> = {
  POWERUP: "#6366F1",
  LANE_CHECK: "#0EA5E9",
  SHUTDOWN: "#374151",
  IN_FLIGHT: "var(--severity-limit)",
};

// Fixture-mode fallback only — real flight_ids are opaque hex, so a real
// filename always comes from the live filenameMap (built from
// listFlights()'s source_filename) below. Fixture flight_ids are still
// the readable "fl_YYYYMMDD_HHMMSS_AIRPORT" form, which already encodes
// what would otherwise be a filename lookup.
function guessFilename(flightId: string): string {
  return flightId.replace(/^fl_/, "log_") + ".csv";
}

function formatDate(utc: string | null): string {
  if (!utc) return "unknown date";
  const d = new Date(utc.replace(" ", "T") + (utc.endsWith("Z") ? "" : "Z"));
  return isNaN(d.getTime()) ? utc : d.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
}

function formatTime(utc: string | null): string {
  if (!utc) return "—";
  const [, time] = utc.split(/[ T]/);
  return time ? time.replace("Z", "").split(".")[0] : utc;
}

// The B3 fix, made visible: an IN_FLIGHT run's oil pressure reading itself
// (not a hardcoded flight_id) decides whether OIL PRESS is highlighted as
// engine-parameter-correlated — RPM > 0 (the engine was actually turning,
// not a ground power-up) with oil pressure reading near zero.
function oilPressCorrelated(run: EcuRun): boolean {
  const { mean_rpm, mean_oil_press_psi } = run.context;
  return (
    run.co_alerts.includes("OIL PRESS") &&
    mean_rpm != null && mean_rpm > 300 &&
    mean_oil_press_psi != null && mean_oil_press_psi < 10
  );
}

function InFlightCard({
  run,
  filename,
  note,
  onSaveNote,
  onDeleteNote,
  notesEnabled = true,
}: {
  run: EcuRun;
  filename: string;
  note?: string;
  onSaveNote?: (text: string) => void;
  onDeleteNote?: () => void;
  notesEnabled?: boolean;
}) {
  const navigate = useNavigate();
  const flagged = oilPressCorrelated(run);
  const c = run.context;
  const [expanded, setExpanded] = useState(false);

  function toggleExpanded(e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    setExpanded((v) => !v);
  }

  return (
    <div
      onClick={() => navigate(`/flights/${run.flight_id}`)}
      style={{
        background: "var(--panel)",
        borderRadius: 12,
        padding: "16px 18px",
        marginBottom: 10,
        cursor: "pointer",
        border: flagged ? "1px solid rgba(229,72,77,0.35)" : "1px solid transparent",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
        <div>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{formatDate(run.start_utc)}</span>
          <span className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)", marginLeft: 8 }}>
            {formatTime(run.start_utc)} &middot; {run.duration_s}s
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }}>{filename}</span>
          {notesEnabled && <NoteToggle note={note} expanded={expanded} onToggle={toggleExpanded} />}
        </div>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(6,1fr)", gap: 10, marginBottom: 12 }}>
        <div><div style={{ fontSize: 9, color: "var(--text-tertiary)" }}>RPM</div><div className="mono" style={{ fontSize: 12 }}>{c.mean_rpm ?? "—"}</div></div>
        <div>
          <div style={{ fontSize: 9, color: "var(--text-tertiary)" }}>Oil press</div>
          <div className="mono" style={{ fontSize: 12, color: flagged ? "var(--severity-limit)" : "var(--text-primary)", fontWeight: flagged ? 600 : 400 }}>
            {c.mean_oil_press_psi ?? "—"} psi
          </div>
        </div>
        <div><div style={{ fontSize: 9, color: "var(--text-tertiary)" }}>Oil temp</div><div className="mono" style={{ fontSize: 12 }}>{c.mean_oil_temp_f ?? "—"}°F</div></div>
        <div><div style={{ fontSize: 9, color: "var(--text-tertiary)" }}>Coolant</div><div className="mono" style={{ fontSize: 12 }}>{c.mean_coolant_temp_f ?? "—"}°F</div></div>
        <div><div style={{ fontSize: 9, color: "var(--text-tertiary)" }}>Main volts</div><div className="mono" style={{ fontSize: 12 }}>{c.mean_main_volts ?? "—"}V</div></div>
        <div><div style={{ fontSize: 9, color: "var(--text-tertiary)" }}>Baro alt</div><div className="mono" style={{ fontSize: 12 }}>{c.mean_baro_alt_ft ?? "—"} ft</div></div>
      </div>
      {run.co_alerts.length > 0 ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {run.co_alerts.map((a) =>
            flagged && a === "OIL PRESS" ? (
              <span key={a} style={{ fontSize: 10, padding: "3px 9px", borderRadius: 10, background: "rgba(229,72,77,0.15)", border: "1px solid var(--severity-limit)", color: "var(--severity-limit)", fontWeight: 600 }}>
                ⚠ {a} — engine-parameter correlated
              </span>
            ) : (
              <span key={a} style={{ fontSize: 10, padding: "3px 9px", borderRadius: 10, background: "var(--panel-control)", color: "var(--text-secondary)" }}>
                {a}
              </span>
            )
          )}
        </div>
      ) : (
        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>No co-active alerts.</div>
      )}
      {flagged && (
        <div style={{ fontSize: 11, color: "var(--text-primary)", marginTop: 8 }}>
          Oil pressure reads {c.mean_oil_press_psi} psi at this event, with the engine turning — the only signal here that lines up with a real engine parameter, not just an avionics indication.
        </div>
      )}
      {c.oil_nan_frac != null && c.oil_nan_frac > 0.5 && (
        <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 8 }}>
          {Math.round(c.oil_nan_frac * 100)}% of oil-pressure readings missing during this window — treat the figure above as approximate.
        </div>
      )}
      {notesEnabled && (
        <NoteSection
          note={note}
          expanded={expanded}
          onSave={(text) => onSaveNote?.(text)}
          onDelete={onDeleteNote}
          onCollapse={() => setExpanded(false)}
        />
      )}
    </div>
  );
}

// ECU investigation (Spec 03 §5.4), built on the B3 fix (Spec 01 §8.6):
// IN_FLIGHT runs get their own expanded card with their own co-active
// alerts — not a pooled fleet-wide frequency table, which is exactly the
// KSFF/OIL PRESS problem B3 was raised over (a real engine-parameter
// correlation would get lost in an aggregate count).
// ECU-run refs (`ref.ref === start_utc`) are only unique within a single
// flight, unlike an insight_id — this view aggregates runs across the
// whole workspace, so a note lookup has to key on both fields together.
function runRefKey(flightId: string, startUtc: string | null): string {
  return `${flightId}::${startUtc ?? ""}`;
}

export function ECU() {
  const [ecu, setEcu] = useState<EcuAnalysis>(fixtureEcu);
  const [filenames, setFilenames] = useState<Record<string, string>>({});
  const [annotations, setAnnotations] = useState<Annotation[]>([]);
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(true);

  async function refreshAnnotations() {
    if (usingFixture) return;
    try {
      const res = await client.listAnnotations();
      setAnnotations(res.annotations);
    } catch {
      // leave whatever was already loaded
    }
  }

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [live, flights, annRes] = await Promise.all([
          client.analyzeEcuWorkspace(),
          client.listFlights(),
          client.listAnnotations(),
        ]);
        if (cancelled) return;
        if (live.flight_ids.length === 0) throw new Error("empty workspace");
        setEcu(live);
        const map: Record<string, string> = {};
        for (const f of flights) if (f.source_filename) map[f.flight_id] = f.source_filename;
        setFilenames(map);
        setAnnotations(annRes.annotations);
        setUsingFixture(false);
      } catch {
        if (!cancelled) {
          setEcu(fixtureEcu);
          setFilenames({});
          setAnnotations([]);
          setUsingFixture(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const annotationByRunKey = useMemo(() => {
    const map = new Map<string, Annotation>();
    for (const a of annotations) if (a.ref.kind === "ecu_run") map.set(runRefKey(a.flight_id, a.ref.ref), a);
    return map;
  }, [annotations]);

  async function handleSaveNote(run: EcuRun, text: string) {
    const key = runRefKey(run.flight_id, run.start_utc);
    const existing = annotationByRunKey.get(key);
    try {
      await client.saveAnnotation({
        id: existing?.id,
        flightId: run.flight_id,
        ref: { kind: "ecu_run", ref: run.start_utc ?? "" },
        note: text,
      });
      await refreshAnnotations();
    } catch {
      // server unreachable
    }
  }

  async function handleDeleteNote(annotationId: string) {
    try {
      await client.deleteAnnotation(annotationId);
      await refreshAnnotations();
    } catch {
      // server unreachable
    }
  }

  const runs = ecu.runs;
  const filenameFor = (flightId: string) => filenames[flightId] ?? guessFilename(flightId);

  const inFlightRuns = useMemo(
    () => runs.filter((r) => r.classification === "IN_FLIGHT").sort((a, b) => (a.start_utc ?? "").localeCompare(b.start_utc ?? "")),
    [runs]
  );

  const routine = useMemo(() => {
    const byClass = new Map<EcuClassification, EcuRun[]>();
    for (const r of runs) {
      if (r.classification === "IN_FLIGHT") continue;
      if (!byClass.has(r.classification)) byClass.set(r.classification, []);
      byClass.get(r.classification)!.push(r);
    }
    return Array.from(byClass.entries()).map(([classification, group]) => {
      const durations = group.map((r) => r.duration_s).sort((a, b) => a - b);
      return { classification, count: group.length, min: durations[0], max: durations[durations.length - 1] };
    });
  }, [runs]);

  const pairExample = useMemo(() => runs.find((r) => r.lane_check_pair), [runs]);
  const powerupCount = ecu.counts.POWERUP ?? 0;

  return (
    <NavShell>
      <div style={{ flexGrow: 1, overflowY: "auto", padding: "24px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <h1 style={{ margin: "0 0 4px", fontSize: 19, fontWeight: 700 }}>
            Engine ECU CAS Events {usingFixture && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}>(sample)</span>}
            {loading && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}> · loading…</span>}
          </h1>
          <span className="mono" style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
            {runs.length} runs across {ecu.flight_ids.length} flights &nbsp;&middot;&nbsp;{" "}
            {Object.entries(ecu.counts).map(([k, v]) => `${v} ${k}`).join(" · ")}
          </span>
          <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 6, maxWidth: 780 }}>
            An <strong>event</strong> here means an ENGINE ECU alert classified <span className="mono">IN_FLIGHT</span> — not
            the ground-context occurrences during POWERUP, LANE_CHECK, or SHUTDOWN, which are routine on nearly every flight
            ({powerupCount} of {runs.length} runs) and are rolled up below instead of expanded per-event.
          </div>
        </div>

        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>In-flight ECU events</span>
            <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.4, color: "var(--severity-warning)", background: "rgba(245,165,36,0.12)", padding: "2px 8px", borderRadius: 10 }}>
              {inFlightRuns.length}
            </span>
          </div>
          {inFlightRuns.map((r, i) => {
            const existing = annotationByRunKey.get(runRefKey(r.flight_id, r.start_utc));
            return (
              <InFlightCard
                key={`${r.flight_id}-${r.start_utc}-${i}`}
                run={r}
                filename={filenameFor(r.flight_id)}
                note={existing?.note}
                notesEnabled={!usingFixture}
                onSaveNote={(text) => handleSaveNote(r, text)}
                onDeleteNote={existing ? () => handleDeleteNote(existing.id) : undefined}
              />
            );
          })}
          {inFlightRuns.length === 0 && (
            <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No in-flight ECU events in this workspace.</div>
          )}
        </div>

        <div>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Ground &amp; routine runs</div>
          <div style={{ background: "var(--panel)", borderRadius: 12, padding: "6px 14px" }}>
            <table>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Classification</th>
                  <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Count</th>
                  <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Duration range</th>
                </tr>
              </thead>
              <tbody>
                {routine.map(({ classification, count, min, max }) => (
                  <tr key={classification} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td>
                      <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ width: 7, height: 7, borderRadius: "50%", background: CLASS_COLOR[classification] }} />
                        {classification}
                      </span>
                    </td>
                    <td className="mono">{count}</td>
                    <td className="mono">{min}s – {max}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {pairExample && (
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 8 }}>
              Sample lane-check pair — <span className="mono">{filenameFor(pairExample.flight_id)}</span>: {pairExample.lane_check_note}
            </div>
          )}
        </div>
      </div>
    </NavShell>
  );
}
