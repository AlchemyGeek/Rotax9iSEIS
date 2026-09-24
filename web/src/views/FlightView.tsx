import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { NavShell } from "../components/NavShell";
import { InsightCard } from "../components/InsightCard";
import { SeverityBadge } from "../components/SeverityBadge";
import { ChannelTimeline } from "../components/ChannelTimeline";
import { PhaseCaption } from "../components/PhaseCaption";
import { PhaseMinimap } from "../components/PhaseMinimap";
import { fixtureFlightById, flightAnalysis as fixtureFlight, insightSet as fixtureInsights, kacvSeries, sourceFilename } from "../lib/fixtures";
import { getEngineClient } from "../lib/engineClient";
import { toSeriesFixture } from "../lib/series";
import { ALL_CHANNEL_IDS, DEFAULT_ACTIVE_CHANNELS } from "../lib/channels";
import type { FlightAnalysis, Insight, InsightSeverity, InsightSet, SeriesFixture, TopicResult } from "../types/contract";

const SEVERITY_RANK: Record<InsightSeverity, number> = { limit: 0, warning: 1, watch: 2, info: 3 };
const client = getEngineClient();

// Spec 03 v0.3 §5.2: when a topic has more than one fired insight, the
// card (Analysis) and the list use the same one — its most severe.
function topTopicInsight(topic: TopicResult): Insight | null {
  if (!topic.insights.length) return null;
  return [...topic.insights].sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])[0];
}

function noInsightSummaryText(topics: TopicResult[]): string {
  const names = topics.slice(0, 2).map((t) => t.topic_id.replace(/_/g, " "));
  const remaining = topics.length - names.length;
  const namesStr = remaining > 0 ? `${names.join(", ")}, and ${remaining} other${remaining === 1 ? "" : "s"}` : names.join(" and ");
  return `${topics.length} topic${topics.length === 1 ? "" : "s"} ${topics.length === 1 ? "was" : "were"} analyzed with nothing to flag — ${namesStr}. See Analysis section for the full picture.`;
}

