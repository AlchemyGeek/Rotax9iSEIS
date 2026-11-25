// Spec 03 v0.34 §5.10 — one formatter for a window's time, used by Research
// home (marks), the notebook page (log-view captions) and the Flight view's
// mark dialog: short — `Jan 1 · 12:01–12:03 (+1:50 into the flight)` — with
// the full local form and zone (the engine's window_label, Spec 16 §4.7) on
// hover. The shortening is ported string for string in
// slingology_eis/investigations/nbhtml.py (short_window), so the HTML export
// says the same.

export interface WindowTime {
  short: string;
  full: string;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** '+06:07' (mm:ss, or h:mm:ss past an hour) — flight_ident.into. */
export function into(tS: number): string {
  const t = Math.round(Math.abs(Number(tS)));
  const h = Math.floor(t / 3600), m = Math.floor((t % 3600) / 60), s = t % 60;
  return h ? `+${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `+${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

function clockAt(startLocal: string, tS: number): string | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(startLocal);
  if (!m) return null;
  // Wall-clock arithmetic in UTC so no browser zone or DST shifts it.
  const at = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]) + Math.round(Number(tS)) * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${at.getUTCFullYear()}-${p(at.getUTCMonth() + 1)}-${p(at.getUTCDate())} ${p(at.getUTCHours())}:${p(at.getUTCMinutes())}:${p(at.getUTCSeconds())}`;
}

/** The engine's window_label (flight_ident.window_label), from the flight's local start and zone. */
export function windowLabel(startLocal: string | null | undefined, tz: string | null | undefined, startS: number, endS?: number | null): string {
  const a = startLocal ? clockAt(startLocal, startS) : null;
  if (endS === null || endS === undefined) {
    return a ? `${a} (${into(startS)} into the flight)` : `${into(startS)} into the flight`;
  }
  const b = startLocal ? clockAt(startLocal, endS) : null;
  if (a && b) return `${a.slice(0, 19)}–${b.slice(11, 19)} ${tz ?? ""} (${into(startS)}–${into(endS)} into the flight)`.replace("  ", " ");
  return `${into(startS)}–${into(endS)} into the flight`;
}

const LABEL = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2})(?:–(\d{2}):(\d{2}):(\d{2}))?(?: ([^ (]+))? \((\+[\d:]+)(?:–\+[\d:]+)? into the flight\)$/;
const NO_CLOCK = /^(\+[\d:]+)(?:–(\+[\d:]+))? into the flight$/;

/** '+06:07' → '+6:07'; '+1:02:03' stays. */
function trimInto(s: string): string {
  return s.replace(/^\+0(\d:)/, "+$1");
}

/** A window_label made short: date without year, hh:mm (with seconds when
 * the window is inside one minute), the offset of its start. */
export function shortWindow(label: string | null | undefined): string {
  const l = String(label ?? "").trim();
  const m = LABEL.exec(l);
  if (m) {
    const date = `${MONTHS[+m[2] - 1] ?? m[2]} ${+m[3]}`;
    let clock = `${m[4]}:${m[5]}`;
    if (m[7] !== undefined) {
      const sameMinute = m[7] === m[4] && m[8] === m[5];
      clock = sameMinute ? `${m[4]}:${m[5]}:${m[6]}–${m[7]}:${m[8]}:${m[9]}` : `${m[4]}:${m[5]}–${m[7]}:${m[8]}`;
    }
    return `${date} · ${clock} (${trimInto(m[11])} into the flight)`;
  }
  const n = NO_CLOCK.exec(l);
  if (n) return `${trimInto(n[1])}${n[2] ? `–${trimInto(n[2])}` : ""} into the flight`;     // no clock: the offsets are the window
  return l;
}

export function windowTime(startLocal: string | null | undefined, tz: string | null | undefined, startS: number, endS?: number | null): WindowTime {
  const full = windowLabel(startLocal, tz, startS, endS);
  return { short: shortWindow(full), full };
}

export function labelTime(label: string | null | undefined): WindowTime {
  const full = String(label ?? "");
  return { short: shortWindow(full), full };
}
