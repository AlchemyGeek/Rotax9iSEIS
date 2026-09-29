# Spec: Workspace Flight Exclusions

**Status:** Ready for implementation (depends on Spec: Ground Session Detection)  
**Affects:** `slingology_eis/loader.py`, new `slingology_eis/exclusions.py`,
`config.json`, CLI, Flights tab UI  
**Version target:** 0.12.0

---

## Purpose

Provide a transparent, user-controllable mechanism for marking flights as
excluded from analysis. Today, ground sessions are silently dropped at
load time with no record and no way for the user to see what was removed
or why. Any flight the user wants to exclude for other reasons (short
hop, ferry flight, known anomaly) has to be physically removed from the
logs folder.

The new mechanism replaces silent dropping with an explicit record:
every exclusion — automatic or manual — is written to `exclusions.json`,
is visible in the Flights tab, and can be overridden by the user.

---

## Design decisions

### All-or-nothing exclusion

There is no partial exclusion (e.g. "exclude from trends but show in
flight list"). A flight is either in the workspace or it isn't. This
keeps the model simple and avoids the complexity of per-analysis opt-out
logic.

### Single source of truth: `exclusions.json`

Every exclusion lives in one file. The loader and all analysis pipelines
read it. The Flights tab writes it (for user exclusions). The auto-
detection logic writes it (for automatic exclusions). Nothing is silently
dropped without an entry here.

### Membership vs. baseline contribution

These are two separate concepts (per the workspace design notes):
- **Membership:** which files are in the workspace at all.
- **Baseline contribution:** which members feed baselines/trends.

`exclusions.json` drives **baseline contribution** — excluded flights are
still *known* to the workspace (they appear in the Flights tab with their
status), but they don't feed any analysis. This preserves the user's
ability to see and review them.

---

## `exclusions.json` format

Location: workspace root (same directory as `baselines.json`,
`models.json`, etc.). For the Python toolkit, this is `data/exclusions.json`
by default, following the same convention as other workspace artifacts.

```json
{
  "version": 1,
  "entries": [
    {
      "filename": "log_20260825_194740_KAWO.csv",
      "source": "auto",
      "reason": "ground session — no airborne phase detected",
      "category": "ground_session",
      "excluded_at": "2026-09-29T14:23:00Z",
      "user_override": false
    },
    {
      "filename": "log_20260423_135821_KTOA.csv",
      "source": "user",
      "reason": "ATC delay at LAX — extended overboost, not representative",
      "category": "user_defined",
      "excluded_at": "2026-09-29T15:00:00Z",
      "user_override": false
    },
    {
      "filename": "log_20260401_091200_KAWO.csv",
      "source": "auto",
      "reason": "below minimum flight duration (8 min < 15 min threshold)",
      "category": "short_flight",
      "excluded_at": "2026-09-29T14:23:00Z",
      "user_override": true,
      "override_reason": "intentional pattern-work session — include in baselines"
    }
  ]
}
```

### Field definitions

| Field | Type | Description |
|---|---|---|
| `filename` | string | Log filename (not full path — relative to the configured logs folder) |
| `source` | `"auto"` \| `"user"` | Who created this entry |
| `reason` | string | Human-readable explanation |
| `category` | string | Machine-readable category (see below) |
| `excluded_at` | ISO 8601 | When the entry was created |
| `user_override` | bool | If `true`, auto-exclusion has been overridden — include this flight despite the auto rule |
| `override_reason` | string | Optional. User's explanation for the override |

### Categories

| Category | Source | Description |
|---|---|---|
| `ground_session` | auto | No airborne phase detected by `detect_phases()` |
| `short_flight` | auto | Total airborne time below `min_flight_duration_min` in `config.json` |
| `corrupt_log` | auto | Parse failure, large time gaps, or mid-log power cycle |
| `user_defined` | user | User-excluded for any reason they choose |

---

## Auto-exclusion rules

### Rule 1: Ground session (`ground_session`)

**Trigger:** `detect_phases()` finds no airborne phase.  
**Implemented in:** `load_directory()` (after the ground-session detection
spec is implemented). When a file is identified as a ground session, write
an entry to `exclusions.json` before skipping it, rather than silently
dropping it.

### Rule 2: Short flight (`short_flight`)

**Trigger:** Total airborne time (rows in an airborne phase) is below
`min_flight_duration_min`.  
**Config:** `min_flight_duration_min` in `config.json`. Default: `10`
(minutes). Set to `0` to disable.  
**Rationale:** Pattern-work hops, touch-and-goes, and very short local
flights produce incomplete analytics data (no cruise phase, no thermal
stabilization) that skews baselines without adding signal.  
**Important:** this is conservative by design. A 12-minute flight to a
nearby airport is real airborne time and should probably be included;
the threshold is meant to catch 3-minute circuits, not cross-country
legs. Default of 10 minutes is deliberately low.

### Rule 3: Corrupt log (`corrupt_log`)

**Trigger:** Any of:
- `load_log()` raises a parse exception (already handled — these become
  `✗` entries today)
- The log contains a time gap > 5 minutes within a single session
  (strong signal of a mid-session avionics restart or SD card error)
- `detect_phases()` identifies a mid-log POWERUP (ENGINE ECU alert
  appearing well after the initial start sequence — the B2 backlog item)

**Note:** The mid-log POWERUP detection (B2) is on the backlog and not
yet implemented. Until it is, `corrupt_log` auto-exclusion only covers
parse failures and large time gaps.

---

## `user_override` behaviour

When `user_override: true` on an auto-excluded entry:
- The entry **stays** in `exclusions.json` — the auto-rule that created
  it is still recorded.
- The flight **is included** in all analysis pipelines, as if it were
  never excluded.
- The Flights tab shows the flight with an "Overridden" badge and the
  override reason.

This is the only way to bring a flight back into baselines. There is no
"delete from exclusions.json" operation — the record is permanent, but
the user_override flag controls whether it takes effect.

---

## `exclusions.py` module

New module: `slingology_eis/exclusions.py`

```python
# Public API

def load_exclusions(workspace_dir: Path) -> dict:
    """Load exclusions.json; return empty structure if file doesn't exist."""

def save_exclusions(workspace_dir: Path, exclusions: dict) -> None:
    """Write exclusions.json atomically."""

def is_excluded(filename: str, exclusions: dict) -> bool:
    """
    Return True if this filename should be excluded from analysis.
    Respects user_override: an overridden entry returns False.
    """

def add_auto_exclusion(
    workspace_dir: Path,
    filename: str,
    category: str,
    reason: str,
) -> None:
    """
    Write an auto-exclusion entry if one doesn't already exist for
    this filename. Idempotent — re-running detection on the same file
    doesn't create duplicate entries.
    """

def add_user_exclusion(
    workspace_dir: Path,
    filename: str,
    reason: str,
) -> None:
    """Add a user-defined exclusion entry."""

def set_user_override(
    workspace_dir: Path,
    filename: str,
    override: bool,
    override_reason: str = "",
) -> None:
    """Set or clear the user_override flag on an existing entry."""

def exclusion_summary(exclusions: dict) -> dict:
    """
    Return counts by category and override status, for the Flights tab
    header line and the CLI output.
    e.g. {"ground_session": 14, "short_flight": 3, "user_defined": 2,
          "overridden": 1}
    """
```

---

## `load_directory()` integration

After implementing ground-session detection (per the companion spec),
`load_directory()` gains a `workspace_dir` optional parameter:

```python
def load_directory(
    directory: str | Path,
    pattern: str = "*.csv",
    skip_ground_sessions: bool = True,
    workspace_dir: Optional[Path] = None,   # NEW
    verbose: bool = True,
) -> list[tuple[pd.DataFrame, AirframeInfo]]:
```

Behaviour when `workspace_dir` is provided:

1. Load `exclusions.json` from `workspace_dir` at the start.
2. For each file:
   - If `is_excluded(filename, exclusions)` → skip, mark `·`, don't re-run
     detection (the entry already exists).
   - If identified as a ground session → call `add_auto_exclusion()`,
     then skip.
   - If below `min_flight_duration_min` → call `add_auto_exclusion()`,
     then skip.
   - Otherwise → include in results.
3. Any new entries written during this run are persisted automatically.

When `workspace_dir` is `None` (the default), behaviour is unchanged from
the ground-session spec: auto-detect and skip, but don't persist anything.
This preserves the CLI's ability to run without a workspace.

---

## `config.json` addition

```json
{
  "engine": "916iS",
  "min_flight_duration_min": 10
}
```

`min_flight_duration_min`: integer, minutes. Default `10`. Set to `0` to
disable the short-flight auto-exclusion rule. Does not affect the
ground-session rule (which runs regardless).

---

## CLI integration

### New: `slingology-eis flights` subcommand

Replaces manually inspecting the fleet CSV. Shows the Flights tab view
in the terminal.

```
slingology-eis flights [--workspace DIR] [--show-excluded]
```

**Default output** (excludes excluded flights, shows summary header):

```
N117ZS — 37 flights  ·  14 ground sessions excluded  ·  3 short flights excluded
─────────────────────────────────────────────────────────────────────────────────
2026-08-25  log_20260825_200344_KSFF.csv     94 min  ✓ in baselines
2026-08-18  log_20260818_143201_KAWO.csv     47 min  ✓ in baselines
...
```

**With `--show-excluded`:** also lists excluded flights with their category
and reason:

```
--- Excluded (not in baselines) ---
2026-08-25  log_20260825_194740_KAWO.csv     ground session
2026-08-01  log_20260801_121500_KAWO.csv     short flight (8 min < 10 min)  [overridden by user]
```

### New: `slingology-eis exclude` subcommand

```
slingology-eis exclude FILENAME --reason "ferry flight to maintenance"
slingology-eis include FILENAME --reason "actually want this in baselines"
```

`exclude` adds a `user_defined` entry. `include` sets `user_override: true`
on any existing auto-exclusion, or removes a `user_defined` entry.

---

## Flights tab UI (future)

The exclusions mechanism is designed to back the Flights tab described
in `claude/workspaces-and-log-browser.md` §3. The `exclusion_summary()`
function provides the header counts. The per-row "In baselines" column
maps directly to `is_excluded()`. The toggle in that column calls
`set_user_override()`. No additional data model is needed beyond what
`exclusions.json` already provides.

---

## Files to create / change

| File | Change |
|---|---|
| `slingology_eis/exclusions.py` | New module — full public API above |
| `slingology_eis/loader.py` | Add `workspace_dir` parameter; integrate `is_excluded()` and `add_auto_exclusion()` calls |
| `config.json` | Add `min_flight_duration_min` field |
| `slingology_eis/cli.py` | Add `flights`, `exclude`, `include` subcommands |
| `tests/` | Tests for exclusions module; test that `load_directory()` respects existing exclusions |

---

## Out of scope for this spec

- Mid-log power-cycle detection (B2 backlog) — `corrupt_log` category
  is defined but detection is limited to parse failures and time gaps
  until B2 is implemented.
- UI wireframe for the Flights tab — covered by the workspace design doc.
- Sharing or exporting exclusions as part of a workspace bundle — future.
