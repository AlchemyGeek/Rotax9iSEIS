import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { SeverityBadge } from "../components/SeverityBadge";
import { ChannelTimeline } from "../components/ChannelTimeline";
import { PhaseCaption } from "../components/PhaseCaption";
import { flightsTable as fixtureFlights, workspaceManifest as fixtureManifest } from "../lib/fixtures";
import { getEngineClient, type IngestResult, type UploadFile } from "../lib/engineClient";
import { toSeriesFixture } from "../lib/series";
import { assignChannelColors } from "../lib/channels";
import { colors as themeColors } from "../theme/colors";
import type {
  ChannelRegistryEntry, ExclusionEntry, FlightAnalysis, FlightRowStatus, FlightTableRow,
  InsightSeverity, SeriesFixture, WorkspaceManifest,
} from "../types/contract";
import { useFilterAttention } from "../lib/filterAttention";

const client = getEngineClient();

const LEGACY_MANIFEST: WorkspaceManifest = {
  id: "legacy", name: "Workspace", engine_model: "", log_folders: [],
  schema_version: "", created_at: "", updated_at: "", engine_version_seen: [],
  flight_count: 0, storage_backend: "filesystem",
};

interface ImportProgressItem {
  filename: string;
  status: "waiting" | "analyzing" | "done" | "error";
  result?: IngestResult;
}

const PROGRESS_LABEL: Record<ImportProgressItem["status"], string> = {
  waiting: "waiting…",
  analyzing: "analyzing…",
  done: "done",
  error: "failed",
};
const CLASSIFICATION_LABEL: Record<IngestResult["classification"], string> = {
  new: "new flight",
  duplicate: "already in this workspace",
  ground_session: "ground session — no airborne phase",
  short_flight: "short flight",
  corrupt_log: "corrupt log",
};

// Spec 03 §5.1's status values, matching Spec 02 §5.5/§5.6 exactly rather
// than inventing UI-only states.
const STATUS_LABEL: Record<FlightRowStatus, string> = {
  analyzed: "Analyzed",
  needs_reanalysis: "Needs re-analysis",
  missing: "Missing log",
  folder_unreachable: "Folder unreachable",
  ground_session: "Ground session",
  unreadable: "Unreadable",
};

const STATUS_COLOR: Record<FlightRowStatus, string> = {
  analyzed: "var(--text-secondary)",
  needs_reanalysis: "var(--severity-watch)",
  missing: "var(--severity-warning)",
  folder_unreachable: "var(--severity-warning)",
  ground_session: "var(--text-tertiary)",
  unreadable: "var(--severity-limit)",
};

// Skipped logs (Spec: Workspace Flight Exclusions) — a file that never
// became a flight_id, tagged with why. Deliberately separate from
// STATUS_LABEL/STATUS_COLOR above (FlightRowStatus), which describes a
// real, analyzed flight's state, not "this was never one."
const EXCLUSION_CATEGORY_LABEL: Record<ExclusionEntry["category"], string> = {
  ground_session: "Ground session",
  short_flight: "Short flight",
  corrupt_log: "Corrupt log",
  user_defined: "User excluded",
};
const EXCLUSION_CATEGORY_COLOR: Record<ExclusionEntry["category"], string> = {
  ground_session: "var(--text-tertiary)",
  short_flight: "var(--text-tertiary)",
  corrupt_log: "var(--severity-warning)",
  user_defined: "var(--text-secondary)",
};

// Skipped-log preview has no chart session/preset machinery to draw a
// selection from (Spec 07's picker lives on Flight view, not here) — a
// fixed, small overview set is enough to answer "does this data look
// right," filtered to whatever the log actually has.
const PREVIEW_CHANNEL_IDS = ["rpm", "ias_kt", "oil_temp_f", "egt_spread_f"];

type GroupBy = "date" | "folder";

function formatDuration(min: number): string {
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function groupKeyForDate(row: FlightTableRow): string {
  const d = new Date(row.date + "T00:00:00");
  return isNaN(d.getTime()) ? row.date : d.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

function dateSortKey(dateStr: string): number {
  const t = new Date(dateStr + "T00:00:00").getTime();
  return isNaN(t) ? 0 : t;
}

function TrashIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 6h18" />
      <path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2" />
      <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
  );
}

