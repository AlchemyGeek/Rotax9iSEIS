import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { TimelinePanel } from "../components/TimelinePanel";
import { pickableChannels } from "../lib/channels";
import { getEngineClient } from "../lib/engineClient";
import { useTimeline } from "../lib/useTimeline";
import { ECU_CLASS_LABEL } from "../lib/casEvent";
import { EXCLUSION_CATEGORY_COLOR, EXCLUSION_CATEGORY_LABEL } from "../lib/exclusions";
import { SOURCE_FORMAT_LABEL } from "../lib/sourceFormat";
import type { EcuClassification, ExclusionEntry, FlightAnalysis, LogSourceFormat } from "../types/contract";

const client = getEngineClient();
const CLASS_ORDER: EcuClassification[] = ["GROUND_START", "LANE_CHECK", "GROUND", "IN_FLIGHT", "GROUND_SHUTDOWN"];

interface CasAlert { alert: string; severity: string; start_utc: string; duration_s: number }

const EMPTY_PHASES: FlightAnalysis["phases"] = [];

// Spec 03 v0.16 §5.9 — Log preview: what is in a log the app didn't treat
// as a flight, and should it be included? Read-only — header, the shared
// timeline chart, the log's CAS alerts and ENGINE ECU runs by class — and
// one action, *Include this log*. Nothing is analysed or saved here: no
// insights, reference state, topic cards, filters or notes.
//
// The route key is the log's file name (URL-encoded): skipped logs are
// keyed by file name in exclusions.json and in the preview/include ops.
export function LogPreview() {
  const { logKey } = useParams();
  const filename = logKey ? decodeURIComponent(logKey) : "";
  const navigate = useNavigate();
  const [fa, setFa] = useState<FlightAnalysis | null>(null);
  const [sourceFormat, setSourceFormat] = useState<LogSourceFormat | null>(null);
  const [filledShare, setFilledShare] = useState(0);
  const [entry, setEntry] = useState<ExclusionEntry | null>(null);
  const [folders, setFolders] = useState<string[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [reason, setReason] = useState("");
  const [including, setIncluding] = useState(false);
  const [includeError, setIncludeError] = useState<string | null>(null);
  const tl = useTimeline({ phases: fa?.phases ?? EMPTY_PHASES, usingFixture: false });

  useEffect(() => {
    let cancelled = false;
    const carried = tl.beginFlight();
    setLoadError(null);
    (async () => {
      try {
        const [got, registry, presets, appSettings, exclusions] = await Promise.all([
          client.previewExcludedLog(filename),
          client.getChannelRegistry(),
          client.getChartPresets(),
          client.getAppSettings(),
          client.listExclusions(true),
        ]);
        if (cancelled) return;
        // The preview op doesn't say which watched folder holds the file;
        // with one folder that's the answer, with several it's one of them.
        client.getActiveWorkspace()
          .then((w) => !cancelled && setFolders((w.manifest?.log_folders ?? []).map((f) => f.path)))
          .catch(() => {});
        setFa(got.flight_analysis);
        setSourceFormat(got.source_format ?? null);
        setFilledShare(got.filled_share ?? 0);
        setEntry(exclusions.entries.find((e) => e.filename === filename) ?? null);
        await tl.setupLive({
          key: filename,
          fetch: (ids) => client.getExcludedLogSeries(filename, ids),
          registry,
          presets: presets.presets,
          appSettings,
          carried,
          isCancelled: () => cancelled,
        });
      } catch {
        if (!cancelled) setLoadError(`Couldn't load ${filename} — the server may be unreachable, or the file is no longer in a watched folder.`);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filename]);

  // Spec 02 §5.11: include with a reason; the server re-scans, and a
  // folder-scanned log comes back as a flight in the same round trip.
  async function include() {
    setIncluding(true);
    setIncludeError(null);
    try {
      const res = await client.includeExcludedLog(filename, reason.trim() || "included from the log preview");
      const newId = res.scan_result?.new_flight_ids[0];
      navigate(newId ? `/flights/${newId}` : "/flights", { replace: true });
    } catch {
      setIncludeError(`Couldn't include ${filename} — the server may be unreachable. Try again.`);
    } finally {
      setIncluding(false);
    }
  }

  const header = fa?.header;
  const durationMin = fa?.metrics.duration_min?.value;
  const durationStr = typeof durationMin === "number" ? `${Math.floor(durationMin / 60)}h ${Math.round(durationMin % 60)}m` : entry?.duration_min != null ? `${Math.round(entry.duration_min)} min` : "—";
  const casAlerts = (fa?.cas_events ?? []) as CasAlert[];
  const ecuRuns = fa?.ecu_runs ?? [];
  const byClass = CLASS_ORDER.map((c) => ({ cls: c, runs: ecuRuns.filter((r) => r.classification === c) }));

  return (
    <NavShell
      right={
        <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 20, background: "var(--panel)", border: "1px solid var(--border)" }}>
          <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Log preview — nothing here is saved</span>
        </div>
      }
    >
      <div style={{ display: "flex", flexDirection: "column", width: "100%", minHeight: 0, overflowY: "auto" }}>
        {loadError ? (
          <div style={{ padding: 60, textAlign: "center" }}>
            <div style={{ fontSize: 14, color: "var(--severity-warning)", marginBottom: 14 }}>{loadError}</div>
            <button type="button" onClick={() => navigate("/flights")} style={{ padding: "6px 14px", borderRadius: 8, background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 12, cursor: "pointer" }}>
              Back to Flights
            </button>
          </div>
        ) : (
          <>
            <div style={{ flexShrink: 0, padding: "18px 24px 14px", borderBottom: "1px solid var(--border)" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: 14, flexWrap: "wrap" }}>
                <h1 className="mono" style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>{filename}</h1>
                {entry && (
                  <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 10, border: `1px solid ${EXCLUSION_CATEGORY_COLOR[entry.category]}`, color: EXCLUSION_CATEGORY_COLOR[entry.category] }}>
                    {EXCLUSION_CATEGORY_LABEL[entry.category]}
                  </span>
                )}
              </div>
              <div data-testid="log-header" className="mono" style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px", fontSize: 12, color: "var(--text-secondary)", marginTop: 8 }}>
                <span><span style={{ color: "var(--text-tertiary)" }}>Folder:</span> {folders.length === 1 ? folders[0] : folders.length > 1 ? `one of ${folders.length} watched folders` : "—"}</span>
                <span><span style={{ color: "var(--text-tertiary)" }}>Skipped:</span> {entry ? `${entry.reason} (${entry.source === "auto" ? "auto-detected" : "excluded by you"})` : "—"}</span>
                <span><span style={{ color: "var(--text-tertiary)" }}>Duration:</span> {durationStr}</span>
                <span><span style={{ color: "var(--text-tertiary)" }}>Aircraft:</span> {header?.aircraft.ident ?? entry?.aircraft_ident ?? "—"}</span>
                <span><span style={{ color: "var(--text-tertiary)" }}>Engine hours:</span> {header?.engine_hours_start ?? "—"}</span>
                {sourceFormat && SOURCE_FORMAT_LABEL[sourceFormat] && (
                  // Spec 03 v0.22 §5.9: the format and, if resampled, the filled share.
                  <span data-testid="log-format">
                    <span style={{ color: "var(--text-tertiary)" }}>Format:</span> {SOURCE_FORMAT_LABEL[sourceFormat]}
                    {filledShare ? ` · resampled to 1 s, ${Math.round(filledShare * 100)}% of rows filled` : ""}
                  </span>
                )}
              </div>
              <div style={{ marginTop: 12, display: "flex", alignItems: "flex-start", gap: 10, flexWrap: "wrap" }}>
                {!confirming ? (
                  <button type="button" onClick={() => setConfirming(true)} style={{ padding: "7px 14px", borderRadius: 8, background: "var(--accent)", border: "none", color: "var(--bg)", fontWeight: 600, fontSize: 12, cursor: "pointer" }}>
                    Include this log
                  </button>
                ) : (
                  <div role="dialog" aria-label="Include this log" style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 10, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 8, maxWidth: 460 }}>
                    <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.5 }}>
                      Include <span className="mono">{filename}</span> as a flight? It will be analysed with your other flights and can change their comparisons.
                    </div>
                    <textarea
                      aria-label="Reason"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      rows={2}
                      placeholder="Why (optional) — e.g. a real flight, the ground run was a test"
                      style={{ width: "100%", boxSizing: "border-box", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 12, resize: "vertical" }}
                    />
                    <div style={{ display: "flex", gap: 8 }}>
                      <button type="button" onClick={() => void include()} disabled={including} style={{ padding: "6px 12px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontWeight: 600, fontSize: 12, cursor: including ? "default" : "pointer" }}>
                        {including ? "Including…" : "Include"}
                      </button>
                      <button type="button" onClick={() => setConfirming(false)} style={{ padding: "6px 12px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 12, cursor: "pointer" }}>
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
                {includeError && <div style={{ fontSize: 11, color: "var(--severity-warning)" }}>{includeError}</div>}
              </div>
            </div>

            <div style={{ padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16 }}>
              {fa ? (
                <TimelinePanel
                  tl={tl}
                  phases={fa.phases}
                  availableChannels={pickableChannels(fa.available_channels, fa.provenance.channel_assignments)}
                  startUtc={fa.header.start_utc}
                  hasPhaseWarning={false}
                  emptyText="No timeline available for this log."
                />
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>Loading…</div>
              )}

              {fa && (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", gap: 12 }}>
                  <section style={{ background: "var(--panel)", borderRadius: 12, padding: "14px 16px" }}>
                    <h2 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 8px" }}>CAS alerts</h2>
                    {casAlerts.length === 0 ? (
                      <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No CAS alerts in this log.</div>
                    ) : (
                      <div className="mono" style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 12, color: "var(--text-secondary)" }}>
                        {casAlerts.map((a, i) => (
                          <div key={i}>{a.start_utc.slice(11, 19)} · {a.alert} · {Math.round(a.duration_s)} s</div>
                        ))}
                      </div>
                    )}
                  </section>
                  <section data-testid="log-ecu-runs" style={{ background: "var(--panel)", borderRadius: 12, padding: "14px 16px" }}>
                    <h2 style={{ fontSize: 13, fontWeight: 600, margin: "0 0 8px" }}>ENGINE ECU runs</h2>
                    <div className="mono" style={{ display: "flex", flexDirection: "column", gap: 2, fontSize: 12, color: "var(--text-secondary)" }}>
                      {byClass.map(({ cls, runs }) => (
                        <div key={cls}>
                          {ECU_CLASS_LABEL[cls]} ({runs.length}){runs.length ? ": " : ""}
                          {runs.map((r) => `${r.start_utc ? r.start_utc.slice(11, 19) : "—"} ${Math.round(r.duration_s)} s`).join(", ")}
                        </div>
                      ))}
                      <div style={{ color: "var(--text-tertiary)" }}>
                        {fa.ecu_sub_threshold_blips ?? 0} brief blip{fa.ecu_sub_threshold_blips === 1 ? "" : "s"} not counted
                      </div>
                    </div>
                  </section>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </NavShell>
  );
}
