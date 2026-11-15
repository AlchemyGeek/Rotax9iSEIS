"""
Flight identification (Spec 16 D10, §4.4): where a flight went and when,
in words a pilot uses — facts, not analysis.

From the log's GPS track, its indicated altitude, the stored phases and
the bundled airport table (slingology_eis/airports/, OurAirports):

    dep_airport, arr_airport   nearest airport (≤ 3 km) to the first and the
                               last GPS fix on the ground
    route                      the airports in order, consecutive repeats
                               collapsed — departure, every stop, arrival
    stops                      every ground stop in order (a touch-and-go is one)
    takeoffs, landings         ground→air and air→ground transitions
    max_altitude_ft            indicated (baro) altitude
    start_local, end_local     ISO times with the flight's UTC offset
    utc_offset, tz_source      "log" (the log's own zone) or "longitude"
                               (the log carries none: the standard offset of
                               the longitude, with daylight saving by the
                               departure's region in the US, Canada and Europe)
    tz_abbrev                  "PDT", … where the region says, else "UTC−07:00"

On the ground: a ground phase (taxi, the rolls, run-up, shutdown), the
log's own on-ground flag, or — for a touch-and-go, which neither the
phases nor the flag catch — within 3 km of an airport with the indicated
altitude within 50 ft of its elevation. A ground stretch of 2 s or more
separates two airborne ones; an airborne stretch shorter than 30 s is
ground.

Stored per flight as flights/<id>/ident.json, keyed by the analysed
source and IDENT_VERSION; Sync fills it for stored flights. The engine
version doesn't change: no analysis does.
"""
from __future__ import annotations

import csv
import gzip
import re as _re
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np

IDENT_VERSION = 1
FILENAME = "ident.json"
AIRPORT_RADIUS_KM = 3.0
TOUCHDOWN_AGL_FT = 50.0
MIN_GROUND_S = 2
MIN_AIRBORNE_S = 30
_GROUND_PHASES = {"PRE_START", "ENGINE_START", "WARMUP", "TAXI", "TAKEOFF_ROLL", "LANDING_ROLL", "SHUTDOWN"}
_TABLE = Path(__file__).resolve().parent / "airports" / "airports.csv.gz"


