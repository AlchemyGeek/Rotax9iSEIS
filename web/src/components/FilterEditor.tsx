import { useEffect, useMemo, useState } from "react";
import { getEngineClient } from "../lib/engineClient";
import type { FilterMagnitudeMode, FilterPreview, FilterProposal, LimitFilter, LimitFilterDraft } from "../types/contract";

const client = getEngineClient();

const MODE_LABEL: Record<FilterMagnitudeMode, string> = {
  absolute: "absolute",
  percent: "% of limit",
  z: "z vs. reference",
};

function fmt(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "—" : v.toFixed(digits);
}

const inputStyle: React.CSSProperties = {
  width: 80,
  background: "var(--bg)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  padding: "5px 8px",
  color: "var(--text-primary)",
  fontSize: 12,
};

const buttonStyle = (primary: boolean, enabled = true): React.CSSProperties => ({
  padding: "5px 11px",
  borderRadius: 6,
  background: primary ? "var(--accent)" : "transparent",
  border: primary ? "none" : "1px solid var(--border)",
  color: primary ? "var(--bg)" : "var(--text-secondary)",
  fontSize: 11,
  fontWeight: primary ? 600 : 400,
  cursor: enabled ? "pointer" : "default",
  opacity: enabled ? 1 : 0.5,
});

