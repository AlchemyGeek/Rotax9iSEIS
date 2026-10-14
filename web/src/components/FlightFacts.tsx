import { admitFacts, type FlightFact } from "../lib/flightFacts";
import type { TopicHelp } from "../types/contract";
import { TopicHelpButton } from "./TopicHelpButton";

// Spec 03 v0.16 §5.2 / Spec 10 §4.3 (D20) — the header's labelled Flight
// facts row: plain values, no badges, "—" when unavailable. Whatever it is
// handed goes through the §4.3 allow-list again, so nothing reaches this
// row without a §4.3 entry.
export function FlightFacts({ facts, help, engine, units }: {
  facts: FlightFact[];
  help?: TopicHelp;
  engine: string;
  units: "imperial" | "metric";
}) {
  const admitted = admitFacts(facts);
  return (
    <div data-testid="flight-facts" style={{ display: "flex", alignItems: "center", flexWrap: "wrap", gap: "4px 16px", marginTop: 8, fontSize: 12 }}>
      <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-tertiary)", display: "flex", alignItems: "center" }}>
        Flight facts
        <TopicHelpButton help={help} engine={engine} units={units} />
      </span>
      {admitted.map((f) => (
        <span key={f.id} data-fact={f.id} className="mono" style={{ color: "var(--text-secondary)" }}>
          <span style={{ color: "var(--text-tertiary)" }}>{f.label}:</span> {f.value}
        </span>
      ))}
    </div>
  );
}
