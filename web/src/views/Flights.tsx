import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { MixedAircraftNotice } from "../components/MixedAircraftNotice";
import { SeverityBadge } from "../components/SeverityBadge";
import { ExcludeConfirmDialog } from "../components/ExcludeDialog";
import { flightsTable as fixtureFlights, workspaceManifest as fixtureManifest } from "../lib/fixtures";
import { getEngineClient, type IngestResult, type UploadFile } from "../lib/engineClient";
import { useCapabilities } from "../lib/capabilities";
import { canKeepFolders, droppedFolders, type FolderState } from "../lib/pageFolders";
import type { FolderPicking } from "../lib/browserClient";
import { EXCLUSION_CATEGORY_COLOR, EXCLUSION_CATEGORY_LABEL } from "../lib/exclusions";
import { SOURCE_FORMAT_LABEL } from "../lib/sourceFormat";
import type {
  ExclusionEntry, FlightRowStatus, FlightTableRow, ImportInfo,
  InsightSeverity, ScanOptions, ScanProgress, ScanResult, SenderMissingFlight, WorkspaceManifest,
} from "../types/contract";
import { useFilterAttention } from "../lib/filterAttention";
import { DROP_PROMPT_THRESHOLD, plural, promptText } from "../lib/flightsSync";

const client = getEngineClient();

const LEGACY_MANIFEST: WorkspaceManifest = {
  id: "legacy", name: "Workspace", engine_model: "", log_folders: [],
  schema_version: "", created_at: "", updated_at: "", engine_version_seen: [],
  flight_count: 0, storage_backend: "filesystem",
};

// Spec 03 §5.1's status values, matching Spec 02 §5.5/§5.6 exactly rather
// than inventing UI-only states.
const STATUS_LABEL: Record<FlightRowStatus, string> = {
  analyzed: "Analyzed",
  needs_analysis: "Needs analysis",
  needs_reanalysis: "Needs re-analysis",
  missing: "Missing log",
  folder_unreachable: "Folder unreachable",
  ground_session: "Ground session",
  unreadable: "Unreadable",
};

const STATUS_COLOR: Record<FlightRowStatus, string> = {
  analyzed: "var(--text-secondary)",
  needs_analysis: "var(--accent)",
  needs_reanalysis: "var(--severity-watch)",
  missing: "var(--severity-warning)",
  folder_unreachable: "var(--severity-warning)",
  ground_session: "var(--text-tertiary)",
  unreadable: "var(--severity-limit)",
};

// Sync's progress poll (op_get_scan_progress) — turns "Syncing…" into
// "Analyzing 42/210" on a large initial sync, which is otherwise one
// opaque multi-minute wait with no indication anything is happening.
const SCAN_PHASE_LABEL: Record<NonNullable<ScanProgress["phase"]>, string> = {
  starting: "Starting",
  reading: "Reading",
  analyzing: "Analyzing",
  reanalyzing: "Re-analyzing",
};

function scanProgressText(p: ScanProgress | null): string {
  if (!p || !p.active || !p.phase) return "Syncing…";
  const label = SCAN_PHASE_LABEL[p.phase];
  if (p.current == null || p.total == null) return `${label}…`;
  return `${label} ${p.current}/${p.total}`;
}

type GroupBy = "date" | "folder";


// One banner above the table for everything transient: progress, the
// Sync / drop question, and the summary afterwards (§5.1 — never a
// permanent panel).
type Banner =
  | { kind: "progress"; text: string; detail?: string }
  | { kind: "prompt"; newLogs: number; stale: number; uploads: File[] }
  | { kind: "summary"; lines: string[] };

function rowKey(row: FlightTableRow): string {
  return row.flight_id ?? (row.source_key ? `log:${row.source_key}` : `upload:${row.upload_key}`);
}

function dateFromFilename(name: string): string {
  const m = /^log_(\d{4})(\d{2})(\d{2})_/.exec(name);
  return m ? `${m[1]}-${m[2]}-${m[3]}` : "";
}

// The analysed flights in a group — the only selectable rows.
function groupIds(rows: FlightTableRow[]): string[] {
  return rows.flatMap((r) => (r.flight_id ? [r.flight_id] : []));
}



