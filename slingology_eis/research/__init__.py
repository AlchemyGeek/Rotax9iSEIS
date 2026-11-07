"""
research — Spec 06: within-flight signal shape, compared across many
slices of many flights.

- `rules`       slice rules (§5.1, §5.3) and hand slices (§5.4) → windows
- `presets`     the shipped rules, per engine profile (§5.2)
- `descriptors` per-slice, per-channel numbers (§6) and the §7.0 window rule
- `questions`   the four v1 tests (§7.1–7.4) returning the §8 contract
- `slices`      building a slice set over a workspace's logs (§5.5)
- `studies`     the saved study, its descriptor cache, `.eisstudy` (§10)
- `render`      plain-text and SVG renderings of a result

Research ships no rules and no verdicts (goal 4): the only built-in
references are OM values already in the engine profile.
"""
TEST_IDS = ("cycling", "coupling", "groups", "unusual")