// Import (Spec 03's old standalone destination) folds into this view as a
// banner + drop zone (§5.1) — this is the same real drag/drop + file-picker
// + live import_files() call the old Import.tsx had, not a fixture stand-in;
// dropping files still actually reaches the local server. Only the
// destination changed, not the mechanism.
export function Flights() {
  const navigate = useNavigate();
  const filterAttention = useFilterAttention();
  const [params, setParams] = useSearchParams();
  const [rows, setRows] = useState<FlightTableRow[]>(fixtureFlights.rows);
  const [manifest, setManifest] = useState(fixtureManifest);
  const [isRegistryActive, setIsRegistryActive] = useState(false);
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(false);
  const [groupBy, setGroupBy] = useState<GroupBy>("date");
  const [statusFilter, setStatusFilter] = useState<FlightRowStatus | "excluded" | null>(
    (params.get("filter") as FlightRowStatus | "excluded" | null) ?? null
  );
  const idsFilter = useMemo(() => {
    const raw = params.get("ids");
    return raw ? new Set(raw.split(",")) : null;
  }, [params]);

  const [importResults, setImportResults] = useState<IngestResult[]>([]);
  const [importing, setImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<ImportProgressItem[]>([]);
  const [importError, setImportError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [rescanning, setRescanning] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);
  const [addingFolder, setAddingFolder] = useState(false);
  const [folderPath, setFolderPath] = useState("");
  const [excludingId, setExcludingId] = useState<string | null>(null);
  const [excludeReason, setExcludeReason] = useState("");
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeMessage, setRemoveMessage] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkConfirming, setBulkConfirming] = useState(false);
  const [deletingWorkspace, setDeletingWorkspace] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  // Skipped logs (Spec: Workspace Flight Exclusions) — files that never
  // became a flight_id at all (ground session / short flight / corrupt
  // log / user-excluded). A separate list from `rows` above, which is
  // exclusively real, analyzed flights.
  const [exclusions, setExclusions] = useState<ExclusionEntry[]>([]);
  const [showSkipped, setShowSkipped] = useState(false);
  const [includingFilename, setIncludingFilename] = useState<string | null>(null);
  const [includeError, setIncludeError] = useState<string | null>(null);
  // Read-only preview of a skipped log's own data (op_preview_excluded_log
  // / op_get_excluded_log_series) — persists nothing, so it's plain local
  // state rather than anything routed through refresh()/exclusions.
  const [previewFilename, setPreviewFilename] = useState<string | null>(null);
  const [previewAnalysis, setPreviewAnalysis] = useState<FlightAnalysis | null>(null);
  const [previewSeries, setPreviewSeries] = useState<SeriesFixture>({ flight_id: "", channels: {} });
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [channelRegistry, setChannelRegistry] = useState<ChannelRegistryEntry[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    try {
      const [active, statusList, exclusionsResult] = await Promise.all([
        client.getActiveWorkspace(), client.listFlightsWithStatus(), client.listExclusions(),
      ]);
      setRows(statusList.rows);
      setManifest(active.active && active.manifest ? active.manifest : LEGACY_MANIFEST);
      setIsRegistryActive(active.active);
      setUsingFixture(false);
      setExclusions(exclusionsResult.entries);
    } catch {
      setRows(fixtureFlights.rows);
      setManifest(fixtureManifest);
      setIsRegistryActive(false);
      setUsingFixture(true);
      setExclusions([]);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    refresh().finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  // One file at a time (not one batched RPC call for the whole drop) so
  // the list below can show real per-file progress — which log is
  // actually being analyzed right now, not just one opaque spinner for
  // however long the whole batch takes.
  const runImport = useCallback(
    async (fileList: File[]) => {
      if (!fileList.length) return;
      setImporting(true);
      setImportError(null);
      setImportProgress(fileList.map((f) => ({ filename: f.name, status: "waiting" })));
      const newResults: IngestResult[] = [];
      for (let i = 0; i < fileList.length; i++) {
        const f = fileList[i];
        setImportProgress((prev) => prev.map((item, idx) => (idx === i ? { ...item, status: "analyzing" } : item)));
        try {
          const upload: UploadFile = { content: await f.arrayBuffer(), filename: f.name };
          const res = await client.importFiles([upload]);
          const result = res.results[0];
          newResults.push(result);
          setImportProgress((prev) => prev.map((item, idx) => (idx === i ? { ...item, status: "done", result } : item)));
        } catch (e) {
          setImportProgress((prev) => prev.map((item, idx) => (idx === i ? { ...item, status: "error" } : item)));
          setImportError(
            `Couldn't reach the local server (${e instanceof Error ? e.message : String(e)}). ` +
              `Run \`slingology-eis serve\` and try again.`
          );
          break;
        }
      }
      setImportResults((prev) => [...newResults, ...prev]);
      await refresh();
      setImporting(false);
    },
    [refresh]
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    runImport(Array.from(e.dataTransfer.files));
  };
  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    runImport(Array.from(e.target.files ?? []));
    e.target.value = "";
  };
  const newCount = importResults.filter((r) => r.classification === "new").length;
  const duplicateResults = importResults.filter((r) => r.classification === "duplicate");
  // Ground session / short flight / corrupt log — auto-excluded and
  // recorded to exclusions.json, never became a flight (Spec: Ground
  // Session Detection + Workspace Flight Exclusions).
  const autoExcludedResults = importResults.filter((r) =>
    r.classification === "ground_session" || r.classification === "short_flight" || r.classification === "corrupt_log"
  );

  // "Sync" (was "Rescan") — finds new/missing/moved files AND re-runs
  // analysis for any already-known flight whose stored result predates
  // the running engine (Spec 03 §5.1), one action covering both jobs
  // rather than leaving reanalysis to a separate, easy-to-forget step.
  async function handleSync() {
    setRescanning(true);
    try {
      const result = await client.scanWorkspace();
      await refresh();
      const parts: string[] = [];
      if (result.new_flight_ids.length) parts.push(`${result.new_flight_ids.length} new`);
      if (result.reanalyzed_flight_ids.length) parts.push(`${result.reanalyzed_flight_ids.length} re-analyzed`);
      if (result.recovered_flight_ids.length) parts.push(`${result.recovered_flight_ids.length} recovered`);
      if (result.now_missing_flight_ids.length) parts.push(`${result.now_missing_flight_ids.length} newly missing`);
      if (result.rematched_flight_ids.length) parts.push(`${result.rematched_flight_ids.length} moved/renamed`);
      if (result.unreachable_folders.length) parts.push(`${result.unreachable_folders.length} folder${result.unreachable_folders.length === 1 ? "" : "s"} unreachable`);
      if (result.auto_excluded.length) parts.push(`${result.auto_excluded.length} excluded (ground session/short flight/corrupt log)`);
      setSyncMessage(parts.length ? parts.join(" · ") : "No changes.");
    } catch {
      // no active workspace, or server unreachable — nothing to do beyond leaving state as-is
    } finally {
      setRescanning(false);
    }
  }

  // Deleting a workspace is permanent (every flight, exclusion, baseline,
  // and rule override in it) — the typed "DELETE" is the only gate, no
  // second modal, matching how deliberately blunt the rest of this app's
  // destructive confirmations are (see bulkConfirming above). A full
  // reload afterward matches NavShell's own switch/create handlers — no
  // cross-component store keeps Flights/NavShell/etc. in sync today.
  async function handleDeleteWorkspace() {
    if (deleteConfirmText !== "DELETE") return;
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await client.deleteWorkspace(manifest.id);
      window.location.hash = "#/flights";
      window.location.reload();
    } catch {
      setDeleteError("Delete failed — the server may be unreachable. Try again.");
      setDeleteBusy(false);
    }
  }

  // Re-locates and re-parses each skipped log's own source file for
  // date/duration/airborne minutes — real per-file I/O, so it's fetched
  // only when the Skipped panel is actually open, not on every routine
  // refresh() (which still fetches the cheap, unenriched list for the
  // chip's count).
  const fetchSkippedDetails = useCallback(async () => {
    try {
      const result = await client.listExclusions(true);
      setExclusions(result.entries);
    } catch {
      // leave whatever refresh() already put there — still correct, just unenriched
    }
  }, []);

  useEffect(() => {
    if (showSkipped) fetchSkippedDetails();
  }, [showSkipped, fetchSkippedDetails]);

  // Opens the read-only preview for a skipped log — runs the same
  // analyze_flight()/downsample used for a real flight (op_preview_
  // excluded_log / op_get_excluded_log_series), just sourced from the
  // watched-folder file on disk instead of a workspace flight_id, and
  // nothing it fetches gets persisted.
  async function handlePreviewSkippedLog(filename: string) {
    setPreviewFilename(filename);
    setPreviewAnalysis(null);
    setPreviewSeries({ flight_id: filename, channels: {} });
    setPreviewError(null);
    setPreviewLoading(true);
    try {
      const registry = channelRegistry.length > 0 ? channelRegistry : (await client.getChannelRegistry()).channels;
      if (channelRegistry.length === 0) setChannelRegistry(registry);

      const { flight_analysis } = await client.previewExcludedLog(filename);
      setPreviewAnalysis(flight_analysis);

      const ids = PREVIEW_CHANNEL_IDS.filter((id) => flight_analysis.available_channels.includes(id));
      if (ids.length > 0) {
        const raw = await client.getExcludedLogSeries(filename, ids);
        const metaFor = (id: string) => {
          const c = registry.find((r) => r.id === id);
          return c ? { label: c.label, unit: c.unit ?? "" } : undefined;
        };
        setPreviewSeries(toSeriesFixture(filename, raw, metaFor));
      }
    } catch {
      setPreviewError(`Couldn't load ${filename} — the server may be unreachable, or the file is no longer in a watched folder.`);
    } finally {
      setPreviewLoading(false);
    }
  }

  function closePreview() {
    setPreviewFilename(null);
    setPreviewAnalysis(null);
    setPreviewSeries({ flight_id: "", channels: {} });
    setPreviewError(null);
  }

  // Brings a skipped log back — for a folder-scanned file this creates
  // the flight in the same round trip (the RPC op runs a scan right
  // after the override); a browser-uploaded one has no bytes saved
  // anywhere to re-analyze from, so the override just clears the way
  // for re-uploading the same file. Only ever called from within the
  // Skipped panel, so re-fetching the enriched list after is always
  // relevant, not just the cheap one refresh() already gets.
  async function handleIncludeExcludedLog(filename: string) {
    setIncludingFilename(filename);
    setIncludeError(null);
    try {
      await client.includeExcludedLog(filename, "included from the Flights tab");
      await refresh();
      await fetchSkippedDetails();
    } catch {
      setIncludeError(`Couldn't include ${filename} — the server may be unreachable. Try again.`);
    } finally {
      setIncludingFilename(null);
    }
  }

  async function handleAddFolder() {
    if (!folderPath.trim()) return;
    try {
      await client.addLogFolder(folderPath.trim());
      setFolderPath("");
      setAddingFolder(false);
      await refresh();
    } catch {
      // leave the form open so the pilot can see it didn't take and retry
    }
  }

  async function handleExclude(flightId: string) {
    try {
      await client.excludeFlight(flightId, excludeReason.trim() || "excluded by pilot");
      setExcludingId(null);
      setExcludeReason("");
      await refresh();
    } catch {
      // server unreachable / fixture mode — nothing to persist
    }
  }

  async function handleInclude(flightId: string) {
    try {
      await client.includeFlight(flightId);
      await refresh();
    } catch {
      // server unreachable / fixture mode
    }
  }

  async function handleRemoveMany(flightIds: string[]) {
    setRemoveBusy(true);
    try {
      const res = await client.removeFlights(flightIds);
      const reappeared = res.scan_result?.new_flight_ids.filter((id) => flightIds.includes(id)) ?? [];
      setRemoveMessage(
        reappeared.length > 0
          ? `Removed, but ${reappeared.length === 1 ? "one log is" : `${reappeared.length} logs are`} still in a watched folder, so the rescan brought ${reappeared.length === 1 ? "it" : "them"} right back — delete or move the file(s) (or remove the log folder) to make removal stick.`
          : null
      );
      setRemovingId(null);
      setBulkConfirming(false);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        for (const id of flightIds) next.delete(id);
        return next;
      });
      await refresh();
    } catch {
      // server unreachable — leave state as-is, nothing was removed
    } finally {
      setRemoveBusy(false);
    }
  }

  function toggleSelected(flightId: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(flightId)) next.delete(flightId);
      else next.add(flightId);
      return next;
    });
  }

  function toggleSelectAll(rowsToToggle: FlightTableRow[]) {
    setSelectedIds((prev) => {
      const allSelected = rowsToToggle.length > 0 && rowsToToggle.every((r) => prev.has(r.flight_id));
      const next = new Set(prev);
      for (const r of rowsToToggle) {
        if (allSelected) next.delete(r.flight_id);
        else next.add(r.flight_id);
      }
      return next;
    });
  }

  const filtered = useMemo(() => {
    let out = rows;
    if (idsFilter) out = out.filter((r) => idsFilter.has(r.flight_id));
    if (statusFilter === "excluded") out = out.filter((r) => r.excluded_reason);
    else if (statusFilter) out = out.filter((r) => r.status === statusFilter);
    return out;
  }, [rows, idsFilter, statusFilter]);

  const groups = useMemo(() => {
    const map = new Map<string, FlightTableRow[]>();
    for (const row of filtered) {
      const key = groupBy === "date" ? groupKeyForDate(row) : row.log_folder || "(unknown folder)";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(row);
    }
    const entries = Array.from(map.entries());
    if (groupBy === "date") {
      // Rows arrive in list_flight_ids' hash-sorted order, not
      // chronological — insertion order alone (the old behavior here)
      // just reflected whichever month's flight happened to come first
      // in that hash order, not which month was actually most recent.
      // Newest first, both across months and within one.
      for (const [, groupRows] of entries) {
        groupRows.sort((a, b) => dateSortKey(b.date) - dateSortKey(a.date) || (b.engine_hours ?? 0) - (a.engine_hours ?? 0));
      }
      entries.sort((a, b) => dateSortKey(b[1][0].date) - dateSortKey(a[1][0].date));
    } else {
      entries.sort((a, b) => a[0].localeCompare(b[0]));
    }
    return entries;
  }, [filtered, groupBy]);

  const summary = useMemo(() => {
    const inBaselines = rows.filter((r) => r.in_baselines).length;
    const missing = rows.filter((r) => r.status === "missing").length;
    const otherAircraft = rows.filter((r) => r.different_tail_number).length;
    return { total: rows.length, inBaselines, missing, otherAircraft };
  }, [rows]);

  const statusCounts = useMemo(() => {
    const counts = new Map<FlightRowStatus, number>();
    for (const r of rows) counts.set(r.status, (counts.get(r.status) ?? 0) + 1);
    return counts;
  }, [rows]);
  const excludedCount = rows.filter((r) => r.excluded_reason).length;
  // Computed from the live `exclusions` list, not a separately-fetched
  // summary — a category count here must always agree with what's
  // actually in the list below it, including right after an Include
  // action removes one entry.
  const skippedBreakdown = useMemo(() => {
    const counts = new Map<ExclusionEntry["category"], number>();
    for (const e of exclusions) counts.set(e.category, (counts.get(e.category) ?? 0) + 1);
    return counts;
  }, [exclusions]);

  function toggleStatusFilter(s: FlightRowStatus | "excluded") {
    setShowSkipped(false);
    const next = statusFilter === s ? null : s;
    setStatusFilter(next);
    const nextParams = new URLSearchParams(params);
    if (next) nextParams.set("filter", next);
    else nextParams.delete("filter");
    setParams(nextParams, { replace: true });
  }

  // Skipped logs are a different list entirely (no flight_id), not a
  // filter over `rows` — mutually exclusive with statusFilter so the
  // page always shows exactly one table at a time.
  function toggleShowSkipped() {
    setStatusFilter(null);
    const nextParams = new URLSearchParams(params);
    nextParams.delete("filter");
    setParams(nextParams, { replace: true });
    setShowSkipped((v) => !v);
  }

  return (
    <NavShell>
      <div style={{ flexGrow: 1, overflowY: "auto", padding: "20px 28px", display: "flex", flexDirection: "column", gap: 16 }}>
        {filterAttention > 0 && (
          // Spec 09 §10.4: one line when a limit filter needs attention.
          <div
            onClick={() => navigate("/annotations")}
            style={{ cursor: "pointer", fontSize: 12, padding: "8px 12px", borderRadius: 8, background: "rgba(245,165,36,0.1)", border: "1px solid rgba(245,165,36,0.3)", color: "var(--severity-warning)" }}
          >
            {filterAttention} limit filter{filterAttention === 1 ? " is" : "s are"} breached or drifting — review on the Notes page →
          </div>
        )}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
          <div>
            <h1 style={{ margin: "0 0 4px", fontSize: 19, fontWeight: 700 }}>
              {manifest.name} {usingFixture && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}>(sample)</span>}
              {loading && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}> · loading…</span>}
            </h1>
            <div style={{ display: "flex", gap: 8, marginBottom: 6, flexWrap: "wrap", alignItems: "center" }}>
              {manifest.log_folders.map((f) => (
                <span
                  key={f.path}
                  className="mono"
                  title={f.reachable ? `last scanned ${f.last_scanned_at ?? "—"}` : "unreachable — Locate folder"}
                  style={{
                    fontSize: 11,
                    padding: "5px 10px",
                    borderRadius: 6,
                    background: f.reachable ? "var(--panel-control)" : "rgba(245,165,36,0.1)",
                    color: f.reachable ? "var(--text-secondary)" : "var(--severity-warning)",
                    border: f.reachable ? "none" : "1px solid rgba(245,165,36,0.3)",
                  }}
                >
                  {f.path}
                  {!f.reachable && " — unreachable"}
                </span>
              ))}
              {isRegistryActive && !addingFolder && (
                <button
                  onClick={() => setAddingFolder(true)}
                  style={{ fontSize: 11, padding: "5px 10px", borderRadius: 6, background: "transparent", border: "1px dashed var(--border)", color: "var(--text-tertiary)", cursor: "pointer" }}
                >
                  + Add folder
                </button>
              )}
              {addingFolder && (
                <span style={{ display: "flex", gap: 4 }}>
                  <input
                    autoFocus
                    value={folderPath}
                    onChange={(e) => setFolderPath(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAddFolder()}
                    placeholder="/path/to/logs"
                    className="mono"
                    style={{ fontSize: 11, padding: "5px 8px", borderRadius: 6, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text-primary)", width: 220 }}
                  />
                  <button onClick={handleAddFolder} style={{ fontSize: 11, padding: "5px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontWeight: 600, cursor: "pointer" }}>
                    Add
                  </button>
                  <button onClick={() => { setAddingFolder(false); setFolderPath(""); }} style={{ fontSize: 11, padding: "5px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", cursor: "pointer" }}>
                    Cancel
                  </button>
                </span>
              )}
            </div>
            <div className="mono" style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
              {summary.total} flights &middot; {summary.inBaselines} in baselines
              {summary.missing > 0 && ` · ${summary.missing} missing`}
              {summary.otherAircraft > 0 && ` · ${summary.otherAircraft} other aircraft`}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
            <button
              onClick={handleSync}
              disabled={rescanning || !isRegistryActive}
              title={!isRegistryActive ? "no active workspace with log folders to sync — create/switch to one first" : "finds new/missing/moved files and re-analyzes any flight whose result predates the current engine"}
              style={{ padding: "7px 14px", borderRadius: 8, background: "var(--panel)", border: "1px solid var(--border)", color: isRegistryActive ? "var(--text-primary)" : "var(--text-tertiary)", fontSize: 12, cursor: rescanning || !isRegistryActive ? "default" : "pointer", flexShrink: 0 }}
            >
              {rescanning ? "Syncing…" : "Sync"}
            </button>
            <button
              onClick={() => { setDeletingWorkspace(true); setDeleteConfirmText(""); setDeleteError(null); }}
              disabled={!isRegistryActive}
              title={!isRegistryActive ? "no active workspace to delete" : "permanently delete this workspace and everything in it"}
              style={{ padding: "7px 14px", borderRadius: 8, background: "transparent", border: "1px solid var(--border)", color: isRegistryActive ? "#e5484d" : "var(--text-tertiary)", fontSize: 12, cursor: isRegistryActive ? "pointer" : "default", flexShrink: 0 }}
            >
              Delete workspace
            </button>
          </div>
        </div>

        {syncMessage && (
          <div style={{ padding: "8px 14px", borderRadius: 8, background: "var(--panel)", border: "1px solid var(--border)", fontSize: 12, color: "var(--text-secondary)", display: "flex", justifyContent: "space-between" }}>
            <span>{syncMessage}</span>
            <a href="#" onClick={(e) => { e.preventDefault(); setSyncMessage(null); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
              dismiss
            </a>
          </div>
        )}

        {deletingWorkspace && (
          <div style={{ padding: "14px", borderRadius: 8, background: "var(--panel)", border: "1px solid #e5484d", fontSize: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ color: "#e5484d", fontWeight: 600 }}>
              Delete workspace "{manifest.name}"?
            </div>
            <div style={{ color: "var(--text-secondary)" }}>
              This permanently removes every flight, exclusion, baseline, and rule override in this workspace. This cannot be undone.
              Your original log files are not touched — this only deletes what SlingologyEIS derived from them, not the source CSVs on disk.
              Type <span className="mono" style={{ fontWeight: 600 }}>DELETE</span> to confirm.
            </div>
            {deleteError && <div style={{ color: "#e5484d" }}>{deleteError}</div>}
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input
                autoFocus
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleDeleteWorkspace()}
                placeholder="DELETE"
                className="mono"
                style={{ fontSize: 12, padding: "6px 10px", borderRadius: 6, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text-primary)", width: 140 }}
              />
              <button
                onClick={handleDeleteWorkspace}
                disabled={deleteConfirmText !== "DELETE" || deleteBusy}
                style={{
                  padding: "6px 12px", borderRadius: 6, border: "none", fontSize: 12, fontWeight: 600, color: "#fff",
                  background: deleteConfirmText === "DELETE" ? "#e5484d" : "var(--border)",
                  cursor: deleteConfirmText === "DELETE" && !deleteBusy ? "pointer" : "default",
                }}
              >
                {deleteBusy ? "Deleting…" : "Permanently delete"}
              </button>
              <button
                onClick={() => { setDeletingWorkspace(false); setDeleteConfirmText(""); setDeleteError(null); }}
                disabled={deleteBusy}
                style={{ padding: "6px 12px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 12, cursor: "pointer" }}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Drop zone / file picker — Import's old standalone role, now living here (§5.1) */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          style={{
            border: `2px dashed ${dragOver ? "var(--accent)" : "#2e6f64"}`,
            borderRadius: 16,
            background: "rgba(79,195,176,0.05)",
            padding: 22,
            display: "flex",
            alignItems: "center",
            gap: 14,
            flexShrink: 0,
          }}
        >
          <div style={{ width: 40, height: 40, borderRadius: "50%", background: "var(--accent-15)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 3v13m0 0l-5-5m5 5l5-5" />
              <path d="M4 18v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
            </svg>
          </div>
          <div style={{ flexGrow: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>Drop your G3X logs here</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              or{" "}
              <a href="#" onClick={(e) => { e.preventDefault(); inputRef.current?.click(); }}>
                choose files
              </a>
              {" — "}dropping a folder triggers a scan the same way Sync does.
            </div>
          </div>
          {importing && (
            <span style={{ fontSize: 12, color: "var(--text-secondary)", flexShrink: 0 }}>
              Analyzing {importProgress.filter((p) => p.status === "done" || p.status === "error").length + 1} of {importProgress.length}…
            </span>
          )}
          {!importing && newCount > 0 && (
            <span style={{ fontSize: 12, color: "var(--accent)", fontWeight: 600, flexShrink: 0 }}>
              Analyze {newCount} new flight{newCount === 1 ? "" : "s"} →
            </span>
          )}
          <input ref={inputRef} type="file" multiple accept=".csv" style={{ display: "none" }} onChange={onPick} />
        </div>
        {importProgress.length > 0 && (
          <div style={{ background: "var(--panel)", borderRadius: 12, padding: "10px 14px", flexShrink: 0 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600 }}>
                {importing ? "Importing…" : "Import finished"} — {importProgress.length} file{importProgress.length === 1 ? "" : "s"}
              </span>
              {!importing && (
                <a href="#" onClick={(e) => { e.preventDefault(); setImportProgress([]); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                  dismiss
                </a>
              )}
            </div>
            <div style={{ maxHeight: 220, overflowY: "auto", display: "flex", flexDirection: "column", gap: 3 }}>
              {importProgress.map((item, i) => (
                <div key={`${item.filename}-${i}`} className="mono" style={{ display: "flex", justifyContent: "space-between", gap: 12, fontSize: 11, padding: "3px 4px" }}>
                  <span style={{ color: item.status === "analyzing" ? "var(--text-primary)" : "var(--text-tertiary)", fontWeight: item.status === "analyzing" ? 600 : 400, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {item.filename}
                  </span>
                  <span
                    style={{
                      flexShrink: 0,
                      color:
                        item.status === "analyzing" ? "var(--accent)" :
                        item.status === "error" ? "var(--severity-limit)" :
                        item.result?.classification === "new" ? "var(--accent)" :
                        "var(--text-tertiary)",
                    }}
                  >
                    {item.status === "done" && item.result ? CLASSIFICATION_LABEL[item.result.classification] : PROGRESS_LABEL[item.status]}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
        {importError && (
          <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(229,72,77,0.1)", border: "1px solid rgba(229,72,77,0.3)", fontSize: 12 }}>
            {importError}
          </div>
        )}
        {removeMessage && (
          <div style={{ padding: "10px 14px", borderRadius: 8, background: "rgba(229,72,77,0.1)", border: "1px solid rgba(229,72,77,0.3)", fontSize: 12, display: "flex", justifyContent: "space-between", gap: 12 }}>
            <span>{removeMessage}</span>
            <a href="#" onClick={(e) => { e.preventDefault(); setRemoveMessage(null); }} style={{ fontSize: 11, color: "var(--text-tertiary)", flexShrink: 0 }}>
              dismiss
            </a>
          </div>
        )}
        {!importing && (duplicateResults.length > 0 || autoExcludedResults.length > 0) && (
          <div style={{ padding: "10px 14px", borderRadius: 8, background: "var(--panel)", border: "1px solid var(--border)", fontSize: 12, color: "var(--text-secondary)", display: "flex", flexDirection: "column", gap: 4 }}>
            {duplicateResults.length > 0 && (
              <span title={duplicateResults.map((r) => r.filename).join(", ")}>
                {duplicateResults.length} file{duplicateResults.length === 1 ? "" : "s"} skipped — already in this workspace
              </span>
            )}
            {autoExcludedResults.length > 0 && (
              <span title={autoExcludedResults.map((r) => `${r.filename}: ${r.reason}`).join("; ")}>
                {autoExcludedResults.length} file{autoExcludedResults.length === 1 ? "" : "s"} skipped — not a flight (ground session, short flight, or corrupt log; recorded in exclusions)
              </span>
            )}
          </div>
        )}

        {/* Status chips */}
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {(Object.keys(STATUS_LABEL) as FlightRowStatus[])
            .filter((s) => (statusCounts.get(s) ?? 0) > 0)
            .map((s) => (
              <button
                key={s}
                onClick={() => toggleStatusFilter(s)}
                style={{
                  padding: "5px 12px",
                  borderRadius: 20,
                  fontSize: 11,
                  fontWeight: 600,
                  cursor: "pointer",
                  border: statusFilter === s ? `1px solid ${STATUS_COLOR[s]}` : "1px solid var(--border)",
                  background: statusFilter === s ? "var(--panel-control)" : "transparent",
                  color: STATUS_COLOR[s],
                }}
              >
                {STATUS_LABEL[s]} ({statusCounts.get(s)})
              </button>
            ))}
          {excludedCount > 0 && (
            <button
              onClick={() => toggleStatusFilter("excluded")}
              style={{
                padding: "5px 12px",
                borderRadius: 20,
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
                border: statusFilter === "excluded" ? "1px solid var(--text-secondary)" : "1px solid var(--border)",
                background: statusFilter === "excluded" ? "var(--panel-control)" : "transparent",
                color: "var(--text-secondary)",
              }}
            >
              Excluded ({excludedCount})
            </button>
          )}
          {exclusions.length > 0 && (
            <button
              onClick={toggleShowSkipped}
              title="logs that were never analyzed as flights — ground sessions, short flights, corrupt logs"
              style={{
                padding: "5px 12px",
                borderRadius: 20,
                fontSize: 11,
                fontWeight: 600,
                cursor: "pointer",
                border: showSkipped ? "1px solid var(--text-tertiary)" : "1px solid var(--border)",
                background: showSkipped ? "var(--panel-control)" : "transparent",
                color: "var(--text-tertiary)",
              }}
            >
              Skipped ({exclusions.length})
            </button>
          )}
          <div style={{ flexGrow: 1 }} />
          {!showSkipped && (
          <div style={{ display: "flex", gap: 4 }}>
            {(["date", "folder"] as GroupBy[]).map((g) => (
              <button
                key={g}
                onClick={() => setGroupBy(g)}
                style={{
                  padding: "5px 12px",
                  borderRadius: 6,
                  fontSize: 11,
                  cursor: "pointer",
                  border: "1px solid var(--border)",
                  background: groupBy === g ? "var(--accent-15)" : "transparent",
                  color: groupBy === g ? "var(--accent)" : "var(--text-tertiary)",
                }}
              >
                group by {g}
              </button>
            ))}
          </div>
          )}
        </div>

        {selectedIds.size > 0 && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 14px", borderRadius: 8, background: "var(--panel)", border: "1px solid var(--border)", fontSize: 12 }}>
            <span>{selectedIds.size} selected</span>
            {bulkConfirming ? (
              <>
                <span style={{ color: "var(--text-secondary)" }}>Remove {selectedIds.size} flight{selectedIds.size === 1 ? "" : "s"}?</span>
                <button
                  onClick={() => handleRemoveMany(Array.from(selectedIds))}
                  disabled={removeBusy}
                  style={{ display: "flex", alignItems: "center", gap: 4, padding: "4px 10px", borderRadius: 6, background: "#e5484d", border: "none", color: "#fff", fontSize: 11, fontWeight: 600, cursor: removeBusy ? "default" : "pointer" }}
                >
                  {removeBusy ? "Removing…" : "Yes, remove"}
                </button>
                <button onClick={() => setBulkConfirming(false)} style={{ padding: "4px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", fontSize: 11, cursor: "pointer" }}>
                  Cancel
                </button>
              </>
            ) : (
              <button
                onClick={() => setBulkConfirming(true)}
                title="remove selected flights from the workspace, then sync"
                style={{ display: "flex", alignItems: "center", gap: 5, padding: "4px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 11, cursor: "pointer" }}
              >
                <TrashIcon size={13} /> Remove
              </button>
            )}
            <div style={{ flexGrow: 1 }} />
            <a href="#" onClick={(e) => { e.preventDefault(); setSelectedIds(new Set()); setBulkConfirming(false); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
              clear selection
            </a>
          </div>
        )}

        {!showSkipped && (statusFilter || idsFilter) && (
          <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
            Showing {filtered.length} of {rows.length} flights
            {idsFilter && " — filtered to a specific set (linked from another view)"}
            {statusFilter && (
              <>
                {" "}
                ·{" "}
                <a href="#" onClick={(e) => { e.preventDefault(); toggleStatusFilter(statusFilter); }}>
                  clear filter
                </a>
              </>
            )}
          </div>
        )}

        {/* Table, grouped */}
        {!showSkipped && (
        <div style={{ background: "var(--panel)", borderRadius: 12, padding: "6px 14px" }}>
          {groups.map(([groupName, groupRows]) => (
            <div key={groupName}>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, color: "var(--text-tertiary)", padding: "10px 10px 4px" }}>
                {groupName.toUpperCase()} ({groupRows.length})
              </div>
              <table>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    <th style={{ width: 24 }}>
                      <input
                        type="checkbox"
                        checked={groupRows.length > 0 && groupRows.every((r) => selectedIds.has(r.flight_id))}
                        ref={(el) => {
                          if (el) el.indeterminate = groupRows.some((r) => selectedIds.has(r.flight_id)) && !groupRows.every((r) => selectedIds.has(r.flight_id));
                        }}
                        onChange={() => toggleSelectAll(groupRows)}
                        title="select all in this group"
                      />
                    </th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Date / route</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Duration, engine hours</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Insights</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>In baselines</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Status</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Source</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {groupRows.map((row) => (
                    <tr key={row.flight_id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      <td onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" checked={selectedIds.has(row.flight_id)} onChange={() => toggleSelected(row.flight_id)} />
                      </td>
                      <td className="mono" onClick={() => navigate(`/flights/${row.flight_id}`)} style={{ cursor: "pointer" }}>
                        {row.date} &middot; {row.airport}
                        {row.different_tail_number && (
                          <span style={{ marginLeft: 6, fontSize: 10, color: "var(--severity-watch)" }} title="informational only — never excludes">
                            &#9992; {row.different_tail_number}
                          </span>
                        )}
                      </td>
                      <td className="mono" onClick={() => navigate(`/flights/${row.flight_id}`)} style={{ cursor: "pointer" }}>
                        {formatDuration(row.duration_min)}
                        {row.engine_hours != null && ` · ${row.engine_hours}h`}
                      </td>
                      <td onClick={() => navigate(`/flights/${row.flight_id}`)} style={{ cursor: "pointer" }}>
                        {row.insight_count > 0 && row.worst_severity ? (
                          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <SeverityBadge severity={row.worst_severity as InsightSeverity} size="sm" />
                            <span className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{row.insight_count}</span>
                          </span>
                        ) : (
                          <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>—</span>
                        )}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        {excludingId === row.flight_id ? (
                          <span style={{ display: "flex", gap: 4 }}>
                            <input
                              autoFocus
                              value={excludeReason}
                              onChange={(e) => setExcludeReason(e.target.value)}
                              onKeyDown={(e) => e.key === "Enter" && handleExclude(row.flight_id)}
                              placeholder="reason"
                              style={{ fontSize: 11, padding: "3px 6px", borderRadius: 4, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text-primary)", width: 100 }}
                            />
                            <button onClick={() => handleExclude(row.flight_id)} style={{ fontSize: 10, padding: "3px 6px", borderRadius: 4, background: "var(--accent)", border: "none", color: "var(--bg)", cursor: "pointer" }}>
                              ✓
                            </button>
                            <button onClick={() => setExcludingId(null)} style={{ fontSize: 10, padding: "3px 6px", borderRadius: 4, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", cursor: "pointer" }}>
                              ×
                            </button>
                          </span>
                        ) : row.excluded_reason ? (
                          <a href="#" onClick={(e) => { e.preventDefault(); handleInclude(row.flight_id); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }} title="click to re-include in baselines">
                            excluded — {row.excluded_reason}
                          </a>
                        ) : row.in_baselines ? (
                          <span
                            onClick={() => setExcludingId(row.flight_id)}
                            style={{ color: "var(--success)", cursor: "pointer" }}
                            title="click to exclude from baselines"
                          >
                            &#10003;
                          </span>
                        ) : (
                          <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>—</span>
                        )}
                      </td>
                      <td onClick={() => navigate(`/flights/${row.flight_id}`)} style={{ cursor: "pointer" }}>
                        <span style={{ color: STATUS_COLOR[row.status], fontWeight: row.status === "analyzed" ? 400 : 600, fontSize: 12 }}>
                          {row.status === "missing" || row.status === "folder_unreachable" ? "⚠ " : ""}
                          {STATUS_LABEL[row.status]}
                        </span>
                      </td>
                      <td className="mono" onClick={() => navigate(`/flights/${row.flight_id}`)} style={{ fontSize: 10, color: "var(--text-tertiary)", cursor: "pointer" }} title={row.log_folder}>
                        {row.filename}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        {removingId === row.flight_id ? (
                          <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
                            <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Remove?</span>
                            <button
                              onClick={() => handleRemoveMany([row.flight_id])}
                              disabled={removeBusy}
                              style={{ fontSize: 10, padding: "3px 6px", borderRadius: 4, background: "#e5484d", border: "none", color: "#fff", cursor: removeBusy ? "default" : "pointer" }}
                            >
                              {removeBusy ? "…" : "Yes"}
                            </button>
                            <button onClick={() => setRemovingId(null)} style={{ fontSize: 10, padding: "3px 6px", borderRadius: 4, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", cursor: "pointer" }}>
                              ×
                            </button>
                          </span>
                        ) : (
                          <a
                            href="#"
                            onClick={(e) => { e.preventDefault(); setRemovingId(row.flight_id); }}
                            style={{ color: "var(--text-tertiary)", display: "inline-flex" }}
                            title="remove this flight from the workspace, then sync"
                          >
                            <TrashIcon />
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)", fontSize: 13 }}>No flights match this filter.</div>
          )}
        </div>
        )}

        {/* Skipped logs (Spec: Workspace Flight Exclusions) — never became
            a flight_id; a distinct list from the table above, not a filter
            over it. */}
        {showSkipped && (
          <div style={{ background: "var(--panel)", borderRadius: 12, padding: "6px 14px" }}>
            {exclusions.length > 0 && (
              <div style={{ fontSize: 11, color: "var(--text-tertiary)", padding: "10px 10px 4px" }}>
                {([
                  ["ground_session", "ground session"],
                  ["short_flight", "short flight"],
                  ["corrupt_log", "corrupt log"],
                  ["user_defined", "user-excluded"],
                ] as const)
                  .filter(([cat]) => (skippedBreakdown.get(cat) ?? 0) > 0)
                  .map(([cat, label]) => {
                    const n = skippedBreakdown.get(cat) ?? 0;
                    return `${n} ${label}${n === 1 ? "" : "s"}`;
                  })
                  .join(" · ")}
              </div>
            )}
            {includeError && (
              <div style={{ padding: "8px 10px", fontSize: 11, color: "var(--severity-warning)" }}>{includeError}</div>
            )}
            <table>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border)" }}>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 11, color: "var(--text-tertiary)", fontWeight: 600 }}>Reason</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 11, color: "var(--text-tertiary)", fontWeight: 600 }}>Date</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 11, color: "var(--text-tertiary)", fontWeight: 600 }}>Duration</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 11, color: "var(--text-tertiary)", fontWeight: 600 }}>Airborne</th>
                  <th style={{ textAlign: "left", padding: "8px 10px", fontSize: 11, color: "var(--text-tertiary)", fontWeight: 600 }}>Source</th>
                  <th style={{ width: 90 }} />
                </tr>
              </thead>
              <tbody>
                {exclusions.map((e) => (
                  <tr
                    key={e.filename}
                    onClick={() => handlePreviewSkippedLog(e.filename)}
                    title="view this log's own flight data"
                    style={{ borderBottom: "1px solid var(--border)", cursor: "pointer" }}
                  >
                    <td style={{ padding: "8px 10px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{
                          fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 10,
                          border: `1px solid ${EXCLUSION_CATEGORY_COLOR[e.category]}`, color: EXCLUSION_CATEGORY_COLOR[e.category],
                          flexShrink: 0,
                        }}>
                          {EXCLUSION_CATEGORY_LABEL[e.category]}
                        </span>
                        <span className="mono" style={{ fontSize: 12 }}>{e.filename}</span>
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 3 }}>{e.reason}</div>
                    </td>
                    <td className="mono" style={{ padding: "8px 10px", fontSize: 11, color: "var(--text-secondary)" }}>
                      {e.date ?? "—"}
                    </td>
                    <td className="mono" style={{ padding: "8px 10px", fontSize: 11, color: "var(--text-secondary)" }}>
                      {e.duration_min != null ? `${e.duration_min}m` : "—"}
                    </td>
                    <td className="mono" style={{ padding: "8px 10px", fontSize: 11, color: "var(--text-secondary)" }}>
                      {e.airborne_min != null ? `${e.airborne_min}m` : "—"}
                    </td>
                    <td style={{ padding: "8px 10px", fontSize: 11, color: "var(--text-tertiary)" }}>
                      {e.source === "auto" ? "auto-detected" : "excluded by you"}
                    </td>
                    <td style={{ padding: "8px 10px", textAlign: "right" }}>
                      <button
                        onClick={(ev) => { ev.stopPropagation(); handleIncludeExcludedLog(e.filename); }}
                        disabled={includingFilename === e.filename}
                        title="bring this log back as a real flight"
                        style={{ padding: "4px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 11, cursor: includingFilename === e.filename ? "default" : "pointer" }}
                      >
                        {includingFilename === e.filename ? "Including…" : "Include"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {exclusions.length === 0 && (
              <div style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)", fontSize: 13 }}>Nothing skipped.</div>
            )}
          </div>
        )}
      </div>

      {previewFilename && (
        <SkippedLogPreview
          filename={previewFilename}
          analysis={previewAnalysis}
          series={previewSeries}
          loading={previewLoading}
          error={previewError}
          onClose={closePreview}
        />
      )}
    </NavShell>
  );
}

// Read-only — no picker, no presets, no chart-session (Spec 07's session
// context lives above Flight view's router and belongs to real flights
// only). Just enough to answer "does this skipped log's data look right."
function SkippedLogPreview({
  filename, analysis, series, loading, error, onClose,
}: {
  filename: string;
  analysis: FlightAnalysis | null;
  series: SeriesFixture;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  const activeChannels = useMemo(() => Object.keys(series.channels), [series]);
  const channelColors = useMemo(() => assignChannelColors(activeChannels, {}), [activeChannels]);
  const colorFor = useMemo(() => (id: string) => channelColors[id] ?? themeColors.textSecondary, [channelColors]);
  const phases = analysis?.phases ?? [];
  const windowEnd = phases.length > 0 ? phases[phases.length - 1].end_s : 0;

  return (
    <>
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 30, background: "rgba(0,0,0,0.5)" }} />
      <div
        style={{
          position: "fixed", top: "5%", left: "50%", transform: "translateX(-50%)", zIndex: 31,
          width: "min(900px, 92vw)", maxHeight: "90vh", overflowY: "auto",
          background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 12,
          boxShadow: "0 16px 48px rgba(0,0,0,0.5)", padding: 20,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 12 }}>
          <div>
            <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{filename}</div>
            <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 2 }}>
              Preview only — this log stays skipped; nothing here is saved.
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ padding: "4px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 11, cursor: "pointer" }}
          >
            Close
          </button>
        </div>

        {loading && (
          <div style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)", fontSize: 13 }}>Loading…</div>
        )}
        {error && (
          <div style={{ padding: "8px 10px", fontSize: 11, color: "var(--severity-warning)" }}>{error}</div>
        )}

        {!loading && !error && analysis && (
          <>
            <div style={{ display: "flex", gap: 20, fontSize: 12, color: "var(--text-secondary)", marginBottom: 12 }}>
              <span>Date: <span className="mono">{analysis.header.date}</span></span>
              <span>Aircraft: <span className="mono">{analysis.header.aircraft.ident ?? "unknown"}</span></span>
              <span>Duration: <span className="mono">{formatDuration(windowEnd / 60)}</span></span>
            </div>
            <PhaseCaption phases={phases} windowStart={0} windowEnd={windowEnd} />
            {activeChannels.length > 0 ? (
              <ChannelTimeline series={series} activeChannels={activeChannels} colorFor={colorFor} phases={phases} />
            ) : (
              <div style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)", fontSize: 13 }}>
                No overview channels available in this log.
              </div>
            )}
          </>
        )}
      </div>
    </>
  );
}
