import { HashRouter, Navigate, Route, Routes, useLocation, useParams } from "react-router-dom";
import type { ReactNode } from "react";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { DataLocationGate } from "./components/DataLocation";
import { EngineGate } from "./components/EngineGate";
import { AppReset } from "./lib/appReset";
import { Flights } from "./views/Flights";
import { FlightView } from "./views/FlightView";
import { LogPreview } from "./views/LogPreview";
import { Trends } from "./views/Trends";
import { Journal } from "./views/Journal";
import { Settings } from "./views/Settings";
import { ChartSessionProvider } from "./lib/chartSession";

// One page failing to render must not take every other route down with it.
function PageBoundary({ children }: { children: ReactNode }) {
  const location = useLocation();
  return <ErrorBoundary resetKey={location.pathname + location.search}>{children}</ErrorBoundary>;
}

function SkippedRedirect() {
  const { logKey } = useParams();
  return <Navigate to={`/logs/${encodeURIComponent(logKey ?? "")}`} replace />;
}

// Spec 03 v0.6 §4: "Flights" is the log browser (this corrected a real
// nav bug — it used to point straight at single-flight detail). Import is
// no longer a destination; it folded into Flights as a drop zone (§5.1).
function App() {
  return (
    // Spec 02 v0.10 §5.8.1: an unreachable chosen data location replaces
    // every page with its notice.
    // Spec 04 v0.7 §9.5: which host, and (in the browser) the engine loading.
    <EngineGate>
    <AppReset>
    <DataLocationGate>
    <HashRouter>
      {/* Spec 07 D7: the chart's channel selection lives above the routes
          so it survives navigating away from and back to Flight view
          (e.g. via the Flights list), not just a same-route param change. */}
      <ChartSessionProvider>
        <PageBoundary>
        <Routes>
          <Route path="/" element={<Navigate to="/flights" replace />} />
          <Route path="/flights" element={<Flights />} />
          <Route path="/flights/:flightId" element={<FlightView />} />
          {/* Spec 03 v0.16 §5.9: a log the loader skipped has its own
              read-only Log preview; the old /skipped/ links redirect. */}
          <Route path="/logs/:logKey" element={<LogPreview />} />
          <Route path="/skipped/:logKey" element={<SkippedRedirect />} />
          <Route path="/trends" element={<Trends />} />
          {/* Spec 14 §4/§9 acceptance 10: Baselines is no longer a
              destination and Baselines.tsx's rule playground is retired
              (step 5, superseded by the insight card's own rule editor) —
              the URL redirects rather than 404ing for anyone with it
              bookmarked. */}
          <Route path="/baselines" element={<Navigate to="/settings?tab=reference" replace />} />
          {/* Spec 03 v0.14 §5.4: the ECU view is retired — its content is CAS event rows and a Trends panel. */}
          <Route path="/ecu" element={<Navigate to="/flights" replace />} />
          <Route path="/annotations" element={<Navigate to="/journal" replace />} />
          <Route path="/journal" element={<Journal />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
        </PageBoundary>
      </ChartSessionProvider>
    </HashRouter>
    </DataLocationGate>
    </AppReset>
    </EngineGate>
  );
}

export default App;
