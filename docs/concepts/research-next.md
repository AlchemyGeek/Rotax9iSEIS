# Questions Research will ask next

<div class="in-brief" markdown>
**In brief.** EIS measures four kinds of question today. Six more are designed and will become instruments as they are built and measured against real logs. Until then Claude can ask any of them in a notebook with its own code against your logs — the instrument makes them faster, referenced and comparable, not possible.
</div>

| Question | What it would tell you |
|---|---|
| **Is this response damped, or self-sustaining?** | Whether a wobble dies away after a disturbance (a controller settling) or keeps going by itself (a limit cycle, as in the oscillation case) |
| **Is this what the Operators Manual says it should be?** | How far manifold pressure, fuel flow or temperatures sit from the Manual's engine deck for that rpm and altitude |
| **When did it change within the flight?** | The moment a signal's level or steadiness shifted inside a slice — a step in one EGT, an oil-pressure step |
| **Is this cylinder behaving like the others?** | One cylinder's EGT with the engine-wide movement removed, so its own dips and drift stand out |
| **Does it depend on conditions?** | How a measurement varies with density altitude, outside air temperature or wind |
| **Is the sensor or log healthy?** | Dropouts, stuck values, step sizes and noise, by log source |

Each will follow the rules of the four that exist ([What EIS measures](../reference/what-eis-measures.md)): a count, a reference beside every number, no verdict. Research will not acquire thresholds of its own or grade findings by severity. If one of these is the one you need, the feedback board is the place to say so.

Spec 06 §7.5 specifies the six; §14 the scan and the shared detectors that may follow.