// Spec 09 §12.1: the inline "Filter this limit…" editor. Pre-filled from
// propose_limit_filter; magnitude and duration are separate toggles, only
// the modes the limit allows are offered, caps are shown and the note is
// required where the policy says so. The engine validates again on save,
// so a refused save shows its message rather than silently storing.
export function FilterEditor({
  limitId,
  flightPeak,
  createdFrom,
  onSaved,
  onCancel,
}: {
  limitId: string;
  flightPeak?: number | null;
  createdFrom?: { flight_id: string; insight_id: string };
  onSaved: (filter: LimitFilter | null) => void;
  onCancel: () => void;
}) {
  const [proposal, setProposal] = useState<FilterProposal | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [magnitudeOn, setMagnitudeOn] = useState(true);
  const [mode, setMode] = useState<FilterMagnitudeMode>("absolute");
  const [value, setValue] = useState<number>(1);
  const [durationOn, setDurationOn] = useState(false);
  const [maxEventS, setMaxEventS] = useState<number>(10);
  const [note, setNote] = useState("");
  // A preview belongs to the draft it was run for; any edit hides it.
  const [previewFor, setPreviewFor] = useState<{ key: string; result: FilterPreview } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    client
      .proposeFilter(limitId)
      .then((p) => {
        if (cancelled) return;
        setProposal(p);
        const existing = p.existing;
        if (existing) {
          setMagnitudeOn(Boolean(existing.magnitude));
          if (existing.magnitude) {
            setMode(existing.magnitude.mode);
            setValue(existing.magnitude.value);
          }
          setDurationOn(Boolean(existing.duration));
          if (existing.duration) setMaxEventS(existing.duration.max_event_s);
          setNote(existing.note);
        } else {
          if (p.suggested.magnitude) setValue(p.suggested.magnitude.value);
          if (p.policy.max_duration_s !== null) setMaxEventS(p.policy.max_duration_s);
          setMagnitudeOn(true);
        }
      })
      .catch((e) => !cancelled && setLoadError(e instanceof Error ? e.message : String(e)));
    return () => {
      cancelled = true;
    };
  }, [limitId]);

  const draft: LimitFilterDraft | null = useMemo(() => {
    if (!proposal) return null;
    return {
      id: proposal.existing?.id,
      limit_id: limitId,
      magnitude: magnitudeOn ? { mode, value } : undefined,
      duration: durationOn && proposal.policy.duration_allowed ? { max_event_s: maxEventS } : undefined,
      note,
      created_from: proposal.existing ? undefined : createdFrom,
    };
  }, [proposal, limitId, magnitudeOn, mode, value, durationOn, maxEventS, note, createdFrom]);

  const draftKey = JSON.stringify(draft);
  const preview = previewFor && previewFor.key === draftKey ? previewFor.result : null;

  if (loadError) {
    return <div style={{ fontSize: 12, color: "var(--severity-limit)", padding: 10 }}>Couldn't load the filter editor: {loadError}</div>;
  }
  if (!proposal || !draft) {
    return <div style={{ fontSize: 12, color: "var(--text-tertiary)", padding: 10 }}>Loading…</div>;
  }

  const { limit, policy, live } = proposal;
  const unit = limit.unit;
  const sign = limit.limit_type === "MIN" ? "−" : "+";
  const liveMag = live.magnitude;
  const isOverboost = limit.id === "overboost";

  if (!policy.filterable) {
    return (
      <div style={{ background: "var(--panel)", borderRadius: 10, padding: "12px 14px", fontSize: 12, color: "var(--text-secondary)" }}>
        <div style={{ fontWeight: 600, marginBottom: 4, color: "var(--text-primary)" }}>{limit.label} can't be filtered</div>
        <div style={{ lineHeight: 1.5 }}>{policy.reason}</div>
        <div style={{ lineHeight: 1.5, marginTop: 6, color: "var(--text-tertiary)" }}>
          It will keep appearing on every flight where it happens. You can add a note to the card to record what you know about it.
        </div>
        <div style={{ marginTop: 8 }}>
          <button style={buttonStyle(false)} onClick={onCancel}>Close</button>
        </div>
      </div>
    );
  }

  const resolvedBand =
    mode === "absolute" ? value : mode === "percent" ? (Math.abs(limit.limit_value) * value) / 100 : null;
  const effectiveLimit =
    resolvedBand !== null ? limit.limit_value + (limit.limit_type === "MIN" ? -resolvedBand : resolvedBand) : null;
  const overCap = policy.max_band_abs !== null && resolvedBand !== null && resolvedBand > policy.max_band_abs + 1e-9;
  const durationOverCap = policy.max_duration_s !== null && maxEventS > policy.max_duration_s;
  const noteMissing = policy.note_required && !note.trim();
  const nothing = !magnitudeOn && !(durationOn && policy.duration_allowed);
  const zUnavailable = mode === "z" && !proposal.z_available;
  const canSave = !nothing && !overCap && !durationOverCap && !noteMissing && !zUnavailable && value > 0 && !busy;

  async function runPreview() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      setPreviewFor({ key: JSON.stringify(draft), result: await client.previewFilter(draft) });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    if (!draft) return;
    setBusy(true);
    setError(null);
    try {
      onSaved(await client.saveFilter(draft));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!proposal?.existing) return;
    setBusy(true);
    try {
      await client.deleteFilter(proposal.existing.id);
      onSaved(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const label = (text: string) => <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{text}</span>;

  return (
    <div
      onClick={(e) => e.stopPropagation()}
      style={{ background: "var(--panel)", borderRadius: 10, padding: "12px 14px", display: "flex", flexDirection: "column", gap: 10, border: "1px solid var(--border)" }}
    >
      <div>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{proposal.existing ? "Edit filter" : "Filter this limit"}: {limit.label}</div>
        <div className="mono" style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 3, lineHeight: 1.5 }}>
          OM {limit.limit_type === "MIN" ? "min" : "max"} {limit.limit_value} {unit}
          {flightPeak !== undefined && flightPeak !== null && <> · this flight {sign}{fmt(flightPeak)} {unit}</>}
        </div>
        {liveMag.n > 0 && (
          <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 3, lineHeight: 1.5 }}>
            {isOverboost
              ? <>Across all your flights the longest block is typically {fmt(liveMag.mean, 0)} s, at most {fmt(liveMag.max, 0)} s ({liveMag.n} flights).</>
              : <>On the {liveMag.n} of your flights that went past this limit, it typically went {fmt(liveMag.mean)} {unit} past, at most {fmt(liveMag.max)} {unit}.</>}
          </div>
        )}
      </div>

      <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
        <input type="checkbox" checked={magnitudeOn} onChange={(e) => setMagnitudeOn(e.target.checked)} />
        <span>{isOverboost ? "A longer block is fine, by" : "A little past the limit is fine, by up to"}</span>
      </label>
      {magnitudeOn && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 24, flexWrap: "wrap" }}>
          <input type="number" step="any" min={0} value={value} onChange={(e) => setValue(Number(e.target.value))} style={inputStyle} />
          <select value={mode} onChange={(e) => setMode(e.target.value as FilterMagnitudeMode)} style={{ ...inputStyle, width: "auto" }}>
            {policy.magnitude_modes.map((m) => (
              <option key={m} value={m} disabled={m === "z" && !proposal.z_available}>
                {m === "absolute" ? unit : MODE_LABEL[m]}
              </option>
            ))}
          </select>
          {resolvedBand !== null && mode !== "absolute" && label(`→ up to ${sign}${fmt(resolvedBand, 2)} ${unit}`)}
          {effectiveLimit !== null && label(`(tolerated to ${fmt(effectiveLimit, 2)} ${unit})`)}
          {mode === "z" && label(proposal.z_available ? `std devs above your reference flights' typical excess` : `needs ${proposal.z_n_min} reference flights with events (has ${proposal.reference.n_with_events})`)}
          {policy.max_band_abs !== null && label(`cap ${policy.max_band_abs} ${unit}`)}
        </div>
      )}
      {overCap && <div style={{ fontSize: 11, color: "var(--severity-limit)", paddingLeft: 24 }}>Over the {policy.max_band_abs} {unit} cap for this limit.</div>}

      {policy.duration_allowed && (
        <>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
            <input type="checkbox" checked={durationOn} onChange={(e) => setDurationOn(e.target.checked)} />
            <span>Brief events are fine, lasting up to</span>
          </label>
          {durationOn && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 24 }}>
              <input type="number" min={1} value={maxEventS} onChange={(e) => setMaxEventS(Number(e.target.value))} style={inputStyle} />
              {label("seconds")}
              {policy.max_duration_s !== null && label(`cap ${policy.max_duration_s} s`)}
            </div>
          )}
          {durationOn && durationOverCap && (
            <div style={{ fontSize: 11, color: "var(--severity-limit)", paddingLeft: 24 }}>Over the {policy.max_duration_s} s cap for this limit.</div>
          )}
        </>
      )}
      {magnitudeOn && durationOn && policy.duration_allowed && (
        <div style={{ fontSize: 11, color: "var(--text-tertiary)" }}>An event is hidden if either condition tolerates it.</div>
      )}

      <div>
        <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginBottom: 4 }}>
          Why is this fine on your aircraft?{policy.note_required ? " (required for a WARNING limit)" : ""}
        </div>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={2}
          placeholder="e.g. sender reads high, confirmed by my mechanic"
          style={{ width: "100%", boxSizing: "border-box", background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "6px 8px", color: "var(--text-primary)", fontSize: 12, resize: "vertical" }}
        />
      </div>

      {preview && (
        <div style={{ fontSize: 12, color: "var(--text-secondary)", background: "var(--bg)", borderRadius: 6, padding: "8px 10px", lineHeight: 1.5 }}>
          {preview.valid ? (
            <>
              This would hide <strong>{preview.events_hidden}</strong> event{preview.events_hidden === 1 ? "" : "s"} on{" "}
              <strong>{preview.flights_affected}</strong> of {preview.flights_considered} flights;{" "}
              {preview.flights_with_breach === 0
                ? "no flight would show a breach."
                : `${preview.flights_with_breach} flight${preview.flights_with_breach === 1 ? "" : "s"} would still show a breach.`}
              {preview.flights.some((f) => f.topic_insights_removed.length > 0) && (
                <div style={{ color: "var(--text-tertiary)" }}>
                  Also hides {preview.flights.reduce((s, f) => s + f.topic_insights_removed.length, 0)} topic threshold insight(s) for this limit.
                </div>
              )}
            </>
          ) : (
            <span style={{ color: "var(--severity-limit)" }}>{preview.diagnostics.map((d) => d.message).join(" ")}</span>
          )}
        </div>
      )}
      {error && <div style={{ fontSize: 12, color: "var(--severity-limit)" }}>{error}</div>}

      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button style={buttonStyle(false, !busy && !nothing)} disabled={busy || nothing} onClick={runPreview}>
          Preview
        </button>
        <button style={buttonStyle(true, canSave)} disabled={!canSave} onClick={save}>
          {proposal.existing ? "Save changes" : "Save filter"}
        </button>
        <button style={buttonStyle(false)} onClick={onCancel}>Cancel</button>
        {proposal.existing && (
          <button style={{ ...buttonStyle(false, !busy), marginLeft: "auto" }} disabled={busy} onClick={remove}>
            Remove filter
          </button>
        )}
      </div>
    </div>
  );
}
