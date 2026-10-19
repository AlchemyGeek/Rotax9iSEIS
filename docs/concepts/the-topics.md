# The topics

<div class="in-brief" markdown>
**In brief.** Eight topics have a card on every Flight view. Each one below says what it measures, what it is compared against, when its insight fires and what the insight can point to. The text is the same as behind the **?** on each card, with the Operators Manual values filled in for the 916iS; on a 915iS or 912iS the card shows that engine's values. The **status** line says on which engines the topic has been validated with real data.
</div>

Every topic was developed and validated on a Rotax 916iS. On the 915iS and 912iS the same analysis runs, but until logs from such an aircraft have confirmed it behaves sensibly there, the card carries *Not yet validated on this engine*. One topic does not exist on the 912iS at all, because the engine has no turbocharger.

| Topic | 916iS | 915iS | 912iS |
|---|---|---|---|
| Cylinder balance (EGT spread) | validated | unverified | unverified |
| Cylinder EGT deviation | validated | unverified | unverified |
| Oil temperature peak | validated | unverified | unverified |
| Coolant temperature peak | validated | unverified | unverified |
| Time at takeoff power | validated | unverified | unverified |
| Turbo boost at takeoff | validated | unverified | — |
| Engine computer alerts in flight | provisional | unverified | unverified |
| Operators Manual limits | validated | unverified | unverified |

*Provisional* on the engine computer alerts means the sorting of alerts by phase has been checked against many flights, but no genuine in-flight alert has yet occurred in the data, so that case has not been seen for real.

---

## Cylinder balance (EGT spread)

Your engine computer sets the fuel and spark for each cylinder, so the four exhaust gas temperatures (EGTs) should keep a consistent pattern from flight to flight. This topic measures the spread between the hottest and the coolest cylinder in cruise. It compares that spread with your own past flights in similar outside air temperature, and with the Operators Manual limit of 392 °F (which applies when fuel flow is above 3 L/h, i.e. at any normal power setting). It also watches whether the spread is slowly growing as engine hours build up.

A widening spread can point to an injector, spark plug or ignition problem. A single unusual flight is worth noting; a spread that keeps growing over several flights is worth raising with your mechanic. When one cylinder on its own explains the change, it is reported under *Cylinder EGT deviation* instead, so you see it once.

*Measured in:* cruise. *Compared with:* your reference (same temperature band) and the OM split limit. *Insight fires on:* a flight outside your usual range, or a widening trend over engine hours. See [Cylinder balance](cylinder-balance.md).

## Cylinder EGT deviation

Every engine has its own cylinder pattern, and on many one cylinder always runs hotter than the rest. Instead of judging cylinders against a generic ideal, this topic compares each cylinder's cruise EGT, measured against the average of the other three, with that same cylinder's own history. It flags a flight that is clearly outside the cylinder's usual range once there are at least 10 comparable flights, and a steady drift up or down as engine hours build up.

A cylinder running hotter than usual can mean a lean injector; one running cooler can point to ignition or a spark plug; erratic readings often point to the EGT probe itself. If the change also means a different cylinder is now the hottest, the message says so.

*Measured in:* cruise. *Compared with:* each cylinder's own reference (same temperature band). *Insight fires on:* a cylinder outside its usual range, or a trend in either direction.

## Oil temperature peak

This shows the highest oil temperature reached during the flight and compares it with your usual peak on flights in similar outside air temperature. Short flights often end before the engine is fully warm, so a lower peak after a short hop is normal.

A peak well above your usual can point to reduced oil cooling — less airflow through the oil cooler, a partial blockage, or a long climb on a hot day. A peak well below your usual on a full-length flight can mean the oil is not getting warm enough. If the oil went past the Operators Manual limit of 248 °F, that is reported once, under *Operators Manual limits*, and this card shows the same badge.

*Measured over:* the whole flight. *Compared with:* your reference (same temperature band). *Insight fires on:* a peak outside your usual range.

## Coolant temperature peak

The cylinder heads are liquid-cooled through the radiator, and this shows the highest coolant temperature reached during the flight, compared with your usual peak on flights in similar outside air temperature. Short flights often end before the engine is fully warm, so a lower peak after a short hop is normal.

