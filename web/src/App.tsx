import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { Flights } from "./views/Flights";
import { FlightView } from "./views/FlightView";
import { Trends } from "./views/Trends";
import { Baselines } from "./views/Baselines";
import { ECU } from "./views/ECU";
import { Annotations } from "./views/Annotations";
import { Settings } from "./views/Settings";

// Spec 03 v0.6 §4: "Flights" is the log browser (this corrected a real
// nav bug — it used to point straight at single-flight detail). Import is
// no longer a destination; it folded into Flights as a drop zone (§5.1).
function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/flights" replace />} />
        <Route path="/flights" element={<Flights />} />
        <Route path="/flights/:flightId" element={<FlightView />} />
        <Route path="/trends" element={<Trends />} />
        <Route path="/baselines" element={<Baselines />} />
        <Route path="/ecu" element={<ECU />} />
        <Route path="/annotations" element={<Annotations />} />
        <Route path="/settings" element={<Settings />} />
      </Routes>
    </HashRouter>
  );
}

export default App;
