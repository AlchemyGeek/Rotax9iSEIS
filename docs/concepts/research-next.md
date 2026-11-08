# Questions Research will ask next

<div class="in-brief" markdown>
**In brief.** Four questions ship today. Six more are designed and will arrive as they are built and measured against real logs; three open questions from the app's own research are waiting for one of them; and two larger ideas — an automatic scan that only speaks when a pattern recurs across flights, and an assistant that runs investigations for you with your own AI — are sketched but not promised. This page says what each would do, in plain words, so you know what to expect and what not to.
</div>

## Six more questions

| Question | What it would tell you | What it would catch |
|---|---|---|
| **Is this response damped, or self-sustaining?** | Whether a wobble dies away after a disturbance (a healthy controller settling) or keeps going by itself (a limit cycle, as in the oscillation case) | Governor and boost-control health, told apart from ordinary settling |
| **Is this what the Operators Manual says it should be?** | How far manifold pressure, fuel flow or temperatures sit from the Manual's engine deck for that rpm and altitude, and whether the gap wobbles, steps or drifts | Boost control at its ceiling, wastegate behaviour, a mis-reading sensor |
| **When did it change within the flight?** | The moment a signal's level or steadiness shifted inside a slice | A step in one EGT when an engine-computer lane switches, an injector dropping out, an oil-pressure step |
| **Is this cylinder behaving like the others?** | One cylinder's EGT with the common engine-wide movement removed, so its own dips and drift stand out | Misfire, injector or ignition imbalance — alongside the Cylinder balance topic |
| **Does it depend on conditions?** | How a measurement varies with density altitude, outside air temperature or wind | Cause hunting — the oscillation's dependence on altitude was the clue to its mechanism |
| **Is the sensor or log healthy?** | Dropouts, stuck values, step sizes and noise, by log source | Instrument artefacts before they are mistaken for engine behaviour |

Each will follow the same rules as the four that exist: a question in your words, the five-part result, references you can see, no verdict.

## Three questions the app's own research left open

When the app's topics were audited, three measurements were set aside as *needs research* because they were too noisy to report as insights: how fast oil and coolant warm in a climb, once climb rate, power and outside temperature are accounted for; whether fuel flow follows power and altitude as the engine computer's map would predict; and how high oil and coolant peak given how long the flight was and how warm the day. All three are *does it depend on conditions?* questions. When that question ships, the three will come as example studies you can run on your own flights.

## Two larger ideas

**A scan that speaks only when a pattern recurs.** Today *Which slices are unusual?* runs when you ask. The designed next step runs it automatically on each preset's slices after an import, and surfaces a short list on the Research page *only when a pattern holds across many flights* — so many of so many, both numbers visible and yours to set. Single odd flights stay where they are, in the Flight view and the Events table. The list would appear on the Research page, never on a flight's cards.

**Investigations.** The oscillation case was investigated by a person asking an AI assistant to run exactly the questions this app now contains. The designed idea is to let the app do the same for you: an assistant that takes the scan's list or your question, runs Research's questions, reads the Operators Manual and service documents, and writes up what it found — observation, possible causes, what to do, evidence package — in the same five-part shape. Three things are fixed about it already: it would connect to **your own AI provider with your own key** — the app runs no service and stores nothing; only the measurements leave your machine, never your logs, and only with your consent; and every sentence it writes must trace to a result or a cited document, or be labelled a hypothesis. It is a future capability, not a current one, and it does not replace the deterministic insights the app already produces.

## What is not planned

Research will not acquire thresholds of its own, will not grade findings by severity, and will not change what Limits, Trends or the Journal do. Shared **detectors** — a study's rule packaged with its author's explanation, installed by owners who want it — are designed as something owners build and share, never something the app ships.

## What to do with this

If one of the six questions is the one you need now, the feedback board is the place to say so; the order in which they are built is open. Until then, the four that exist cover more than they seem to: the oscillation case needed only the first three.

## How it works

The six questions are specified in Spec 06 §7.5 and share the slice, descriptor and result machinery of the four that ship; each needs its own measurement against real logs before it is turned on. The scan is §14.1, Investigations §14.2, detectors §14.3, and the example studies §14.6.
