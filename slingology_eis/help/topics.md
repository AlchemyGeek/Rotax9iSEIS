# Topic help

Pilot-facing explanations shown behind the `?` on each Flight view topic card and on the flight-summary line (Spec 01 §8.8, Spec 03 §5.2, Spec 10 D13).

Format: one `##` section per entry. The heading is the `topic_id` (or a non-topic `help_id`, e.g. `flight_summary`). It's followed by `key: value` lines (`title`, `applies_to`, `last_reviewed`), a blank line, and exactly one paragraph. Placeholders such as `{limit:oil_temp_max}` are filled in by the engine from the active engine profile, rule set and settings; never write a value that a profile, rule or setting controls.

**Write for any aircraft with this engine, not one aircraft.** Every reader is a different owner with a different installation. Don't state findings from a particular aircraft's data (patterns seen, typical values, how often something has happened), don't cite numbers that aren't the OM's or a placeholder, and describe causes as possibilities ("can point to"), not as what usually turns out to be the case.

## egt_spread
title: Cylinder balance (EGT spread)
applies_to: all
last_reviewed: 2026-10-02

Your engine computer sets the fuel and spark for each cylinder, so the four exhaust gas temperatures (EGTs) should keep a consistent pattern from flight to flight. This topic measures the spread between the hottest and the coolest cylinder in cruise. It compares that spread with your own past flights in similar outside air temperature, and with the Operators Manual limit of {limit:egt_split_high_flow} (which applies when fuel flow is above {profile:egt_spread.high_flow_threshold_lph}). It also watches whether the spread is slowly growing as engine hours build up. A widening spread can point to an injector, spark plug or ignition problem. A single unusual flight is worth noting; a spread that keeps growing over several flights is worth raising with your mechanic. When one cylinder on its own explains the change, it's reported under Cylinder EGT deviation instead, so you see it once.

## egt_cyl_deviation
title: Cylinder EGT deviation
applies_to: all
last_reviewed: 2026-10-02

Every engine has its own cylinder pattern, and on many one cylinder always runs hotter than the rest. Instead of judging cylinders against a generic ideal, this topic compares each cylinder's cruise EGT, measured against the average of the other three, with that same cylinder's own history. It flags a flight that's clearly outside the cylinder's usual range once there are at least {rule:egt_cyl_deviation.baseline_deviation.n_min} comparable flights, and a steady drift up or down as engine hours build up. A cylinder running hotter than usual can mean a lean injector; one running cooler can point to ignition or a spark plug; erratic readings often point to the EGT probe itself. If the change also means a different cylinder is now the hottest, the message says so.

## oil_temp_peak
title: Oil temperature peak
applies_to: all
last_reviewed: 2026-10-05

This shows the highest oil temperature reached during the flight and compares it with your usual peak on flights in similar outside air temperature. Short flights often end before the engine is fully warm, so a lower peak after a short hop is normal. A peak well above your usual can point to reduced oil cooling, for example less airflow through the oil cooler, a partial blockage, or a long climb on a hot day. A peak well below your usual on a full-length flight can mean the oil isn't getting warm enough. If the oil went past the Operators Manual limit of {limit:oil_temp_max}, that's reported once, under Operators Manual limits, and this card shows the same badge.

## coolant_temp_peak
title: Coolant temperature peak
applies_to: all
last_reviewed: 2026-10-05

The cylinder heads are liquid-cooled through the radiator, and this shows the highest coolant temperature reached during the flight, compared with your usual peak on flights in similar outside air temperature. Short flights often end before the engine is fully warm, so a lower peak after a short hop is normal. A peak well above your usual can point to the cooling system: airflow through the radiator, coolant level, the pressure cap or the thermostat. A peak well below your usual on a full-length flight is less common and worth a look at the sensor. If the coolant went past the Operators Manual limit of {limit:coolant_temp_max}, that's reported once, under Operators Manual limits, and this card shows the same badge.

## overboost_time
title: Time at takeoff power
applies_to: all
last_reviewed: 2026-10-05

The Operators Manual allows takeoff power, above {profile:overboost.rpm_threshold} or {profile:overboost.power_pct_threshold} power, for no more than {profile:overboost.limit_s} at a time. This topic measures the longest continuous stretch you spent there on this flight. Going past the limit is reported under Operators Manual limits, and this card shows the same badge. Coming within {profile:overboost.close_call_margin_s} of it is noted as a close call: it often means power wasn't reduced promptly after takeoff, for example during a long climb-out or a delay. Reducing to climb power once you're safely airborne keeps you well clear.

## map_at_takeoff
title: Turbo boost at takeoff
applies_to: [915iS, 916iS]
last_reviewed: 2026-10-02

At full takeoff power the turbocharger should deliver a manifold pressure (MAP) that depends mainly on airport elevation and outside air temperature. This topic learns that relationship from your own takeoffs and compares each takeoff's MAP with what your engine normally makes in the same conditions. A takeoff is flagged when the difference is larger than your takeoffs normally vary, about {config:outlier_z_threshold} times the usual scatter of your own data. Lower than expected can point to the turbo, the wastegate or an intake leak; higher than expected is usually worth a sensor check. If a takeoff's elevation or temperature is outside anything your takeoffs have covered so far, the card says so instead of guessing.

## engine_ecu_inflight
title: Engine computer alerts in flight
applies_to: all
last_reviewed: 2026-10-13

The ENGINE ECU caution comes from the engine computer, and when it appears matters more than that it appears. This card sorts each occurrence by the flight phase it happens in and counts them: at start, while the avionics and the engine computer come up; during the lane check, when each lane is tested on its own; and at shutdown. Those are expected and are only counted here. An occurrence on the ground with the engine running that isn't a lane check, or one in flight from the takeoff roll to the landing roll, appears under the limits and alerts card with the other events of the flight, together with the reason it isn't a lane check when it nearly is one, and you can filter or annotate it there like any limit event. This card only explains and summarises. An occurrence in flight is not expected, and it is worth having the engine computer's fault log read at the next maintenance. The card also says whether the lane check covered both lanes: both lanes ✓, one lane only (the log can't identify the lane), or not detected. Occurrences shorter than {profile:cas.min_event_duration_s} are counted separately and not treated as events, since a single reading can be a logging artefact.

## limit_exceedances
title: Operators Manual limits
applies_to: all
last_reviewed: 2026-10-02

This checks every reading the engine reports against the limits in the Rotax Operators Manual for your engine: temperatures, pressures, RPM, manifold pressure, voltage, EGT split and time at takeoff power. Moments when a reading is expected to be out of range, such as engine start, warm-up or the fuel pump test, are allowed for, and very brief blips are ignored. Each limit that was exceeded appears once, with how long and by how much, and links to that moment on the chart. If a limit is exceeded on every flight because of a known sensor or installation characteristic, you can set a filter with a note; the app keeps watching the filtered limit and tells you if the pattern changes.

## flight_summary
title: Flight summary numbers
applies_to: all
last_reviewed: 2026-10-05

Fuel burned, cruise miles per gallon and average cruise fuel flow are shown for planning, not as engine-health checks. They mostly reflect wind, weight and the power setting you chose rather than the engine itself: miles per gallon uses ground speed, so a headwind lowers it, and fuel flow is an estimate calculated by the engine computer, not a measurement. That's why these numbers never raise an alert.
