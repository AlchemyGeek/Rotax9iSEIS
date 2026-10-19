# Why a FADEC Rotax is different

<div class="in-brief" markdown>
**In brief.** On a Rotax iS engine the engine computer — not you — sets the fuel and the spark. Most engine-analysis tools were built for engines where the pilot leans the mixture by hand, and their signature diagnostics (rich-of-peak, lean-of-peak, mixture sweeps) have no meaning here. SlingologyEIS starts from what the iS engine actually controls and what its log actually contains, which is why its topics look different from what you may have seen elsewhere.
</div>

## What the engine computer does

The 912iS, 915iS and 916iS are *full-authority* engines: a dual-redundant engine control unit (two lanes, A and B) reads throttle position, air temperature, manifold pressure and the rest, and from them decides injector timing, ignition advance and — above roughly 97 % throttle — whether the engine runs in ECO or POWER mode. There is no mixture lever and no magneto switch. The pilot has one input, the throttle, and the computer does the rest.

That is good news for engine health: the mixture is always what the computer intends, so a cylinder running hot or cool is telling you about *that cylinder* — its injector, plug, probe or airflow — not about how the engine was leaned. It also means the pilot-centred diagnostics of other tools do not apply.

## What other tools assume

Platforms such as Savvy Aviation and FlySto grew up around Lycoming and Continental engines, where the central engine-management question is how the pilot handles the mixture. Their signature analyses — finding peak EGT during a lean sweep, judging rich-of-peak versus lean-of-peak operation, spotting an exhaust valve from the EGT pattern during leaning — depend on the mixture being varied by hand. On a FADEC engine the mixture is never varied by hand, so those analyses either cannot run or produce noise. FlySto will replay your flight and graph any channel, which is useful, but it has no engine-health model for an iS engine. Rotax's own diagnostic software reads the engine computer's fault log directly, but it needs a hardware interface and is used at maintenance, not after every flight.

So a pilot with a Rotax iS engine and a modern glass panel has been collecting a rich engine log every flight with nothing designed to read it. That is the gap this app fills.

## What is, and is not, in the log

Everything the app knows comes from the engine log your Garmin avionics write — G3X, Garmin Pilot export or AXIS. That log carries RPM, manifold pressure, oil temperature and pressure, coolant temperature, four exhaust gas temperatures, fuel pressure and flow, bus voltage, the CAS alerts, and the flight data (airspeed, altitude, position, outside air temperature) that the app needs to work out what phase of flight you were in.

Some things the engine computer knows never reach the log: throttle position, which lane is active, injector pulse width, ignition advance, wastegate position. The app does not try to guess them. Two consequences matter to how you read its output:

- **Fuel flow is an estimate.** The Rotax iS reports a fuel flow calculated by the engine computer from injector timing, not measured by a sensor, and Rotax quotes a tolerance of about ±10 %. That is why fuel burned and miles per gallon appear as *flight facts* for your planning and never raise an alert.
- **The cooling system is split.** The cylinder heads are liquid-cooled and the barrels air-cooled, so the health signals are **coolant temperature** and **EGT**, not cylinder-head temperature as on an air-cooled engine. The app's thermal topics follow that split.

## How this shapes the topics

With the mixture fixed by the computer, the useful questions become:

- Are the four cylinders behaving as a matched set, and is the one that runs hottest the one that usually does? → [Cylinder balance](cylinder-balance.md)
- Are the oil and coolant peaks what they usually are for this weather? → oil and coolant peak topics
- Is the turbocharger delivering the boost it usually does for this elevation and temperature? → *Turbo boost at takeoff* (915iS and 916iS)
- Did you stay within the time the manual allows at takeoff power? → *Time at takeoff power*
- Did the engine computer raise an alert at a moment when it shouldn't? → *Engine computer alerts in flight*

And underneath all of them, the Operators Manual limits, checked with an understanding of when a reading is *expected* to be out of range. See [The topics](the-topics.md) for the full list and [Operators Manual limits and events](limits-and-events.md) for how limits are checked.

---

*Further reading: the research paper [Rotax 91XiS Engine Data Analytics](../reference/further-reading.md), sections 1–3, sets out this argument in full with references to the Rotax documentation.*