export function FlightView() {
  const { flightId } = useParams();
  const navigate = useNavigate();
  const [zoomWindow, setZoomWindow] = useState<[number, number] | null>(null);
  const [visibleWindow, setVisibleWindow] = useState<[number, number]>([0, 0]);
  const [highlight, setHighlight] = useState<{ start_s: number; end_s: number } | null>(null);
  const [activeChannels, setActiveChannels] = useState<string[]>(DEFAULT_ACTIVE_CHANNELS);

  const [flightAnalysis, setFlightAnalysis] = useState<FlightAnalysis>(fixtureFlight);
  const [insightSet, setInsightSet] = useState<InsightSet>(fixtureInsights);
  const [series, setSeries] = useState<SeriesFixture | null>(kacvSeries);
  const [filename, setFilename] = useState(sourceFilename(fixtureFlight.source_keys[0]));
  const [usingFixture, setUsingFixture] = useState(true);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setZoomWindow(null);
    setHighlight(null);

    async function load() {
      if (!flightId) {
        // No id in the URL: send to a real flight if one exists in this
        // workspace, otherwise fall through to the bundled fixture below.
        try {
          const flights = await client.listFlights();
          if (!cancelled && flights.length > 0) {
            navigate(`/flights/${flights[0].flight_id}`, { replace: true });
            return;
          }
        } catch {
          // server unreachable — fixture is already the current state, nothing to do
        }
        if (!cancelled) setUsingFixture(true);
        return;
      }
      setLoading(true);
      try {
        const got = await client.getFlight(flightId);
        if (cancelled) return;
        setFlightAnalysis(got.flight_analysis);
        setInsightSet(got.insight_set);
        setFilename(got.source_filename ?? got.flight_analysis.source_keys[0]);
        setUsingFixture(false);
        try {
          const s = await client.getFlightSeries(flightId, ALL_CHANNEL_IDS);
          if (!cancelled) setSeries(toSeriesFixture(flightId, s));
        } catch {
          if (!cancelled) setSeries(null); // no source log retained for this flight — show insights/analysis without a timeline
        }
      } catch {
        if (!cancelled) {
          // No live server, or this id doesn't exist there — a fixture
          // flight matching the requested id (e.g. an ECU event card
          // linking to the real KSFF flight, Spec 03 v0.9 §5.4) wins over
          // the generic KACV default, so every event card lands on its
          // own actual flight instead of a stand-in that can't show it.
          const known = fixtureFlightById(flightId);
          const fa = known?.analysis ?? fixtureFlight;
          setFlightAnalysis(fa);
          setInsightSet(known?.insightSet ?? fixtureInsights);
          setSeries(known ? known.series : kacvSeries);
          setFilename(sourceFilename(fa.source_keys[0]));
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
  }, [flightId, navigate]);

  const flatInsights = useMemo(() => {
    const items: { insight: Insight; topicId: string }[] = [];
    for (const topic of insightSet.topics) {
      for (const insight of topic.insights) items.push({ insight, topicId: topic.topic_id });
    }
    return items.sort((a, b) => SEVERITY_RANK[a.insight.severity] - SEVERITY_RANK[b.insight.severity]);
  }, [insightSet]);

  const noInsightTopics = useMemo(() => insightSet.topics.filter((t) => t.insights.length === 0), [insightSet]);

  const h = flightAnalysis.header;
  const durationMin = flightAnalysis.metrics.duration_min?.value;
  const durationStr = typeof durationMin === "number" ? `${Math.floor(durationMin / 60)}h ${Math.round(durationMin % 60)}m` : "—";
  const hasPhaseWarning = flightAnalysis.quality.some((q) => q.code === "PHASE_TAKEOFF_NOT_DETECTED");
  const fullEnd = flightAnalysis.phases.at(-1)?.end_s ?? 0;

  useEffect(() => {
    setVisibleWindow([0, flightAnalysis.phases.at(-1)?.end_s ?? 0]);
  }, [flightAnalysis]);

  function formatTimeRange(startS: number, endS: number): string {
    if (!h.start_utc) return "—";
    const base = new Date(h.start_utc);
    const fmt = (s: number) => new Date(base.getTime() + s * 1000).toISOString().slice(11, 16);
    const durMin = Math.round((endS - startS) / 60);
    return `${fmt(startS)}–${fmt(endS)} (${durMin} min)`;
  }

  function stepZoom(direction: "in" | "out") {
    const [s, e] = visibleWindow;
    const span = e - s || fullEnd;
    const center = (s + e) / 2;
    let newSpan = direction === "in" ? span * 0.5 : span * 2;
    newSpan = Math.min(Math.max(newSpan, 10), fullEnd);
    let newStart = center - newSpan / 2;
    let newEnd = center + newSpan / 2;
    if (newStart < 0) {
      newEnd -= newStart;
      newStart = 0;
    }
    if (newEnd > fullEnd) {
      newStart -= newEnd - fullEnd;
      newEnd = fullEnd;
    }
    newStart = Math.max(0, newStart);
    setZoomWindow([newStart, newEnd]);
    setVisibleWindow([newStart, newEnd]);
  }

  function handleEvidenceClick(insight: Insight) {
    for (const ev of insight.evidence) {
      if (ev.kind === "series_window") {
        setZoomWindow([ev.start_s, ev.end_s]);
        setVisibleWindow([ev.start_s, ev.end_s]);
        setHighlight({ start_s: ev.start_s, end_s: ev.end_s });
        document.getElementById("timeline")?.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      if (ev.kind === "baseline_point") {
        navigate(`/trends?metric=${ev.metric_id}&flight=${ev.flight_id}`);
        return;
      }
      if (ev.kind === "metric") {
        // No specific flight point to highlight (unlike baseline_point) —
        // just the metric's trend, in the context of this flight.
        navigate(`/trends?metric=${ev.metric_id}&flight=${flightAnalysis.flight_id}`);
        return;
      }
    }
  }

  return (
    <NavShell
      right={
        usingFixture ? (
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 20, background: "var(--panel)", border: "1px solid var(--border)" }}>
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>Sample flight — import your own logs to replace it</span>
          </div>
        ) : (
          <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 10px", borderRadius: 20, background: "var(--panel)", border: "1px solid var(--border)" }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--success)" }} />
            <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{loading ? "Loading…" : "Up to date"}</span>
          </div>
        )
      }
    >
      <div style={{ display: "flex", flexDirection: "column", width: "100%", minHeight: 0 }}>
        {/* Flight header */}
        <div style={{ flexShrink: 0, padding: "18px 24px 14px", borderBottom: "1px solid var(--border)" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 18 }}>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>{h.date}</h1>
            <span className="mono" style={{ fontSize: 13, color: "var(--text-secondary)" }}>
              {durationStr} &middot; {h.engine_hours_start ?? "—"} engine hrs &middot; {h.airport_hint ?? "—"}
            </span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 6 }}>
            <span className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>
              {filename}
            </span>
          </div>
        </div>

        {/* Body */}
        <div style={{ flexGrow: 1, display: "flex", minHeight: 0 }}>
          {/* Insight list */}
          <div style={{ width: 376, flexShrink: 0, borderRight: "1px solid var(--border)", display: "flex", flexDirection: "column", minHeight: 0 }}>
            <div style={{ padding: "16px 20px 10px", flexShrink: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600 }}>
                Insights <span style={{ color: "var(--text-tertiary)", fontWeight: 400 }}>({flatInsights.length})</span>
              </div>
            </div>
            <div style={{ flexGrow: 1, overflowY: "auto", padding: "0 16px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
              {flatInsights.map(({ insight, topicId }) => (
                <InsightCard key={insight.id} insight={insight} topicId={topicId} onClick={() => handleEvidenceClick(insight)} />
              ))}
              {flatInsights.length === 0 && noInsightTopics.length === 0 && (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>No insights fired for this flight.</div>
              )}
              {noInsightTopics.length > 0 && (
                <div style={{ background: "var(--panel)", borderRadius: 10, padding: "13px 14px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                    <div style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--severity-info)", flexShrink: 0 }} />
                    <span style={{ fontSize: 10, fontWeight: 700, letterSpacing: 0.5, color: "var(--severity-info-text)" }}>
                      no fired insights
                    </span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4 }}>
                    {noInsightSummaryText(noInsightTopics)}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Main column */}
          <div style={{ flexGrow: 1, overflowY: "auto", padding: "20px 24px", display: "flex", flexDirection: "column", gap: 16, minHeight: 0 }}>
            <div id="timeline" style={{ background: "var(--panel)", borderRadius: 12, padding: "18px 20px", flexShrink: 0 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
                <span style={{ fontSize: 13, fontWeight: 600 }}>Timeline</span>
                {series && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span className="mono" style={{ fontSize: 11, color: "var(--text-secondary)", marginRight: 4 }}>
                      {formatTimeRange(visibleWindow[0], visibleWindow[1])}
                    </span>
                    <button
                      onClick={() => stepZoom("out")}
                      style={{ width: 24, height: 24, borderRadius: 6, background: "var(--panel-control)", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 14, lineHeight: 1, cursor: "pointer" }}
                    >
                      &minus;
                    </button>
                    <button
                      onClick={() => stepZoom("in")}
                      style={{ width: 24, height: 24, borderRadius: 6, background: "var(--panel-control)", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 14, lineHeight: 1, cursor: "pointer" }}
                    >
                      +
                    </button>
                    <button
                      onClick={() => {
                        setZoomWindow([0, fullEnd]);
                        setVisibleWindow([0, fullEnd]);
                        setHighlight(null);
                      }}
                      style={{ fontSize: 11, background: "none", border: "none", color: "var(--accent)", cursor: "pointer", marginLeft: 6 }}
                    >
                      Full flight
                    </button>
                  </div>
                )}
              </div>

              {hasPhaseWarning && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    background: "rgba(234,179,8,0.1)",
                    border: "1px solid rgba(234,179,8,0.3)",
                    borderRadius: 8,
                    padding: "8px 12px",
                    marginBottom: 10,
                  }}
                >
                  <div style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--severity-watch)", flexShrink: 0 }} />
                  <span style={{ fontSize: 12 }}>
                    Phase detection didn't find a clear climb or cruise for this flight — shown below as one continuous segment.
                  </span>
                </div>
              )}

              {/* Spec 03 v0.7 §5.2: one navigational bar, not two. The
                  minimap keeps its original job (full-flight orientation,
                  drag-to-navigate); what the old standalone phase band
                  showed now lives as a tint on the chart itself, below. */}
              <PhaseMinimap
                phases={flightAnalysis.phases}
                fullEnd={fullEnd}
                windowStart={visibleWindow[0]}
                windowEnd={visibleWindow[1]}
                onNavigate={(s, e) => {
                  setZoomWindow([s, e]);
                  setVisibleWindow([s, e]);
                }}
              />

              {series ? (
                <ChannelTimeline
                  series={series}
                  activeChannels={activeChannels}
                  onToggleChannel={(id) =>
                    setActiveChannels((prev) => (prev.includes(id) ? prev.filter((c) => c !== id) : [...prev, id]))
                  }
                  phases={flightAnalysis.phases}
                  highlight={highlight}
                  zoomWindow={zoomWindow}
                  onZoomChange={(s, e) => setVisibleWindow([s, e])}
                />
              ) : (
                <div style={{ fontSize: 12, color: "var(--text-tertiary)", padding: "16px 0" }}>
                  No timeline available for this flight (its source log wasn't retained by the server).
                </div>
              )}

              <PhaseCaption
                phases={flightAnalysis.phases}
                windowStart={visibleWindow[0]}
                windowEnd={visibleWindow[1]}
                undifferentiatedNote={hasPhaseWarning ? "undifferentiated" : undefined}
              />
            </div>

            <div style={{ flexShrink: 0 }}>
              <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 10 }}>Analysis</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 10 }}>
                {insightSet.topics.map((t) => {
                  const topInsight = topTopicInsight(t);
                  const clickable = Boolean(topInsight && topInsight.evidence.length > 0);
                  const Wrapper = clickable ? "a" : "div";
                  return (
                    <Wrapper
                      key={t.topic_id}
                      href={clickable ? "#timeline" : undefined}
                      onClick={
                        clickable
                          ? (e: React.MouseEvent) => {
                              e.preventDefault();
                              if (topInsight) handleEvidenceClick(topInsight);
                            }
                          : undefined
                      }
                      style={{ display: "block", background: "var(--panel)", borderRadius: 10, padding: "13px 15px", cursor: clickable ? "pointer" : "default" }}
                    >
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>{t.topic_id.replace(/_/g, " ")}</span>
                        {topInsight && <SeverityBadge severity={topInsight.severity} size="sm" />}
                      </div>
                      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.45 }}>{t.analysis.text}</div>
                    </Wrapper>
                  );
                })}
              </div>
            </div>
          </div>
        </div>
      </div>
    </NavShell>
  );
}
