import flightAnalysisRaw from "../fixtures/flight-kacv-analysis.json";
import insightSetRaw from "../fixtures/flight-kacv-insights.json";
import fleetAnalysisRaw from "../fixtures/fleet-analysis.json";
import ruleOverboostRaw from "../fixtures/rule-overboost.json";
import seriesRaw from "../fixtures/flight-kacv-series.json";
import sourceFilenames from "../fixtures/source-filenames.json";
import ecuAnalysisRaw from "../fixtures/ecu-analysis.json";
import annotationStoreRaw from "../fixtures/annotations.json";
import appSettingsRaw from "../fixtures/app-settings.json";
import workspaceSettingsRaw from "../fixtures/workspace-settings.json";
import workspaceRegistryRaw from "../fixtures/workspace-registry.json";
import workspaceManifestRaw from "../fixtures/workspace-manifest.json";
import flightsTableRaw from "../fixtures/flights-table.json";
import ksffAnalysisRaw from "../fixtures/flight-ksff-analysis.json";
import ksffInsightsRaw from "../fixtures/flight-ksff-insights.json";
import insightRulesRaw from "../fixtures/insight-rules.json";
import type {
  AnnotationStore,
  AppSettings,
  EcuAnalysis,
  FleetAnalysis,
  FlightAnalysis,
  FlightsTableFixture,
  InsightSet,
  Phase,
  RuleOverboostFixture,
  RuleSet,
  SeriesFixture,
  TopicResult,
  WorkspaceManifest,
  WorkspaceRegistry,
  WorkspaceSettings,
} from "../types/contract";

// One real flight (log_20260423_200615_KACV.csv) and one real 37-flight
// fleet, generated from the actual engine via `slingology-eis ... --json`
// (Spec 05 §5) — not hand-authored. See CHANGELOG / BACKLOG G-series for
// the two contract gaps these fixtures work around (evidence backfill,
// no literal source filename).
//
// Exception (Spec 08 §11): the cylinder-balance data (egt1..4_deviation,
// cylinder_balance, and the cylinder_rank / egt_cyl_deviation topics) was
// added without the private logs. Cyl 4 is the real egt4_elevation per
// flight; the split across cyls 1–3 is synthetic. Everything derived from
// it was computed by the engine.
export const flightAnalysis = flightAnalysisRaw as FlightAnalysis;
export const insightSet = insightSetRaw as InsightSet;
export const fleetAnalysis = fleetAnalysisRaw as FleetAnalysis;
export const ruleOverboost = ruleOverboostRaw as RuleOverboostFixture;
// The real shipped insight_rules.json, mirrored here (Spec 03 §5.5's
// "reset to shipped defaults" comparison baseline in fixture mode too —
// no live workspace to diverge from, so resolved === shipped).
export const insightRules = insightRulesRaw as RuleSet;
export const kacvSeries = seriesRaw as SeriesFixture;

// Spec 02/03 round: ecu-analysis and flights-table generated from the real
// engine against the actual logs in data/logs/ (same "not hand-authored"
// discipline as the fixtures above); annotations/settings/workspace
// fixtures are hand-authored (no live source for those yet) but shaped
// exactly to the current spec's documents, not the earlier drafts the
// wireframes were built against.
export const ecuAnalysis = ecuAnalysisRaw as EcuAnalysis;
export const annotationStore = annotationStoreRaw as AnnotationStore;
export const appSettings = appSettingsRaw as AppSettings;
export const workspaceSettings = workspaceSettingsRaw as WorkspaceSettings;
export const workspaceRegistry = workspaceRegistryRaw as WorkspaceRegistry;
export const workspaceManifest = workspaceManifestRaw as WorkspaceManifest;
export const flightsTable = flightsTableRaw as FlightsTableFixture;

// FlightAnalysis.source_keys is a content hash, not a filename (Spec 05 §9
// contract-fit finding) — this fixture-only lookup fills the gap for
// display until Spec 01 carries the real filename. Falls back to the hash.
const SOURCE_FILENAMES: Record<string, string> = sourceFilenames;
export function sourceFilename(sourceKey: string): string {
  return SOURCE_FILENAMES[sourceKey] ?? sourceKey;
}

// ── The KSFF flight (Spec 03 v0.9 §5.4) ──────────────────────────────────
// A second real Flight view fixture, hand-authored to the current contract
// shape rather than generated (no raw KSFF log exists), specifically so the
// ECU view's one genuine oil-pressure-correlated IN_FLIGHT event links to
// its own real flight instead of the generic KACV stand-in every event
// used to fall back to — the exact bug Spec 03 v0.9 documents and fixes.
//
// Two shape quirks in the hand-authored source, reconciled here rather
// than left to drift into a second convention:
// - `phases` used {phase, start_utc, duration_s} (only the first entry's
//   start_utc is populated); every other fixture in this codebase — and
//   everything PhaseMinimap/PhaseCaption/ChannelTimeline's tint expect —
//   is {phase, start_s, end_s} on elapsed seconds. Rebuilt sequentially
//   from duration_s.
// - `insight` was singular (matching Spec 01 §8.5's own illustrative
//   sketch), but the actual engine output (and every other insight
//   fixture here, generated or hand-authored) uses a plural `insights`
//   array — real topics can fire more than one insight at once. Wrapped
//   to match.
interface RawKsffPhase {
  phase: string;
  start_utc: string | null;
  duration_s: number;
}

function normalizePhases(raw: RawKsffPhase[]): Phase[] {
  let t = 0;
  return raw.map((p) => {
    const start_s = t;
    t += p.duration_s;
    return { phase: p.phase, start_s, end_s: t };
  });
}

function normalizeTopics(raw: unknown[]): TopicResult[] {
  return (raw as (Omit<TopicResult, "insights"> & { insight: TopicResult["insights"][number] | null })[]).map(
    (t) => ({ ...t, insights: t.insight ? [t.insight] : [] })
  );
}

const ksffAnalysis: FlightAnalysis = {
  ...(ksffAnalysisRaw as unknown as FlightAnalysis),
  phases: normalizePhases((ksffAnalysisRaw as unknown as { phases: RawKsffPhase[] }).phases),
};
const ksffInsights: InsightSet = {
  ...(ksffInsightsRaw as unknown as InsightSet),
  topics: normalizeTopics((ksffInsightsRaw as unknown as { topics: unknown[] }).topics),
};

export interface FixtureFlight {
  analysis: FlightAnalysis;
  insightSet: InsightSet;
  series: SeriesFixture | null; // null renders Flight view's existing "no timeline available" state
}

// Keyed by every flight_id an ECU event / annotation / other fixture might
// link with. Both the real engine-generated id and the "fl_..." readable
// placeholder id ecu-analysis.json/annotations.json use for the *same*
// physical KACV flight resolve to the one real fixture — not a second,
// thinner mockup copy of it — so nothing downstream of that link sees a
// different (poorer) version of a flight it already has full data for.
const FIXTURE_FLIGHTS: Record<string, FixtureFlight> = {
  [flightAnalysis.flight_id]: { analysis: flightAnalysis, insightSet, series: kacvSeries },
  fl_20260423_200615_KACV: { analysis: flightAnalysis, insightSet, series: kacvSeries },
  [ksffAnalysis.flight_id]: { analysis: ksffAnalysis, insightSet: ksffInsights, series: null },
};

export function fixtureFlightById(flightId: string): FixtureFlight | null {
  return FIXTURE_FLIGHTS[flightId] ?? null;
}