# ── The airport table ──────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def airports() -> dict:
    """Columns as numpy arrays plus the text columns as lists."""
    with gzip.open(_TABLE, "rt", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    return {
        "ident": [r["ident"] for r in rows], "icao": [r["icao"] for r in rows], "gps": [r["gps"] for r in rows],
        "iata": [r["iata"] for r in rows],
        "local": [r["local"] for r in rows], "name": [r["name"] for r in rows],
        "municipality": [r["municipality"] for r in rows], "region": [r["region"] for r in rows],
        "lat": np.array([float(r["lat"]) for r in rows]), "lon": np.array([float(r["lon"]) for r in rows]),
        "elev": np.array([float(r["elev_ft"]) if r["elev_ft"] else np.nan for r in rows]),
    }


def code(i: int) -> str:
    """The code a pilot (and Garmin) uses: the ICAO code; in the US without
    one, K + a three-letter FAA identifier (KMAN), else the identifier as
    it is (0S9, W28); elsewhere the GPS code, else OurAirports' ident."""
    a = airports()
    if a["icao"][i]:
        return a["icao"][i]
    local = a["local"][i]
    if a["region"][i].startswith("US-") and local:
        return f"K{local}" if len(local) == 3 and local.isalpha() else local
    return a["gps"][i] or a["ident"][i]


def airport_info(i: int) -> dict:
    a = airports()
    return {"code": code(i), "ident": a["ident"][i], "iata": a["iata"][i] or None, "local": a["local"][i] or None,
            "name": a["name"][i], "municipality": a["municipality"][i] or None, "region": a["region"][i] or None}


def _km(lat1, lon1, lat2, lon2):
    """Equirectangular distance in km (good to well under 1% at 3 km)."""
    x = (np.asarray(lon2) - lon1) * np.cos(np.radians((np.asarray(lat2) + lat1) / 2))
    y = np.asarray(lat2) - lat1
    return 111.195 * np.hypot(x, y)


def _candidates(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    a = airports()
    pad = 0.06
    m = ((a["lat"] >= np.nanmin(lat) - pad) & (a["lat"] <= np.nanmax(lat) + pad)
         & (a["lon"] >= np.nanmin(lon) - pad * 2) & (a["lon"] <= np.nanmax(lon) + pad * 2))
    return np.nonzero(m)[0]


def nearest(lat: float, lon: float, within_km: float = AIRPORT_RADIUS_KM) -> Optional[int]:
    if lat is None or lon is None or not np.isfinite(lat) or not np.isfinite(lon):
        return None
    cand = _candidates(np.array([lat]), np.array([lon]))
    if not len(cand):
        return None
    a = airports()
    d = _km(lat, lon, a["lat"][cand], a["lon"][cand])
    j = int(np.argmin(d))
    return int(cand[j]) if d[j] <= within_km else None


def search(text: str) -> list[int]:
    """Airports whose code, IATA, local code, name or municipality matches
    a word or phrase (case-insensitive): exact codes first."""
    a = airports()
    t = text.strip().lower()
    if not t:
        return []
    exact = [i for i in range(len(a["ident"]))
             if t in (a["ident"][i].lower(), a["icao"][i].lower(), a["gps"][i].lower(), a["iata"][i].lower(),
                      a["local"][i].lower())]
    if exact:
        return exact
    return [i for i in range(len(a["ident"])) if t in a["name"][i].lower() or t == a["municipality"][i].lower()]


# ── Time zone ──────────────────────────────────────────────────────────────

def _nth_sunday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(6 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_sunday(year: int, month: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


_EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE", "IT", "LV", "LT", "LU",
       "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE", "GB", "NO", "CH", "LI"}
_NO_DST = {"US-AZ", "US-HI", "CA-SK", "CA-YT"}
_US_ABBR = {(-5, False): "EST", (-4, True): "EDT", (-6, False): "CST", (-5, True): "CDT", (-7, False): "MST",
            (-6, True): "MDT", (-8, False): "PST", (-7, True): "PDT", (-9, False): "AKST", (-8, True): "AKDT",
            (-10, False): "HST"}


def _dst(region: Optional[str], day: date) -> bool:
    if not region or region in _NO_DST:
        return False
    country = region.split("-")[0]
    if country in ("US", "CA"):
        return _nth_sunday(day.year, 3, 2) <= day < _nth_sunday(day.year, 11, 1)
    if country in _EU:
        return _last_sunday(day.year, 3) <= day < _last_sunday(day.year, 10)
    return False


def _fmt_offset(minutes: int) -> str:
    sign = "-" if minutes < 0 else "+"
    m = abs(int(minutes))
    return f"{sign}{m // 60:02d}:{m % 60:02d}"


def _parse_offset(s: str) -> Optional[int]:
    s = (s or "").strip()
    if len(s) == 6 and s[0] in "+-" and s[3] == ":" and s[1:3].isdigit() and s[4:].isdigit():
        m = int(s[1:3]) * 60 + int(s[4:])
        return -m if s[0] == "-" else m
    return None


def abbrev(offset_min: int, region: Optional[str], day: date) -> str:
    if region and region.split("-")[0] in ("US",) and offset_min % 60 == 0:
        a = _US_ABBR.get((offset_min // 60, _dst(region, day)))
        if a:
            return a
    if region and region.split("-")[0] in ("GB", "IE") and offset_min in (0, 60):
        return {0: "GMT", 60: "BST" if region.startswith("GB") else "IST"}[offset_min]
    return "UTC" + _fmt_offset(offset_min).replace("-", "−")


# ── The facts ──────────────────────────────────────────────────────────────

def _runs(mask: np.ndarray) -> list[tuple[int, int, bool]]:
    """Contiguous runs of a boolean array: (start, end_exclusive, value)."""
    out = []
    if not len(mask):
        return out
    start = 0
    for i in range(1, len(mask) + 1):
        if i == len(mask) or mask[i] != mask[start]:
            out.append((start, i, bool(mask[start])))
            start = i
    return out


def _smooth(ground: np.ndarray) -> np.ndarray:
    g = ground.copy()
    # A short airborne blip (a bounce, a GPS jump) is ground.
    for s, e, v in _runs(g):
        if not v and (e - s) < MIN_AIRBORNE_S and s > 0 and e < len(g):
            g[s:e] = True
    # A ground flicker shorter than MIN_GROUND_S between airborne stretches is airborne.
    for s, e, v in _runs(g):
        if v and (e - s) < MIN_GROUND_S and s > 0 and e < len(g):
            g[s:e] = False
    return g


def compute(df, phases: list[dict]) -> dict:
    """The facts for one flight from its loaded frame (loader.load_log_bytes)
    and its stored phase segments."""
    n = len(df)
    t = df["elapsed_s"].to_numpy(dtype=float) if "elapsed_s" in df else np.arange(n, dtype=float)
    lat = df["lat"].to_numpy(dtype=float) if "lat" in df else np.full(n, np.nan)
    lon = df["lon"].to_numpy(dtype=float) if "lon" in df else np.full(n, np.nan)
    alt = df["baro_alt_ft"].to_numpy(dtype=float) if "baro_alt_ft" in df else np.full(n, np.nan)
    fix = np.isfinite(lat) & np.isfinite(lon) & ~((lat == 0) & (lon == 0))

    ground = np.zeros(n, dtype=bool)
    for p in phases or []:
        if p.get("phase") in _GROUND_PHASES:
            ground |= (t >= p["start_s"]) & (t < p["end_s"])
    if "on_ground" in df:
        og = df["on_ground"].to_numpy()
        ground |= np.array([v is True or v == 1 for v in og], dtype=bool)
    near_idx = np.full(n, -1)
    if fix.any():
        cand = _candidates(lat[fix], lon[fix])
        if len(cand):
            a = airports()
            d = _km(lat[fix][:, None], lon[fix][:, None], a["lat"][cand][None, :], a["lon"][cand][None, :])
            j = np.argmin(d, axis=1)
            close = d[np.arange(len(j)), j] <= AIRPORT_RADIUS_KM
            idx = np.where(close, cand[j], -1)
            near_idx[np.nonzero(fix)[0]] = idx
            elev = np.where(idx >= 0, a["elev"][np.maximum(idx, 0)], np.nan)
            agl = alt[fix] - elev
            touch = close & np.isfinite(agl) & (agl <= TOUCHDOWN_AGL_FT)
            ground[np.nonzero(fix)[0][touch]] = True
    ground = _smooth(ground)

    runs = _runs(ground)
    takeoffs = sum(1 for (_s, _e, v), (_s2, _e2, v2) in zip(runs, runs[1:]) if v and not v2)
    landings = sum(1 for (_s, _e, v), (_s2, _e2, v2) in zip(runs, runs[1:]) if not v and v2)

    stops = []      # one per ground stretch: the airport, from its fixes
    for k, (s, e, v) in enumerate(runs):
        if not v:
            continue
        sel = np.nonzero(fix[s:e])[0] + s
        if not len(sel):
            stops.append({"airport": None, "kind": "start" if k == 0 else "end" if k == len(runs) - 1 else "stop",
                          "t_s": float(t[s])})
            continue
        # The departure is where the first fix on the ground is; the arrival the last; a stop its middle.
        pick = sel[0] if k == 0 else sel[-1] if k == len(runs) - 1 else sel[len(sel) // 2]
        ap = int(near_idx[pick]) if near_idx[pick] >= 0 else nearest(lat[pick], lon[pick])
        stops.append({"airport": code(ap) if ap is not None else None, "_i": ap,
                      "kind": "start" if k == 0 else "end" if k == len(runs) - 1 else "stop",
                      "t_s": float(t[s]), "touch_and_go": bool(k not in (0, len(runs) - 1) and (e - s) < 60)})
    dep = stops[0] if stops and stops[0]["kind"] == "start" else None
    arr = stops[-1] if stops and stops[-1]["kind"] == "end" else None
    route: list[str] = []
    for st in stops:
        c = st["airport"] or "?"
        if not route or route[-1] != c:
            route.append(c)

    # Local time.
    dts = df["datetime"] if "datetime" in df else None
    start_naive = dts.iloc[0].to_pydatetime() if dts is not None and n else None
    end_naive = dts.iloc[-1].to_pydatetime() if dts is not None and n else None
    offset = None
    if "utc_offset" in df:
        vals = [o for o in (_parse_offset(str(v)) for v in df["utc_offset"].dropna().unique()) if o is not None]
        if vals:
            offset = max(set(vals), key=vals.count)
    lon_med = float(np.nanmedian(lon[fix])) if fix.any() else None
    dep_i = dep.get("_i") if dep else None
    region = airports()["region"][dep_i] if dep_i is not None else None
    if region is None:
        first_ap = next((s.get("_i") for s in stops if s.get("_i") is not None), None)
        region = airports()["region"][first_ap] if first_ap is not None else None
    # A zero offset far from Greenwich is a clock without a zone (the AXIS
    # reports +00:00 and UTC times): the clock is UTC, the zone unknown.
    tz_source = "log"
    utc_start = None
    if offset is None or (offset == 0 and lon_med is not None and abs(round(lon_med / 15)) >= 1):
        tz_source = "longitude" if lon_med is not None else "none"
        utc_start = start_naive
        if lon_med is not None and start_naive is not None:
            std = int(round(lon_med / 15)) * 60
            offset = std + (60 if _dst(region, start_naive.date()) else 0)
        else:
            offset = 0
        if start_naive is not None:
            start_naive = start_naive + timedelta(minutes=offset)
            end_naive = end_naive + timedelta(minutes=offset)
    day = start_naive.date() if start_naive else date.today()
    off = _fmt_offset(offset)
    out = {
        "version": IDENT_VERSION,
        "dep_airport": dep["airport"] if dep else None,
        "arr_airport": arr["airport"] if arr else None,
        "route": route if any(c != "?" for c in route) else [],
        "stops": [{k: v for k, v in s.items() if not k.startswith("_")} for s in stops],
        "takeoffs": int(takeoffs), "landings": int(landings),
        "max_altitude_ft": float(np.nanmax(alt)) if np.isfinite(alt).any() else None,
        "start_local": start_naive.isoformat(timespec="seconds") + off if start_naive else None,
        "end_local": end_naive.isoformat(timespec="seconds") + off if end_naive else None,
        "utc_offset": off, "tz_source": tz_source, "tz_abbrev": abbrev(offset, region, day),
        "local_date": day.isoformat() if start_naive else None,
    }
    if utc_start is None and start_naive is not None:
        utc_start = start_naive - timedelta(minutes=offset)
    out["utc_start"] = utc_start.isoformat(timespec="seconds") + "Z" if utc_start else None
    return out


def compute_from_bytes(content: bytes, filename: str, phases: list[dict]) -> dict:
    from .loader import load_log_bytes
    df, _info = load_log_bytes(content, filename)
    return compute(df, phases)


# ── Labels (§4.7) ──────────────────────────────────────────────────────────

def local_clock(ident: Optional[dict], header_start: Optional[str], t_s: float) -> Optional[str]:
    """'2026-11-11 12:55:22 PST' for t_s seconds into the flight."""
    if not ident or not ident.get("start_local"):
        return None
    start = datetime.fromisoformat(ident["start_local"][:19])
    at = start + timedelta(seconds=float(t_s))
    return f"{at:%Y-%m-%d %H:%M:%S} {ident.get('tz_abbrev') or ''}".strip()


def into(t_s: float) -> str:
    """'+06:07' (mm:ss, or h:mm:ss past an hour) into the flight."""
    t = int(round(float(t_s)))
    h, rem = divmod(abs(t), 3600)
    m, s = divmod(rem, 60)
    return f"+{h}:{m:02d}:{s:02d}" if h else f"+{m:02d}:{s:02d}"


def window_label(ident: Optional[dict], start_s: float, end_s: Optional[float] = None) -> str:
    """§4.7: '2026-11-11 12:55:22 PST (+06:07 into the flight)', or a span
    '… 12:55:22–12:56:19 PST (+06:07–+07:04 into the flight)'."""
    a = local_clock(ident, None, start_s)
    if end_s is None:
        return f"{a} ({into(start_s)} into the flight)" if a else f"{into(start_s)} into the flight"
    b = local_clock(ident, None, end_s)
    if a and b:
        tz = (ident or {}).get("tz_abbrev") or ""
        return f"{a[:19]}–{b[11:19]} {tz} ({into(start_s)}–{into(end_s)} into the flight)".replace("  ", " ")
    return f"{into(start_s)}–{into(end_s)} into the flight"


# ── Storage ────────────────────────────────────────────────────────────────

def _key(fa) -> str:
    return f"{IDENT_VERSION}:{fa.analysis_key}"


def load(ws_dir: Path, flight_id: str) -> Optional[dict]:
    import json
    p = Path(ws_dir) / "flights" / flight_id / FILENAME
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text())
    except ValueError:
        return None


def current(ws_dir: Path, fa) -> Optional[dict]:
    """The stored facts if they belong to this analysis, else None."""
    got = load(ws_dir, fa.flight_id)
    return got if got and got.get("key") == _key(fa) else None


def save(ws_dir: Path, fa, facts: dict) -> dict:
    import json
    doc = {**facts, "key": _key(fa)}
    p = Path(ws_dir) / "flights" / fa.flight_id / FILENAME
    p.write_text(json.dumps(doc, indent=2))
    return doc


async def ensure_async(ws_dir: Path, sources, flight_ids: Optional[list] = None, on_progress=None) -> dict:
    """Fill flights/<id>/ident.json for every flight (or `flight_ids`)
    lacking current facts: the analysed log is read (one file at a time,
    through the workspace's log sources) and nothing else is touched.
    Returns {identified, unreadable}."""
    from . import workspace as ws
    done = unreadable = 0
    ids = list(flight_ids) if flight_ids is not None else ws.list_flight_ids(ws_dir)
    todo = []
    for fid in ids:
        fa = ws.load_flight_analysis(ws_dir, fid)
        if fa is not None and current(ws_dir, fa) is None:
            todo.append(fa)
    for k, fa in enumerate(todo):
        src = ws.load_sources(ws_dir, fa.flight_id)
        got = (await ws.read_source_bytes_async(ws_dir, src, sources)) if src is not None else None
        if got is None:
            unreadable += 1
            continue
        try:
            facts = compute_from_bytes(got[0], got[1], fa.phases)
        except Exception:   # noqa: BLE001 — a log that won’t identify keeps no facts; the flight is unchanged
            unreadable += 1
            continue
        save(ws_dir, fa, facts)
        done += 1
        if on_progress:
            on_progress({"phase": "identify", "done": k + 1, "total": len(todo)})
    return {"identified": done, "unreadable": unreadable}


# ── Names (the pilot's) ────────────────────────────────────────────────────

NAMES = "flight_names.json"
MAX_NAME_CHARS = 120
MAX_NOTES_CHARS = 4000


def load_names(ws_dir: Path) -> dict:
    import json
    p = Path(ws_dir) / NAMES
    if not p.is_file():
        return {}
    try:
        return dict((json.loads(p.read_text()) or {}).get("flights") or {})
    except ValueError:
        return {}


def set_name(ws_dir: Path, flight_id: str, name: Optional[str], notes: Optional[str]) -> dict:
    """Set (or, with both empty, clear) a flight's name and notes."""
    import json
    from datetime import timezone
    names = load_names(ws_dir)
    cur = dict(names.get(flight_id) or {})
    if name is not None:
        name = str(name).strip()
        if len(name) > MAX_NAME_CHARS:
            raise ValueError(f"a flight's name is at most {MAX_NAME_CHARS} characters")
        cur["name"] = name
    if notes is not None:
        notes = str(notes).strip()
        if len(notes) > MAX_NOTES_CHARS:
            raise ValueError(f"a flight's notes are at most {MAX_NOTES_CHARS} characters")
        cur["notes"] = notes
    cur = {k: v for k, v in cur.items() if k in ("name", "notes") and v}
    if cur:
        cur["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        names[flight_id] = cur
    else:
        names.pop(flight_id, None)
    (Path(ws_dir) / NAMES).write_text(json.dumps({"version": 1, "flights": names}, indent=2, ensure_ascii=False))
    return cur


# ── flights_find (D10): a description in words → ranked candidates ─────────


_MONTHS = {m: i + 1 for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                           "september", "october", "november", "december"))}
_MONTHS.update({m[:3]: i for m, i in list(_MONTHS.items())})
_MONTHS["sept"] = 9
_WEEKDAYS = {d: i for i, d in enumerate(("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"))}
_WEEKDAYS.update({d[:3]: i for d, i in list(_WEEKDAYS.items())})
_NUMBERS = {w: i for i, w in enumerate(("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
                                         "ten", "eleven", "twelve"))}
_NUMBERS.update({"once": 1, "twice": 2, "single": 1, "a": 1, "an": 1})
_STOP = {"the", "flight", "flights", "with", "at", "to", "from", "in", "on", "my", "of", "and", "that", "where",
         "when", "was", "were", "i", "we", "it", "this", "trip", "went", "go", "fly", "flew", "around", "via",
         "after", "before", "day", "landing", "landings", "takeoff", "takeoffs", "take-off", "take-offs", "stop",
         "stops", "touch", "go", "goes", "touch-and-go", "touch-and-goes", "airport", "field", "last", "this",
         "today", "yesterday", "or", "for", "about", "out", "back"}


def _words(text: str) -> list[str]:
    return _re.findall(r"[a-z0-9][a-z0-9'\-/]*", text.lower())


def parse_description(text: str, today: date) -> dict:
    """What a description asks for: dates, weekdays, months, counts,
    airport words and the rest (name words)."""
    t = text.lower()
    want: dict = {"dates": set(), "months": set(), "weekdays": set(), "landings": None, "takeoffs": None,
                  "airport_words": [], "years": set()}
    for y, m, d in _re.findall(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t):
        want["dates"].add(date(int(y), int(m), int(d)))
    for m, d in _re.findall(r"\b(\d{1,2})/(\d{1,2})\b", t):
        if 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            want["dates"].add((int(m), int(d)))
    for y in _re.findall(r"\b(20\d\d)\b", t):
        want["years"].add(int(y))
    words = _words(t)
    used: set[int] = set()
    for i, w in enumerate(words):
        mw = w.rstrip(".,")
        if mw in _MONTHS:
            month = _MONTHS[mw]
            day = None
            for j in (i + 1, i - 1):
                if 0 <= j < len(words):
                    m = _re.match(r"^(\d{1,2})(st|nd|rd|th)?$", words[j])
                    if m and 1 <= int(m.group(1)) <= 31:
                        day, _ = int(m.group(1)), used.add(j)
                        break
            used.add(i)
            if day:
                want["dates"].add((month, day))
            else:
                want["months"].add(month)
        elif mw in _WEEKDAYS:
            used.add(i)
            if i > 0 and words[i - 1] == "last":
                back = (today.weekday() - _WEEKDAYS[mw]) % 7 or 7
                want["dates"].add(today - timedelta(days=back))
            else:
                want["weekdays"].add(_WEEKDAYS[mw])
        elif mw == "today":
            want["dates"].add(today)
            used.add(i)
        elif mw == "yesterday":
            want["dates"].add(today - timedelta(days=1))
            used.add(i)
        elif mw in ("landing", "landings", "takeoff", "takeoffs", "take-off", "take-offs", "stops", "stop"):
            n = None
            if i > 0 and (words[i - 1].isdigit() or words[i - 1] in _NUMBERS):
                n = int(words[i - 1]) if words[i - 1].isdigit() else _NUMBERS[words[i - 1]]
                used.add(i - 1)
            used.add(i)
            if n is not None:
                if mw.startswith("take"):
                    want["takeoffs"] = n
                elif mw.startswith("stop"):
                    want["landings"] = n + 1      # n stops on the way, then the arrival
                else:
                    want["landings"] = n
        elif mw in ("touch-and-go", "touch-and-goes") or (mw == "touch" and words[i + 1:i + 3] == ["and", "go"]) \
                or (mw == "touch" and words[i + 1:i + 3] == ["and", "goes"]):
            used.update({i, i + 1, i + 2})
            want["landings"] = max(want["landings"] or 0, 2)
    for i, w in enumerate(words):
        if i in used or w in _STOP or w in _NUMBERS or _re.match(r"^\d+(st|nd|rd|th)?$", w) or "/" in w \
                or _re.match(r"^20\d\d-\d\d-\d\d$", w):
            continue
        want["airport_words"].append(w)
    return want


def _airport_matches(word: str) -> set[str]:
    return {code(i) for i in search(word)} if len(word) >= 3 else set()


def find(rows: list[dict], description: str, today: Optional[date] = None, limit: int = 10) -> dict:
    """Score each flight row ({flight_id, ident, name, notes}) against the
    description; ≤ limit candidates, best first, with what matched."""
    today = today or date.today()
    want = parse_description(description, today)
    airports_by_word = {w: _airport_matches(w) for w in want["airport_words"]}
    out = []
    for r in rows:
        ident = r.get("ident") or {}
        d = date.fromisoformat(ident.get("local_date") or r.get("date") or "1970-01-01")
        score, matched = 0.0, []
        for want_d in want["dates"]:
            if (isinstance(want_d, date) and want_d == d) or (isinstance(want_d, tuple) and want_d == (d.month, d.day)):
                score += 6
                matched.append(f"date {d.isoformat()}")
        if d.month in want["months"]:
            score += 2
            matched.append(f"month {d:%B}")
        if d.weekday() in want["weekdays"]:
            score += 2
            matched.append(f"{d:%A}")
        if d.year in want["years"] and want["years"]:
            score += 1
            matched.append(f"year {d.year}")
        for key in ("landings", "takeoffs"):
            if want[key] is not None and ident.get(key) is not None:
                if ident[key] == want[key]:
                    score += 3
                    matched.append(f"{want[key]} {key}")
                elif abs(ident[key] - want[key]) == 1:
                    score += 0.5
        route = set(ident.get("route") or []) | {ident.get("dep_airport"), ident.get("arr_airport")} - {None}
        text = f"{r.get('name') or ''} {r.get('notes') or ''}".lower()
        for w, codes in airports_by_word.items():
            hit = route & codes
            if hit:
                score += 4
                matched.append(f"airport {'/'.join(sorted(hit))} ({w})")
            elif w in _words(text):
                score += 3
                matched.append(f"name “{w}”")
        if score > 0:
            out.append({"flight_id": r["flight_id"], "score": round(score, 1), "matched": matched,
                        "local_date": d.isoformat(), "start_local": ident.get("start_local"),
                        "route": "–".join(ident.get("route") or []) or None, "takeoffs": ident.get("takeoffs"),
                        "landings": ident.get("landings"), "name": r.get("name") or None})
    # Best first; ties, the most recent first.
    out.sort(key=lambda c: (-c["score"], -(datetime.fromisoformat(c["start_local"][:19]).timestamp()
                                           if c["start_local"] else 0)))
    understood = {
        "dates": sorted(x.isoformat() if isinstance(x, date) else f"{x[0]:02d}-{x[1]:02d}" for x in want["dates"]),
        "months": sorted(want["months"]), "weekdays": sorted(want["weekdays"]),
        "landings": want["landings"], "takeoffs": want["takeoffs"],
        "airports": {w: sorted(c)[:5] for w, c in airports_by_word.items() if c},
        "other_words": [w for w, c in airports_by_word.items() if not c],
    }
    return {"description": description, "understood": understood, "candidates": out[:limit], "total": len(out)}


# ── §4.7: every time a tool returns is local with its offset ───────────────

# What the caller sends back as a definition (a derived rule's hand slice,
# a study's slice set) stays as the engine gave it.
_DEFINITIONS = ("derived_rule", "hand_slices", "slice_rules", "selection", "slice_set", "params")
_SLICE_ID = _re.compile(r"^([0-9a-f]{16}):.*:(\d+(?:\.\d+)?)-(\d+(?:\.\d+)?)$")


def localise(ws_dir: Path, obj, _cache: Optional[dict] = None):
    """Label every slice and window in an operation's answer with the
    flight's local time (§4.7): a dict naming a slice (`slice_id`
    "<flight>:<rule>:<a>-<b>") or a flight and `start_s` gains
    `start_local` ("2026-11-11 12:55:22 PST") and `when` ("2026-11-11
    12:55:22–12:56:19 PST (+06:07–+07:04 into the flight)"). Facts, not
    analysis: nothing else changes. Returns obj (changed in place)."""
    cache = {} if _cache is None else _cache

    def ident(fid: str):
        if fid not in cache:
            cache[fid] = load(ws_dir, fid)
        return cache[fid]

    def walk(x, inherited=None):
        if isinstance(x, list):
            for v in x:
                walk(v, inherited)
            return
        if not isinstance(x, dict):
            return
        own = x.get("flight") or x.get("flight_id")
        here = own if isinstance(own, str) and _re.match(r"^[0-9a-f]{16}$", own) else inherited
        fid, a, b = None, None, None
        m = _SLICE_ID.match(str(x.get("slice_id") or ""))
        if m:
            fid, a, b = m.group(1), float(m.group(2)), float(m.group(3))
        elif here and isinstance(x.get("start_s"), (int, float)) and not isinstance(x.get("start_s"), bool):
            fid, a = here, float(x["start_s"])
            b = float(x["end_s"]) if isinstance(x.get("end_s"), (int, float)) else None
        if fid:
            i = ident(fid)
            if i and i.get("start_local"):
                x["start_local"] = local_clock(i, None, a)
                x["when"] = window_label(i, a, b)
        for k, v in x.items():
            if isinstance(v, (dict, list)) and k not in _DEFINITIONS:
                walk(v, here)
    walk(obj)
    return obj
