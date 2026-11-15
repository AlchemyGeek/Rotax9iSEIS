import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { EngineRpcError, getEngineClient } from "../../lib/engineClient";
import { ChartSessionProvider } from "../../lib/chartSession";
import { useTimeline } from "../../lib/useTimeline";
import { pickableChannels } from "../../lib/channels";
import { logviewCaption, logviewMarks, type LogViewRef } from "../../lib/notebook";
import type { FlightAnalysis, Phase } from "../../types/contract";
import { TimelinePanel } from "../TimelinePanel";
import type { EventMarker } from "../ChannelTimeline";
import { BUTTON, MUTED } from "./ui";

const client = getEngineClient();
const EMPTY_PHASES: Phase[] = [];

function clock(s: number): string {
  const t = Math.max(0, Math.round(s));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), sec = t % 60;
  return `${h > 0 ? `${h}:` : ""}${String(m).padStart(h > 0 ? 2 : 1, "0")}:${String(sec).padStart(2, "0")}`;
}

// Spec 16 §5.2 — a log-view output on the Research page: the Flight view's
// chart (channel picker, zoom, cursor read-outs) scoped to the window, with
// Open flight. A chart of its own: the app's chart selection is untouched.
// Where the flight is not in this workspace (a received notebook), or the
// chart can't be drawn, the stored SVG stands, as in Jupyter.
export function LogViewCell({ view, svgHtml }: { view: LogViewRef; svgHtml: string }) {
  const [state, setState] = useState<"loading" | "live" | "absent" | "failed">("loading");
  const [fa, setFa] = useState<FlightAnalysis | null>(null);

  useEffect(() => {
    let live = true;
    client.getFlight(view.flight).then(
      (got) => { if (live) { setFa(got.flight_analysis); setState("live"); } },
      (e) => { if (live) setState(e instanceof EngineRpcError && e.code === "NOT_FOUND" ? "absent" : "failed"); },
    );
    return () => { live = false; };
  }, [view.flight]);

  const caption = logviewCaption(view);
  if (state === "live" && fa) {
    return (
      <ChartSessionProvider initialSlots={view.channels}>
        <LiveLogView view={view} fa={fa} onFail={() => setState("failed")} />
      </ChartSessionProvider>
    );
  }
  return (
    <div data-testid="logview-static">
      <div dangerouslySetInnerHTML={{ __html: svgHtml }} />
      {state === "absent" && <div style={{ ...MUTED, marginTop: 4 }} data-testid="logview-absent">Flight not in this workspace — the chart as it was drawn ({caption}).</div>}
      {state === "loading" && <div style={MUTED}>Loading the flight…</div>}
    </div>
  );
}

function LiveLogView({ view, fa, onFail }: { view: LogViewRef; fa: FlightAnalysis; onFail: () => void }) {
  const navigate = useNavigate();
  const tl = useTimeline({ phases: fa.phases ?? EMPTY_PHASES, usingFixture: false });
  const placed = useRef(false);

  useEffect(() => {
    let cancelled = false;
    const carried = tl.beginFlight();
    (async () => {
      try {
        const [registry, presets, appSettings] = await Promise.all([client.getChannelRegistry(), client.getChartPresets(), client.getAppSettings()]);
        if (cancelled) return;
        await tl.setupLive({
          key: `logview:${view.flight}`,
          fetch: (ids) => client.getFlightSeries(view.flight, ids),
          fetchWindow: (ids, w) => client.getFlightSeries(view.flight, ids, w),
          registry, presets: presets.presets, appSettings, carried,
          isCancelled: () => cancelled,
        });
      } catch {
        if (!cancelled) onFail();
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view.flight]);

  // Scoped to the window once the chart is up.
  useEffect(() => {
    if (placed.current || !tl.hasTimeline || !tl.fullEnd) return;
    placed.current = true;
    tl.navigateTo(view.start_s, view.end_s);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tl.hasTimeline, tl.fullEnd]);

  const marks = useMemo(() => logviewMarks(view), [view]);
  const markers = useMemo<EventMarker[]>(() => marks.map((m, i) => ({ id: `mark-${i}`, n: i + 1, x_s: m.t_s, source: "limit" })), [marks]);

  function openFlight() {
    const [s, e] = tl.visibleWindow[1] > tl.visibleWindow[0] ? tl.visibleWindow : [view.start_s, view.end_s];
    const channels = tl.activeSlots.length ? tl.activeSlots : view.channels;
    navigate(`/flights/${view.flight}?window=${Math.floor(s)}-${Math.ceil(e)}&channels=${encodeURIComponent(channels.join(","))}`);
  }

  return (
    <div data-testid="logview-live">
      <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginBottom: 6 }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{logviewCaption(view)}</span>
        {view.flight_date_local && <span className="mono" style={MUTED}>{view.flight_date_local} · {clock(view.start_s)}–{clock(view.end_s)} into the flight</span>}
        <span style={{ flexGrow: 1 }} />
        <button type="button" style={BUTTON} onClick={openFlight} data-testid="open-flight">Open flight</button>
      </div>
      <TimelinePanel
        tl={tl}
        phases={fa.phases}
        availableChannels={pickableChannels(fa.available_channels, fa.provenance.channel_assignments)}
        startUtc={fa.header.start_utc}
        hasPhaseWarning={false}
        markers={markers}
        emptyText="This flight's log isn't retained here, so the chart can't be drawn."
      />
      {markers.length > 0 && (
        <div style={{ ...MUTED, marginTop: 4 }}>
          {marks.map((m, i) => <span key={i} style={{ marginRight: 12 }}>{i + 1} — {m.label} ({clock(m.t_s)})</span>)}
        </div>
      )}
    </div>
  );
}