function formatDuration(min: number): string {
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

function groupKeyForDate(row: FlightTableRow): string {
  if (!row.date) return "Undated";
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
  // Starts true (not false) so the very first render — before refresh()
  // below has resolved — renders the loading gate further down instead
  // of painting the fixture/demo rows this component's state is seeded
  // with. Only ever flips true->false once, at mount; nothing later
  // re-sets it, so the loading gate never reappears on a routine
  // refresh() (Sync, Include, etc. have their own finer-grained
  // in-progress states for that).
  const [loading, setLoading] = useState(true);
  const [groupBy, setGroupBy] = useState<GroupBy>("date");
  const [statusFilter, setStatusFilter] = useState<FlightRowStatus | "excluded" | null>(
    (params.get("filter") as FlightRowStatus | "excluded" | null) ?? null
  );
  const idsFilter = useMemo(() => {
    const raw = params.get("ids");
    return raw ? new Set(raw.split(",")) : null;
  }, [params]);

  const [importing, setImporting] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [rescanning, setRescanning] = useState(false);
  const [banner, setBanner] = useState<Banner | null>(null);
  // Dropped files the pilot said "Not now" to — they wait in this page
  // (a drop points at files; nothing is stored until they're analysed).
  const [pendingUploads, setPendingUploads] = useState<File[]>([]);
  // A Needs-analysis row the pilot clicked: it offers "Analyze this flight".
  const [offerKey, setOfferKey] = useState<string | null>(null);
  const [addLogsOpen, setAddLogsOpen] = useState(false);
  const [addingFolder, setAddingFolder] = useState(false);
  const [folderPath, setFolderPath] = useState("");
  const [excludingId, setExcludingId] = useState<string | null>(null);
  // Spec 14 §7.1 (v0.6): Include again opens the exclusion dialog in include mode.
  const [includingId, setIncludingId] = useState<string | null>(null);
  const [excludeBusy, setExcludeBusy] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [removeBusy, setRemoveBusy] = useState(false);
  const [removeMessage, setRemoveMessage] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [bulkConfirming, setBulkConfirming] = useState(false);
  const [deletingWorkspace, setDeletingWorkspace] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState("");
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  // Skipped logs (Spec 02 §5.11, Spec 03 §5.1) — files that never
  // became a flight_id at all (ground session / short flight / corrupt
  // log / user-excluded). A separate list from `rows` above, which is
  // exclusively real, analyzed flights.
  const [exclusions, setExclusions] = useState<ExclusionEntry[]>([]);
  // Spec 02 v0.11 §7.5: an imported workspace's flights whose log isn't
  // here yet, and the sender's flight list for the empty state.
  const [senderMissing, setSenderMissing] = useState<SenderMissingFlight[]>([]);
  const [importInfo, setImportInfo] = useState<ImportInfo>({ imported: false });
  const [showSkipped, setShowSkipped] = useState(false);
  const [includingFilename, setIncludingFilename] = useState<string | null>(null);
  const [includeError, setIncludeError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  // Spec 03 v0.24 §5.1 / Spec 04 §9.3: where the host can't open a folder
  // by path (the browser), Choose folder… instead of a typed path, and a
  // folder row says when the page can't supply it.
  const caps = useCapabilities();
  const byPath = caps ? caps.features.add_folder_by_path : true;
  const pageFolders = caps?.features.choose_folder ? (client as unknown as FolderPicking) : null;
  const dirInputRef = useRef<HTMLInputElement>(null);
  const [reconnecting, setReconnecting] = useState<string | null>(null);
  const [folderStates, setFolderStates] = useState<Record<string, FolderState>>({});
  const [folderError, setFolderError] = useState<string | null>(null);

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
      setSenderMissing(exclusionsResult.sender_missing ?? []);
      try {
        setImportInfo(await client.getImportInfo());
      } catch {
        setImportInfo({ imported: false });   // an older server, or not imported
      }
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

  // Which of this workspace's folders the page can supply right now.
  useEffect(() => {
    void refreshFolderStates(manifest.log_folders);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [manifest, pageFolders]);

  // One file at a time (not one batched RPC call for the whole drop) so
  // the banner can show real per-file progress.
  const runImport = useCallback(
    async (fileList: File[]) => {
      if (!fileList.length) return;
      setImporting(true);
      const newResults: IngestResult[] = [];
      let failed: string | null = null;
      for (let i = 0; i < fileList.length; i++) {
        const f = fileList[i];
        setBanner({ kind: "progress", text: `Analyzing ${i + 1} of ${fileList.length}`, detail: f.name });
        try {
          const upload: UploadFile = { content: await f.arrayBuffer(), filename: f.name };
          const res = await client.importFiles([upload]);
          newResults.push(res.results[0]);
        } catch (e) {
          failed = `Couldn't reach the local server (${e instanceof Error ? e.message : String(e)}). Run \`slingology-eis serve\` and try again.`;
          break;
        }
      }
      setPendingUploads((prev) => prev.filter((f) => !fileList.includes(f)));
      await refresh();
      setImporting(false);
      const count = (c: IngestResult["classification"][]) => newResults.filter((r) => c.includes(r.classification)).length;
      const lines = [
        count(["new"]) ? `${plural(count(["new"]), "new flight")} analyzed` : "",
        count(["duplicate"]) ? `${plural(count(["duplicate"]), "file")} skipped — already in this workspace` : "",
        count(["ground_session", "short_flight", "corrupt_log"])
          ? `${plural(count(["ground_session", "short_flight", "corrupt_log"]), "file")} skipped — not a flight (ground session, short flight, or corrupt log; recorded in Skipped)`
          : "",
        failed ?? "",
      ].filter(Boolean);
      setBanner({ kind: "summary", lines: lines.length ? lines : ["Nothing new in those files."] });
    },
    [refresh]
  );

  // Spec 03 v0.17 §5.1: a drop of one or two files analyses at once; more
  // ask first, the same question Sync asks.
  function receiveFiles(files: File[]) {
    const csvs = files.filter((f) => f.name.toLowerCase().endsWith(".csv"));
    if (!csvs.length) return;
    if (csvs.length < DROP_PROMPT_THRESHOLD) void runImport(csvs);
    else setBanner({ kind: "prompt", newLogs: csvs.length, stale: 0, uploads: csvs });
  }

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    if (pageFolders && isRegistryActive) {
      // Spec 04 §9.3: a dropped folder becomes a folder of this workspace
      // (Safari's way to add one; Chrome's too); loose files import as before.
      const dt = e.dataTransfer;
      void droppedFolders(dt).then(async (folders) => {
        if (!folders.length) { receiveFiles(files); return; }
        for (const f of folders) await pageFolders.addFolderFiles(f);
        await refresh();
      });
      return;
    }
    receiveFiles(files);
  };
  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    receiveFiles(Array.from(e.target.files ?? []));
    e.target.value = "";
  };

  // scan_workspace is one synchronous RPC that can take minutes on a big
  // batch — a cheap second RPC is polled meanwhile for per-flight progress.
  async function withScanProgress<T>(fn: () => Promise<T>): Promise<T> {
    setRescanning(true);
    const pollId = window.setInterval(() => {
      client.getScanProgress()
        .then((p) => p.active && setBanner({ kind: "progress", text: scanProgressText(p), detail: p.filename ?? undefined }))
        .catch(() => {});
    }, 400);
    try {
      return await fn();
    } finally {
      window.clearInterval(pollId);
      setRescanning(false);
    }
  }

  // Spec 03 §5.1 "Unreadable": say which logs couldn't be read and why —
  // never leave them looking like they wait for analysis.
  function unreadableLines(result: ScanResult): string[] {
    const u = result.unreadable ?? [];
    if (!u.length) return [];
    const reasons = Array.from(new Set(u.map((x) => x.reason)));
    const names = u.slice(0, 3).map((x) => x.filename).join(", ") + (u.length > 3 ? `, +${u.length - 3} more` : "");
    return [`${plural(u.length, "log")} couldn't be used: ${reasons.join(" ")} (${names})`];
  }

  function bookkeepingLines(result: ScanResult): string[] {
    const parts: string[] = [];
    if (result.recovered_flight_ids.length) parts.push(`${result.recovered_flight_ids.length} recovered`);
    if (result.now_missing_flight_ids.length) parts.push(`${result.now_missing_flight_ids.length} newly missing`);
    if (result.rematched_flight_ids.length) parts.push(`${result.rematched_flight_ids.length} moved/renamed`);
    if (result.unreachable_folders.length) parts.push(`${plural(result.unreachable_folders.length, "folder")} unreachable`);
    if (result.auto_excluded.length) parts.push(`${result.auto_excluded.length} skipped — not a flight`);
    return parts.length ? [parts.join(" · ")] : [];
  }

  // Spec 03 v0.17 §5.1: Sync discovers (moved, missing, new, stale) and
  // asks before it analyses anything.
  async function handleSync() {
    setBanner({ kind: "progress", text: "Looking for changes…" });
    try {
      const result = await withScanProgress(() => client.scanWorkspace({ analyze: false }));
      await refresh();
      const newLogs = result.pending_new_logs?.length ?? 0;
      const stale = result.pending_reanalysis_flight_ids?.length ?? 0;
      if (newLogs + stale === 0) setBanner({ kind: "summary", lines: ["No changes.", ...bookkeepingLines(result)] });
      else setBanner({ kind: "prompt", newLogs, stale, uploads: [] });
    } catch {
      setBanner(null); // no active workspace, or server unreachable
    }
  }

  // Spec 02 v0.11 §7.4 step 5: the import flow lands here with ?sync=1 —
  // the ordinary Sync confirmation for the matched flights.
  useEffect(() => {
    if (params.get("sync") !== "1") return;
    setParams((p) => { const c = new URLSearchParams(p); c.delete("sync"); return c; }, { replace: true });
    void handleSync();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Analyze now / Analyze N / a row's "Analyze this flight": the folder
  // logs and stale flights given (all when omitted), then any dropped
  // files still waiting in the browser.
  async function runAnalysis(options: ScanOptions = {}, uploads: File[] = []) {
    const hasServerWork = options.source_keys === undefined || options.source_keys.length > 0 || (options.flight_ids?.length ?? 0) > 0;
    let result: ScanResult | null = null;
    if (hasServerWork) {
      setBanner({ kind: "progress", text: "Analyzing…" });
      try {
        result = await withScanProgress(() => client.scanWorkspace(options));
      } catch {
        setBanner({ kind: "summary", lines: ["Couldn't reach the local server — nothing was analyzed."] });
        return;
      }
    }
    if (uploads.length) {
      await runImport(uploads);
      return;
    }
    await refresh();
    if (result) {
      const lines = [
        result.new_flight_ids.length ? `${plural(result.new_flight_ids.length, "new flight")} analyzed` : "",
        result.reanalyzed_flight_ids.length ? `${result.reanalyzed_flight_ids.length} re-analyzed` : "",
        ...unreadableLines(result),
        ...bookkeepingLines(result),
      ].filter(Boolean);
      setBanner({ kind: "summary", lines: lines.length ? lines : ["Nothing needed analysis."] });
    }
  }

  function answerPrompt(analyze: boolean) {
    if (banner?.kind !== "prompt") return;
    const uploads = banner.uploads;
    if (analyze) {
      void runAnalysis(uploads.length ? { source_keys: [], flight_ids: [] } : {}, uploads);
    } else {
      // Not now: the logs wait in the table as Needs analysis, with
      // Analyze N beside Sync. Dropped files wait in this page.
      setPendingUploads((prev) => [...prev, ...uploads.filter((u) => !prev.includes(u))]);
      setBanner(null);
    }
  }

  // Deleting a workspace is permanent (every flight, exclusion, reference,
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
      setSenderMissing(result.sender_missing ?? []);
    } catch {
      // leave whatever refresh() already put there — still correct, just unenriched
    }
  }, []);

  useEffect(() => {
    if (showSkipped) fetchSkippedDetails();
  }, [showSkipped, fetchSkippedDetails]);

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

  async function refreshFolderStates(folders: { folder_id?: string }[]) {
    if (!pageFolders) return;
    const next: Record<string, FolderState> = {};
    for (const f of folders) if (f.folder_id) next[f.folder_id] = await pageFolders.folderState(f.folder_id);
    setFolderStates(next);
  }

  function startAddFolder() {
    if (byPath || !pageFolders) { setAddingFolder(true); return; }
    setFolderError(null);
    if (canKeepFolders()) {
      pageFolders.chooseFolder().then(() => refresh(), (e) => { if (e?.name !== "AbortError") setFolderError(String(e?.message ?? e)); });
    } else {
      setReconnecting(null);
      dirInputRef.current?.click();
    }
  }

  async function reconnect(folderId: string) {
    if (!pageFolders) return;
    setFolderError(null);
    if (canKeepFolders()) {
      try { await pageFolders.reconnectFolder(folderId); } catch (e) { if ((e as Error)?.name !== "AbortError") setFolderError(String((e as Error)?.message ?? e)); }
      await refresh();
    } else {
      setReconnecting(folderId);
      dirInputRef.current?.click();
    }
  }

  async function onPickFolder(e: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    e.target.value = "";
    if (!files.length || !pageFolders) return;
    if (reconnecting) await pageFolders.reconnectFolder(reconnecting, files);
    else await pageFolders.addFolderFiles(files);
    setReconnecting(null);
    await refresh();
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

  async function handleExclude(flightId: string, reason: string) {
    setExcludeBusy(true);
    try {
      await client.excludeFlight(flightId, reason);
      setExcludingId(null);
      await refresh();
    } catch {
      // server unreachable / fixture mode — nothing to persist, dialog stays open
    } finally {
      setExcludeBusy(false);
    }
  }

  async function handleInclude(flightId: string) {
    setExcludeBusy(true);
    try {
      await client.includeFlight(flightId);
      setIncludingId(null);
      await refresh();
    } catch {
      // server unreachable / fixture mode — dialog stays open
    } finally {
      setExcludeBusy(false);
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

  // Only analysed flights can be selected (remove); a log waiting for
  // analysis has nothing to remove yet.
  function toggleSelectAll(rowsToToggle: FlightTableRow[]) {
    const ids = rowsToToggle.flatMap((r) => (r.flight_id ? [r.flight_id] : []));
    setSelectedIds((prev) => {
      const allSelected = ids.length > 0 && ids.every((id) => prev.has(id));
      const next = new Set(prev);
      for (const id of ids) {
        if (allSelected) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }

  // Server rows plus dropped files waiting in this page (Spec 03 v0.17).
  const allRows = useMemo<FlightTableRow[]>(() => [
    ...rows,
    ...pendingUploads.map((f): FlightTableRow => ({
      flight_id: null, upload_key: f.name, date: dateFromFilename(f.name), airport: "—", duration_min: null,
      engine_hours: null, insight_count: null, worst_severity: null, in_baselines: null, status: "needs_analysis",
      filename: f.name, log_folder: "dropped files",
    })),
  ], [rows, pendingUploads]);
  const queue = {
    newLogs: allRows.filter((r) => r.status === "needs_analysis").length,
    stale: allRows.filter((r) => r.status === "needs_reanalysis").length,
  };

  const filtered = useMemo(() => {
    let out = allRows;
    if (idsFilter) out = out.filter((r) => r.flight_id !== null && idsFilter.has(r.flight_id));
    if (statusFilter === "excluded") out = out.filter((r) => r.excluded_reason);
    else if (statusFilter) out = out.filter((r) => r.status === statusFilter);
    return out;
  }, [allRows, idsFilter, statusFilter]);

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
    const flights = rows.filter((r) => r.flight_id !== null);
    const inBaselines = flights.filter((r) => r.in_baselines).length;
    const missing = flights.filter((r) => r.status === "missing").length;
    const otherAircraft = flights.filter((r) => r.different_tail_number).length;
    return { total: flights.length, inBaselines, missing, otherAircraft };
  }, [rows]);

  const statusCounts = useMemo(() => {
    const counts = new Map<FlightRowStatus, number>();
    for (const r of allRows) counts.set(r.status, (counts.get(r.status) ?? 0) + 1);
    return counts;
  }, [allRows]);
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

  // See the loading state's comment above — avoids flashing the fixture
  // workspace's sample rows on every navigation to this page before the
  // real workspace's data has actually loaded.
  if (loading) {
    return (
      <NavShell>
        <div style={{ flexGrow: 1, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ color: "var(--text-tertiary)", fontSize: 13 }}>Loading…</span>
        </div>
      </NavShell>
    );
  }

  // Spec 03 v0.17 §5.1: a log found but not analysed has no results —
  // its date comes from the file name, Insights and In reference read "—",
  // and clicking it offers "Analyze this flight" instead of opening an
  // empty Flight view.
  // Spec 03 §5.1 "Unreadable": the log, its status and why — no "Analyze"
  // offer, since analysing it again would fail the same way.
  function unreadableRow(row: FlightTableRow) {
    const dash = <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>—</span>;
    return (
      <tr key={rowKey(row)} data-testid="unreadable-row" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <td />
        <td className="mono">{row.date || "—"} &middot; —</td>
        <td>{dash}</td>
        <td>{dash}</td>
        <td>{dash}</td>
        <td>
          <span style={{ color: STATUS_COLOR[row.status], fontWeight: 600, fontSize: 12 }}>{STATUS_LABEL[row.status]}</span>
          {row.unreadable_reason && (
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 2, maxWidth: 320 }}>{row.unreadable_reason}</div>
          )}
        </td>
        <td className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }} title={row.log_folder}>{row.filename}</td>
        <td />
      </tr>
    );
  }

  function pendingRow(row: FlightTableRow) {
    const key = rowKey(row);
    const offered = offerKey === key;
    const upload = row.upload_key ? pendingUploads.find((f) => f.name === row.upload_key) : undefined;
    const dash = <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>—</span>;
    return (
      <tr key={key} data-testid="pending-row" onClick={() => setOfferKey(offered ? null : key)} style={{ borderBottom: "1px solid var(--border-subtle)", cursor: "pointer" }}>
        <td />
        <td className="mono">{row.date || "—"} &middot; —</td>
        <td>{dash}</td>
        <td>{dash}</td>
        <td>{dash}</td>
        <td><span style={{ color: STATUS_COLOR[row.status], fontWeight: 600, fontSize: 12 }}>{STATUS_LABEL[row.status]}</span></td>
        <td className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }} title={row.log_folder}>{row.filename}</td>
        <td onClick={(e) => e.stopPropagation()}>
          {offered && (
            <button
              type="button"
              disabled={rescanning || importing}
              onClick={() => {
                setOfferKey(null);
                void runAnalysis({ source_keys: row.source_key ? [row.source_key] : [], flight_ids: [] }, upload ? [upload] : []);
              }}
              style={{ fontSize: 11, padding: "4px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontWeight: 600, cursor: "pointer", whiteSpace: "nowrap" }}
            >
              Analyze this flight
            </button>
          )}
        </td>
      </tr>
    );
  }

  const hasFolders = manifest.log_folders.length > 0;
  const queueCount = queue.newLogs + queue.stale;
  const BUTTON: React.CSSProperties = { padding: "7px 14px", borderRadius: 8, background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 12, cursor: "pointer", flexShrink: 0 };

  const folderForm = (
    <span style={{ display: "flex", gap: 4 }}>
      <input
        autoFocus
        aria-label="Folder path"
        value={folderPath}
        onChange={(e) => setFolderPath(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleAddFolder()}
        placeholder="/path/to/logs"
        className="mono"
        style={{ fontSize: 11, padding: "5px 8px", borderRadius: 6, background: "var(--bg)", border: "1px solid var(--border)", color: "var(--text-primary)", width: 260 }}
      />
      <button type="button" onClick={handleAddFolder} style={{ fontSize: 11, padding: "5px 10px", borderRadius: 6, background: "var(--accent)", border: "none", color: "var(--bg)", fontWeight: 600, cursor: "pointer" }}>
        Add
      </button>
      <button type="button" onClick={() => { setAddingFolder(false); setFolderPath(""); }} style={{ fontSize: 11, padding: "5px 10px", borderRadius: 6, background: "transparent", border: "1px solid var(--border)", color: "var(--text-secondary)", cursor: "pointer" }}>
        Cancel
      </button>
    </span>
  );

  return (
    <NavShell>
      <div
        // Spec 03 v0.17 §5.1: once the workspace has a folder, a drop
        // anywhere on the page is still accepted.
        onDragOver={(e) => { if (hasFolders) { e.preventDefault(); setDragOver(true); } }}
        onDragLeave={(e) => { if (e.currentTarget === e.target) setDragOver(false); }}
        onDrop={(e) => { if (hasFolders) onDrop(e); }}
        data-testid="flights-page"
        style={{ flexGrow: 1, overflowY: "auto", padding: "20px 28px", display: "flex", flexDirection: "column", gap: 16, outline: dragOver && hasFolders ? "2px dashed var(--accent)" : "none", outlineOffset: -6 }}
      >
        <input ref={inputRef} type="file" multiple accept=".csv" style={{ display: "none" }} onChange={onPick} data-testid="file-input" />
        {pageFolders && (
          <input ref={dirInputRef} type="file" multiple style={{ display: "none" }} onChange={onPickFolder} data-testid="folder-input"
            {...{ webkitdirectory: "" }} />
        )}
        {folderError && <div role="alert" style={{ fontSize: 12, color: "var(--severity-warning)" }}>{folderError}</div>}
        {filterAttention > 0 && (
          // Spec 09 §10.4: one line when a limit filter needs attention.
          <div
            onClick={() => navigate("/annotations")}
            style={{ cursor: "pointer", fontSize: 12, padding: "8px 12px", borderRadius: 8, background: "rgba(245,165,36,0.1)", border: "1px solid rgba(245,165,36,0.3)", color: "var(--severity-warning)" }}
          >
            {filterAttention} limit filter{filterAttention === 1 ? " is" : "s are"} breached or drifting — review on the Notes page →
          </div>
        )}
        <MixedAircraftNotice usingFixture={usingFixture} />
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
          <div>
            <h1 style={{ margin: "0 0 4px", fontSize: 19, fontWeight: 700 }}>
              {manifest.name} {usingFixture && <span style={{ fontSize: 12, fontWeight: 400, color: "var(--text-tertiary)" }}>(sample)</span>}
            </h1>
            <div style={{ display: "flex", gap: 8, marginBottom: 6, flexWrap: "wrap", alignItems: "center" }}>
              {manifest.log_folders.map((f) => {
                const pageState = f.folder_id ? folderStates[f.folder_id] : undefined;
                const offline = pageState ? pageState !== "connected" : !f.reachable;
                return (
                  <span
                    key={f.folder_id ?? f.path}
                    className="mono"
                    data-testid="folder-row"
                    title={!offline ? `last scanned ${f.last_scanned_at ?? "—"}` : pageState ? undefined : "unreachable — Locate folder"}
                    style={{
                      fontSize: 11,
                      padding: "5px 10px",
                      borderRadius: 6,
                      background: !offline ? "var(--panel-control)" : "rgba(245,165,36,0.1)",
                      color: !offline ? "var(--text-secondary)" : "var(--severity-warning)",
                      border: !offline ? "none" : "1px solid rgba(245,165,36,0.3)",
                      display: "inline-flex", gap: 8, alignItems: "center",
                    }}
                  >
                    {f.path}
                    {!pageState && !f.reachable && " — unreachable"}
                    {pageState === "needs_permission" && (
                      <button type="button" onClick={() => void reconnect(f.folder_id!)} style={{ fontSize: 11, padding: "1px 8px", borderRadius: 5, border: "1px solid var(--border)", background: "var(--panel)", color: "var(--text-primary)", cursor: "pointer" }}>
                        Allow access
                      </button>
                    )}
                    {pageState === "not_connected" && (
                      <button type="button" onClick={() => void reconnect(f.folder_id!)} style={{ fontSize: 11, padding: "1px 8px", borderRadius: 5, border: "1px solid var(--border)", background: "var(--panel)", color: "var(--text-primary)", cursor: "pointer" }}>
                        Not connected — reconnect
                      </button>
                    )}
                  </span>
                );
              })}
              {hasFolders && addingFolder && folderForm}
            </div>
            <div className="mono" style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
              {summary.total} flights &middot; {summary.inBaselines} in reference
              {summary.missing > 0 && ` · ${summary.missing} missing`}
              {summary.otherAircraft > 0 && ` · ${summary.otherAircraft} other aircraft`}
            </div>
          </div>
          <div style={{ display: "flex", gap: 8, flexShrink: 0, alignItems: "flex-start" }}>
            {queueCount > 0 && !rescanning && !importing && (
              <button
                type="button"
                onClick={() => void runAnalysis({}, pendingUploads)}
                title={`${plural(queue.newLogs, "log")} not analyzed yet, ${plural(queue.stale, "flight")} needing re-analysis`}
                style={{ ...BUTTON, background: "var(--accent)", border: "none", color: "var(--bg)", fontWeight: 600 }}
              >
                Analyze {queueCount}
              </button>
            )}
            {hasFolders && isRegistryActive && (
              <span style={{ position: "relative" }}>
                <button type="button" onClick={() => setAddLogsOpen((v) => !v)} style={BUTTON} aria-expanded={addLogsOpen}>
                  Add logs…
                </button>
                {addLogsOpen && (
                  <div role="menu" style={{ position: "absolute", right: 0, top: "calc(100% + 6px)", zIndex: 10, background: "var(--panel-control)", border: "1px solid var(--border)", borderRadius: 10, padding: 10, width: 260, display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
                    <button type="button" role="menuitem" onClick={() => { setAddLogsOpen(false); inputRef.current?.click(); }} style={{ ...BUTTON, textAlign: "left" }}>
                      Choose log files…
                    </button>
                    <button type="button" role="menuitem" onClick={() => { setAddLogsOpen(false); startAddFolder(); }} style={{ ...BUTTON, textAlign: "left" }}>
                      {byPath ? "Add a folder…" : "Choose folder…"}
                    </button>
                    <div style={{ fontSize: 11, color: "var(--text-tertiary)", lineHeight: 1.4 }}>
                      Or drop log files anywhere on this page.
                    </div>
                  </div>
                )}
              </span>
            )}
            <button
              type="button"
              onClick={handleSync}
              disabled={rescanning || !isRegistryActive}
              title={!isRegistryActive ? "no active workspace with log folders to sync — create/switch to one first" : "looks for new, moved, missing and out-of-date logs, then asks before analysing"}
              style={{ ...BUTTON, color: isRegistryActive ? "var(--text-primary)" : "var(--text-tertiary)", cursor: rescanning || !isRegistryActive ? "default" : "pointer" }}
            >
              {rescanning ? "Syncing…" : "Sync"}
            </button>
            <button
              type="button"
              onClick={() => { setDeletingWorkspace(true); setDeleteConfirmText(""); setDeleteError(null); }}
              disabled={!isRegistryActive}
              title={!isRegistryActive ? "no active workspace to delete" : "permanently delete this workspace and everything in it"}
              style={{ ...BUTTON, background: "transparent", color: isRegistryActive ? "#e5484d" : "var(--text-tertiary)", cursor: isRegistryActive ? "pointer" : "default" }}
            >
              Delete workspace
            </button>
          </div>
        </div>

        {deletingWorkspace && (
          <div style={{ padding: "14px", borderRadius: 8, background: "var(--panel)", border: "1px solid #e5484d", fontSize: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ color: "#e5484d", fontWeight: 600 }}>
              Delete workspace "{manifest.name}"?
            </div>
            <div style={{ color: "var(--text-secondary)" }}>
              This permanently removes every flight, exclusion, reference, and rule override in this workspace. This cannot be undone.
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

        {/* Spec 03 v0.17 §5.1: with no folders, the page is the onboarding
            surface — drop zone / file picker and Add folder. */}
        {!hasFolders && importInfo.imported && (
          // Spec 02 v0.11 §7.4 step 3: imported, logs not linked yet.
          <div data-testid="link-logs-empty" style={{ background: "var(--panel)", borderRadius: 12, padding: "16px 18px", display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ fontSize: 14, fontWeight: 700 }}>Link your logs to see this workspace's analysis</div>
            <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
              Imported from {importInfo.provenance?.workspace_name ?? "another workspace"}. Add the folder that holds your copies of its logs (below); file names and folder layout don't matter.
            </div>
            <div style={{ maxHeight: 220, overflowY: "auto", display: "flex", flexDirection: "column", gap: 2 }}>
              {(importInfo.flights ?? []).map((f) => (
                <div key={f.flight_id} className="mono" style={{ fontSize: 11, color: "var(--text-secondary)", display: "flex", gap: 10 }}>
                  <span>{f.date ?? "—"}</span>
                  <span>{f.airport_hint ?? ""}</span>
                  <span>{f.duration_min != null ? `${Math.round(f.duration_min)} min` : ""}</span>
                  <span style={{ color: "var(--text-tertiary)" }}>{f.sender_filename ?? ""}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        {!hasFolders && (
          <div
            data-testid="onboarding-drop"
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={onDrop}
            style={{
              border: `2px dashed ${dragOver ? "var(--accent)" : "#2e6f64"}`, borderRadius: 16, background: "rgba(79,195,176,0.05)",
              padding: 22, display: "flex", alignItems: "center", gap: 14, flexShrink: 0, flexWrap: "wrap",
            }}
          >
            <div style={{ width: 40, height: 40, borderRadius: "50%", background: "var(--accent-15)", display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
              <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M12 3v13m0 0l-5-5m5 5l5-5" />
                <path d="M4 18v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
              </svg>
            </div>
            <div style={{ flexGrow: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 700 }}>Drop your engine logs here</div>
              <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>Garmin G3X (SD card or Garmin Pilot) or Garmin AXIS exports</div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                or{" "}
                <a href="#" onClick={(e) => { e.preventDefault(); inputRef.current?.click(); }}>choose files</a>
                {isRegistryActive && <> — or add the folder you keep them in, and the app will keep it in sync.</>}
              </div>
            </div>
            {isRegistryActive && (addingFolder ? folderForm : (
              <button type="button" onClick={startAddFolder} style={{ ...BUTTON, fontWeight: 600 }}>{byPath ? "Add folder" : "Choose folder…"}</button>
            ))}
          </div>
        )}

        {/* One transient banner: progress, the Sync / drop question, the summary. */}
        {banner && (
          <div
            role={banner.kind === "prompt" ? "dialog" : "status"}
            aria-label={banner.kind === "prompt" ? "Analyze now?" : undefined}
            data-testid="flights-banner"
            style={{ padding: "10px 14px", borderRadius: 8, background: "var(--panel)", border: banner.kind === "prompt" ? "1px solid var(--accent)" : "1px solid var(--border)", fontSize: 12, color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}
          >
            {banner.kind === "progress" && (
              <span>
                {banner.text}
                {banner.detail && <span className="mono" style={{ color: "var(--text-tertiary)" }}> — {banner.detail}</span>}
              </span>
            )}
            {banner.kind === "prompt" && (
              <>
                <span style={{ color: "var(--text-primary)" }}>
                  {promptText(banner.newLogs, banner.stale)}
                </span>
                <span style={{ flexGrow: 1 }} />
                <button type="button" onClick={() => answerPrompt(true)} style={{ ...BUTTON, padding: "5px 12px", background: "var(--accent)", border: "none", color: "var(--bg)", fontWeight: 600 }}>
                  Analyze now
                </button>
                <button type="button" onClick={() => answerPrompt(false)} style={{ ...BUTTON, padding: "5px 12px", background: "transparent" }}>
                  Not now
                </button>
              </>
            )}
            {banner.kind === "summary" && (
              <>
                <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                  {banner.lines.map((l) => <span key={l}>{l}</span>)}
                </span>
                <span style={{ flexGrow: 1 }} />
                <a href="#" onClick={(e) => { e.preventDefault(); setBanner(null); }} style={{ fontSize: 11, color: "var(--text-tertiary)" }}>dismiss</a>
              </>
            )}
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
              Skipped ({exclusions.length + senderMissing.length})
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
                        checked={groupIds(groupRows).length > 0 && groupIds(groupRows).every((id) => selectedIds.has(id))}
                        ref={(el) => {
                          const ids = groupIds(groupRows);
                          if (el) el.indeterminate = ids.some((id) => selectedIds.has(id)) && !ids.every((id) => selectedIds.has(id));
                        }}
                        onChange={() => toggleSelectAll(groupRows)}
                        title="select all in this group"
                      />
                    </th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Date / route</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Duration, engine hours</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Insights</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>In reference</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Status</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Source</th>
                    <th style={{ color: "var(--text-tertiary)", fontWeight: 500 }}></th>
                  </tr>
                </thead>
                <tbody>
                  {groupRows.map((row) => {
                    if (row.flight_id === null) return row.status === "unreadable" ? unreadableRow(row) : pendingRow(row);
                    const fid = row.flight_id;
                    return (
                    <tr key={fid} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      <td onClick={(e) => e.stopPropagation()}>
                        <input type="checkbox" checked={selectedIds.has(fid)} onChange={() => toggleSelected(fid)} />
                      </td>
                      <td className="mono" onClick={() => navigate(`/flights/${fid}`)} style={{ cursor: "pointer" }}>
                        {row.date} &middot; {row.airport}
                        {row.different_tail_number && (
                          <span style={{ marginLeft: 6, fontSize: 10, color: "var(--severity-watch)" }} title="informational only — never excludes">
                            &#9992; {row.different_tail_number}
                          </span>
                        )}
                      </td>
                      <td className="mono" onClick={() => navigate(`/flights/${fid}`)} style={{ cursor: "pointer" }}>
                        {row.duration_min != null ? formatDuration(row.duration_min) : "—"}
                        {row.engine_hours != null && ` · ${row.engine_hours}h`}
                      </td>
                      <td onClick={() => navigate(`/flights/${fid}`)} style={{ cursor: "pointer" }}>
                        {(row.insight_count ?? 0) > 0 && row.worst_severity ? (
                          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
                            <SeverityBadge severity={row.worst_severity as InsightSeverity} size="sm" />
                            <span className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{row.insight_count}</span>
                          </span>
                        ) : (
                          <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>—</span>
                        )}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        {row.excluded_reason ? (
                          <span
                            onClick={() => setIncludingId(fid)}
                            style={{ color: "var(--text-tertiary)", cursor: "pointer" }}
                            title={`excluded — ${row.excluded_reason} — click to include in reference again`}
                          >
                            &#10007;
                          </span>
                        ) : row.in_baselines ? (
                          <span
                            onClick={() => setExcludingId(fid)}
                            style={{ color: "var(--success)", cursor: "pointer" }}
                            title="click to exclude from reference"
                          >
                            &#10003;
                          </span>
                        ) : (
                          <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>—</span>
                        )}
                      </td>
                      <td onClick={() => navigate(`/flights/${fid}`)} style={{ cursor: "pointer" }}>
                        <span style={{ color: STATUS_COLOR[row.status], fontWeight: row.status === "analyzed" ? 400 : 600, fontSize: 12 }}>
                          {row.status === "missing" || row.status === "folder_unreachable" ? "⚠ " : ""}
                          {STATUS_LABEL[row.status]}
                        </span>
                      </td>
                      <td className="mono" onClick={() => navigate(`/flights/${fid}`)} style={{ fontSize: 10, color: "var(--text-tertiary)", cursor: "pointer" }} title={row.log_folder}>
                        {row.source_format && SOURCE_FORMAT_LABEL[row.source_format] && (
                          // Spec 03 v0.22 §5.1: the Source column names the format.
                          <span data-testid="source-format" style={{ fontFamily: "inherit", fontSize: 10, color: "var(--text-secondary)", marginRight: 6 }}>
                            {SOURCE_FORMAT_LABEL[row.source_format]}
                          </span>
                        )}
                        {row.filename}
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        {removingId === fid ? (
                          <span style={{ display: "flex", gap: 4, alignItems: "center" }}>
                            <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>Remove?</span>
                            <button
                              onClick={() => handleRemoveMany([fid])}
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
                            onClick={(e) => { e.preventDefault(); setRemovingId(fid); }}
                            style={{ color: "var(--text-tertiary)", display: "inline-flex" }}
                            title="remove this flight from the workspace, then sync"
                          >
                            <TrashIcon />
                          </a>
                        )}
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)", fontSize: 13 }}>No flights match this filter.</div>
          )}
        </div>
        )}

        {/* Skipped logs (Spec 02 §5.11, Spec 03 §5.1) — never became
            a flight_id; a distinct list from the table above, not a filter
            over it. */}
        {showSkipped && (
          <div style={{ background: "var(--panel)", borderRadius: 12, padding: "6px 14px" }}>
            {exclusions.length + senderMissing.length > 0 && (
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
                  .concat((skippedBreakdown.get("not_in_sender") ?? 0) > 0 ? [`${skippedBreakdown.get("not_in_sender")} not in the sender's workspace`] : [])
                  .concat(senderMissing.length > 0 ? [`${senderMissing.length} in the sender's workspace, log not found`] : [])
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
                    onClick={() => navigate(`/logs/${encodeURIComponent(e.filename)}`)}
                    title="preview this log"
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
                {senderMissing.map((m) => (
                  // No actions: it resolves when the log is added (Spec 03 v0.19 §5.8).
                  <tr key={`sender-${m.flight_id}`} data-testid="sender-missing-row" style={{ borderBottom: "1px solid var(--border)" }}>
                    <td style={{ padding: "8px 10px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <span style={{ fontSize: 10, fontWeight: 700, padding: "2px 8px", borderRadius: 10, border: "1px solid var(--severity-watch)", color: "var(--severity-watch)", flexShrink: 0 }}>
                          {m.reason}
                        </span>
                        <span className="mono" style={{ fontSize: 12 }}>{m.sender_filename ?? "—"}</span>
                      </div>
                      <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 3 }}>Ask the sender for this log; it is added when found.</div>
                    </td>
                    <td className="mono" style={{ padding: "8px 10px", fontSize: 11, color: "var(--text-secondary)" }}>{m.date ?? "—"}</td>
                    <td className="mono" style={{ padding: "8px 10px", fontSize: 11, color: "var(--text-secondary)" }}>—</td>
                    <td className="mono" style={{ padding: "8px 10px", fontSize: 11, color: "var(--text-secondary)" }}>—</td>
                    <td style={{ padding: "8px 10px", fontSize: 11, color: "var(--text-tertiary)" }}>{m.airport_hint ?? ""}</td>
                    <td />
                  </tr>
                ))}
              </tbody>
            </table>
            {exclusions.length === 0 && senderMissing.length === 0 && (
              <div style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)", fontSize: 13 }}>Nothing skipped.</div>
            )}
          </div>
        )}
      </div>
      {includingId && (
        <ExcludeConfirmDialog
          mode="include"
          flightId={includingId}
          flightLabel={rows.find((r) => r.flight_id === includingId)?.date ?? "this flight"}
          busy={excludeBusy}
          onCancel={() => setIncludingId(null)}
          onConfirm={() => handleInclude(includingId)}
        />
      )}
      {excludingId && (
        <ExcludeConfirmDialog
          flightId={excludingId}
          flightLabel={rows.find((r) => r.flight_id === excludingId)?.date ?? "this flight"}
          busy={excludeBusy}
          onCancel={() => setExcludingId(null)}
          onConfirm={(reason) => handleExclude(excludingId, reason)}
        />
      )}
    </NavShell>
  );
}
