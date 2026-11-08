# Research presets

The slice rules the app ships, what each isolates, and how each behaved when measured against a real season of flights. A preset is an ordinary rule: copy it and change any number. The rpm bands below are the Rotax 916iS's; other engine profiles carry the same values marked *unverified* until logs from such an aircraft confirm them.

## The five presets

| Preset | Conditions | Lasts at least | Bridge gaps under | Within | Isolates | Asks first |
|---|---|---|---|---|---|---|
| **Full-power segment** | rpm ≥ 5,550 | 15 s | 3 s | — | Takeoff and go-around power | Is rpm steady, or cycling? |
| **Governed climb** | rpm 5,300–5,500 · vertical speed ≥ 300 fpm | 60 s | 5 s | — | Climb under the propeller governor | Is rpm steady, or cycling? |
| **Stable cruise** | rpm 4,800–5,300 | 300 s | 5 s | cruise | The steady stretches of a cruise | Which slices are unusual? |
| **Idle** | rpm < 2,200 | 30 s | 3 s | taxi | Idle quality, taxi out and taxi in | Is rpm steady, or cycling? |
| **Warm-up** | rpm ≥ 1,000 · oil temperature below the profile's takeoff minimum (122 °F on the 916iS) | 60 s | 5 s | engine start, warm-up or taxi | From start until the oil is warm | Which slices are unusual? |

*Within* restricts the rule to a phase the app already identifies on the flight. *Bridge gaps under* keeps a brief dip from splitting one slice into two.

## How they were measured

Each candidate rule was run over one aircraft's 60 flights (April–October 2026, Garmin G3X then AXIS logs). The test for a preset: about one slice per flight that contains the manoeuvre, durations in a plausible band, and no slice spanning two occurrences of the manoeuvre.

| Preset | Slices | Flights with one | Most in one flight | Duration: median (10th–90th percentile) |
|---|---|---|---|---|
| Full-power segment | 98 | 59 of 60 | 9 | 54 s (41–72) |
| Governed climb | 92 | 48 | 7 | 126 s (73–301) |
| Stable cruise | 108 | 38 | 10 | 712 s (340–3,286) |
| Idle | 161 | 59 | 7 | 95 s (39–235) |
| Warm-up | 44 | 44 | 1 | 256 s (162–324) |

What the measurement changed, and why some flights have several slices:

- **Full-power segment** — kept as first written. Flights with several slices are touch-and-go sessions (up to nine takeoffs in one flight). The app's phase labelling marks one takeoff roll per landing sequence and misses touch-and-go rolls, so the rule sees more takeoffs than the phases do; that is a fact about the phases, not the rule.
- **Governed climb** — kept. A climb interrupted by a level-off is two slices, which is what happened.
- **Stable cruise** — the minimum was raised from 120 s to 300 s. At two minutes every power change on a cross-country cut the cruise into pieces (211 slices, up to 25 in one flight); at five minutes the rule finds the steady stretches. Twenty-two flights had no five-minute cruise at all — pattern work.
- **Idle** — *on the ground* was made *within taxi*. Across all ground phases, fourteen slices ran from the taxi out, through the run-up, into the next taxi; within taxi, one did.
- **Warm-up** — written as a rule because the app's own warm-up phase is short and interleaved with taxi; hence the three ground phases. Sixteen flights had no warm-up slice: the engine started with the oil already at the takeoff minimum.

## Windows the questions use with these presets

The questions size their measurement windows from the data (see [Research questions and parameters](research-questions.md)). On the full-power set they resolve to the floors — a 12-second swing window and a ±10-second lag search; on the stable-cruise set, whose slices are long and have no dominant period, to 142 seconds and ±71 seconds.

## Changing a preset

On the Research page or in a study, **Add a preset**, then **Edit…**: rename it, change a value, add or remove a condition, change the phase. The copy is a rule of your workspace; the shipped preset is unchanged. Studies store the rule they used, so editing a copy later does not alter a saved study.

Spec 06 §5.2 records the presets and the full measurement.