A peak well above your usual can point to the cooling system: airflow through the radiator, coolant level, the pressure cap or the thermostat. A peak well below your usual on a full-length flight is less common and worth a look at the sensor. If the coolant went past the Operators Manual limit of 248 °F, that is reported once, under *Operators Manual limits*, and this card shows the same badge.

*Measured over:* the whole flight. *Compared with:* your reference (same temperature band). *Insight fires on:* a peak outside your usual range.

## Time at takeoff power

The Operators Manual allows takeoff power — above 5,500 rpm or 100 % power — for no more than 5 minutes at a time. This topic measures the longest continuous stretch you spent there on this flight. Going past the limit is reported under *Operators Manual limits*, and this card shows the same badge. Coming within 60 seconds of it is noted as a **close call**: it often means power was not reduced promptly after takeoff, for example during a long climb-out or a delay. Reducing to climb power once you are safely airborne keeps you well clear.

*Measured over:* every second above the takeoff-power threshold. *Compared with:* the OM limit only. *Insight fires on:* the limit event, or a close call.

## Turbo boost at takeoff

*915iS and 916iS only.* At full takeoff power the turbocharger should deliver a manifold pressure (MAP) that depends mainly on airport elevation and outside air temperature. This topic learns that relationship from your own takeoffs and compares each takeoff's MAP with what your engine normally makes in the same conditions. A takeoff is flagged when the difference is larger than your takeoffs normally vary — about 2 times the usual scatter of your own data.

Lower than expected can point to the turbo, the wastegate or an intake leak; higher than expected is usually worth a sensor check. If a takeoff's elevation or temperature is outside anything your takeoffs have covered so far, the card says so instead of guessing.

*Measured in:* the takeoff roll, at full power. *Compared with:* your own boost model (needs 5 takeoffs). *Insight fires on:* a takeoff further from the model than your takeoffs normally scatter.

## Engine computer alerts in flight

The ENGINE ECU caution comes from the engine computer, and *when* it appears matters more than that it appears. This card sorts each occurrence by the flight phase it happens in and counts them: at start, while the avionics and the engine computer come up; during the lane check, when each lane is tested on its own; and at shutdown. Those are expected and are only counted here.

An occurrence on the ground with the engine running that is not a lane check, or one in flight from the takeoff roll to the landing roll, appears in the Events table with the other events of the flight, together with the reason it is not a lane check when it nearly is one, and you can filter or annotate it there like any limit event. An occurrence in flight is not expected, and it is worth having the engine computer's fault log read at the next maintenance. The card also says whether the lane check covered both lanes: *both lanes ✓*, *one lane only* (the log cannot identify the lane), or *not detected*. Occurrences shorter than 3 seconds are counted separately and not treated as events, since a single reading can be a logging artefact.

*Measured over:* the whole log, including the ground. *Compared with:* the expected pattern. *Insight fires:* never from this card — the unexpected occurrences are events on the limits card.

## Operators Manual limits

This checks every reading the engine reports against the limits in the Rotax Operators Manual for your engine: temperatures, pressures, RPM, manifold pressure, voltage, EGT split and time at takeoff power. Moments when a reading is expected to be out of range, such as engine start, warm-up or the fuel pump test, are allowed for, and very brief blips are ignored. Each limit that was exceeded appears once, with how long and by how much, and links to that moment on the chart. If a limit is exceeded on every flight because of a known sensor or installation characteristic, you can set a filter with a note; the app keeps watching the filtered limit and tells you if the pattern changes.

*Compared with:* the OM, with phase awareness. *Insight fires on:* any event. See [Operators Manual limits and events](limits-and-events.md).

---

## Flight facts

Not a topic, but shown in the Flight view header: **fuel burned**, **cruise miles per gallon**, **average cruise fuel flow** and the **lane check** result. They are shown for planning, not as engine-health checks. They mostly reflect wind, weight and the power setting you chose rather than the engine itself: miles per gallon uses ground speed, so a headwind lowers it, and fuel flow is an estimate calculated by the engine computer, not a measurement. That is why these numbers never raise an alert.

## Topics you will not see

Two things the app once tried are deliberately not topics. **Climb thermal rate** — how fast oil and coolant warm during the climb — turned out to vary more flight to flight than any change it could detect, so it is computed for research only and has no card. **Cruise efficiency** and **cruise fuel flow** were topics for a while and are now flight facts, for the reasons above. The app also never tries to detect ECO/POWER mode, because the throttle position that governs it is not in the log.
