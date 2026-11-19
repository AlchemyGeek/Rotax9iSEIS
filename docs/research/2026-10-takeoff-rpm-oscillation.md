---
title: Takeoff RPM/MAP oscillation (N117ZS, Oct 2026)
---

> Owner's investigation write-up, rev 3 (2026-10-29), kept as the acceptance case for Spec 06 (Research). Per-flight detail in Appendix A is published with the owner's consent (CLAUDE.md, data rules). The Airmaster correspondence section of the original is not reproduced.

# N117ZS — Takeoff RPM/MAP Oscillation Investigation

Aircraft: Sling TSi N117ZS (S/N 654SQ), Rotax 916iS S/N 10010552, Airmaster AP431HCTF S/N 2839 (3-blade SNR72K, 72 in, feathering; fine stop 7°24′, feather 87°) with AC300F controller S/N 3016 (firmware 10.139, hub DSD 1.43, programmed 20 Nov 2025, set up for Rotax 916), Garmin AXIS (G3X Touch before Oct 2026).

Controller presets as delivered (propeller logbook, Leading Particulars – Controller): **Take-Off 5700, Climb 5400, Cruise 5000, Hold preset 4800, Hold range 4000–5700.**
Status as of 2026-10-29 (rev 3): **Airmaster confirms this is a known 916iS behaviour and that controller and hub firmware updates address it. Remote support/configuration session with Airmaster to be scheduled; diagnostic test flight superseded by a before/after comparison.** No airworthiness action taken (see §6).

Change log
- 2026-10-29 — Initial write-up after analysis of 98 takeoffs (Apr 8 – Oct 28 2026) and Rotax OM-916 i A/C24 Ed0 Rev1.
- 2026-10-29 (rev 3) — Email sent to Airmaster (configuration, symptom, example plot, 94/98 figure). Same-day reply: "known behaviour" on the 916iS; firmware updates for controller and hub address the TO-mode hunting, "still having teething problems with some customers but the severity is much less"; Airmaster now performs the updates and diagnostics download by remote session into the customer's PC rather than sending instructions. Reply sent proposing Pacific afternoon slots and asking what to have ready (Windows laptop, A0117 cable on CN4, aircraft power) and which versions will be installed.
- 2026-10-29 (rev 2) — Propeller logbook reviewed: controller is AC300F and the Take-Off preset is **5700, not 5800**. Mean rpm in every takeoff (5705–5715) matches that setpoint. Test plan revised: Hold steps at 5600/5550/5500 instead of 5700; Manual test unchanged.

---

## 1. Symptom

With the Airmaster controller in Takeoff mode (preset **5700** rpm) and wide-open throttle, engine rpm does not hold steady. It cycles by roughly ±90 rpm around the 5700 setpoint with a period of 4–5 s, and manifold pressure cycles with it between ~45 and ~50 inHg. Fuel flow follows one second behind. Power varies roughly ±6% per cycle. The oscillation begins the moment rpm passes ~5600 (at rotation on a normal takeoff; within 2 s on a touch-and-go) and stops the moment Climb mode (5400 rpm) is selected, with throttle unchanged. Climb and Cruise modes are steady.

First noticed by the pilot on 2026-10-24 during a touch-and-go at KBLI, as a fore-aft surge felt in the climb in calm air.

## 2. Data

### 2.1 Sources
- 121 CSV logs from the owner’s log set (the flights dated through 2026-10-28): Garmin G3X Touch (GDU 460, 1 Hz) from 2026-04-08 (28 engine hours, Phase 1 at KTOA) through 2026-10-05, and Garmin AXIS (1 Hz) from 2026-10-14 through 2026-10-28.
- Every segment with rpm ≥ 5550 for ≥ 15 s was extracted (98 distinct segments after removing duplicate files). Metrics per segment: rpm and MAP min/max, median 12-second rpm peak-to-peak ("swing"), period (peak counting), rpm–MAP correlation, OAT, pressure and density altitude, wind, vertical-g scatter.
- 46 logs contained no full-power segment (taxi/ground runs, partial exports); 14 were startup-only fragments.

### 2.2 Headline result
**94 of 98 takeoffs oscillate.** Median swing 180 rpm (range 140–240), period 4.4 s (IQR 4.1–4.8). Amplitude and period are the same in April (28–33 hr) as in October (145 hr), and the same on G3X and AXIS logs. Nothing has drifted; this is a structural characteristic of the installation from delivery.

| DA band | takeoffs | median rpm swing | typical MAP peak |
|---|---|---|---|
| < 3000 ft | 92 | 180 rpm | 49–50 inHg |
| 3500–4900 ft (KACV, KSFF, KRAP) | 3 | 125–140 rpm ("weak") | 49.9 |
| 6000–6350 ft (KBIL, KHLN) | 2 | 70–80 rpm (clean) | 51.4–51.5 |

- Amplitude vs density altitude: r = −0.50 (monotonic decline above ~3500 ft DA).
- Amplitude vs OAT at a given DA: r = 0.05 (no effect). Amplitude vs turbulence (vertical-g scatter): no effect.
- Rpm–MAP correlation at zero lag: 0.89–0.97 on AXIS logs; 0.1–0.3 on G3X logs. The G3X appears to damp its MAP channel (2 inHg ripple vs 5–7 inHg on AXIS for the same oscillation); rpm amplitude is identical on both, so the G3X MAP traces are treated as smoothed.
- Ground roll is clean on normal takeoffs (5520–5550 rpm, MAP 42.5–43, prop on fine-pitch stop); oscillation starts when rpm passes ~5600.
- Climb mode at WOT: 12-s rpm ripple 20–75 rpm, MAP ripple 0.1–0.9 inHg, in every log checked.

### 2.3 Example: 2026-10-24, three takeoffs (AXIS)
| Takeoff | rpm swing | MAP range | period | OAT / PA |
|---|---|---|---|---|
| KAWO 15:26 | ~±110 | 43.4–50.0 | 3.7 s | 5 °C / −150 ft |
| KPAE 15:51 | ~±100 | 43.4–49.9 | 4.3 s | 6 °C / 1430 ft |
| KBLI T&G 16:22 | ~±100 | 44.4–49.9 | 4.0 s | 5 °C / 2380 ft |

Longitudinal acceleration correlates with rpm at zero lag (0.42 / 0.33 / 0.52). The KBLI event was felt because the air was calmest (vertical-g σ 0.050 vs 0.063 / 0.077; wind 5 kt vs 11–13 kt), not because the oscillation was larger.

## 3. Mechanism

Two correctly-functioning controllers are coupled through the 916iS boost schedule.

**Rotax side (OM-916 i A/C24, Ed0 Rev1).** Chapter 5 engine deck, WOT, sea level, ISA:

| rpm | p_plenum | power |
|---|---|---|
| 5000 | 1409 mbar (41.6 inHg) | 92.8 kW |
| 5500 | 1484 mbar (43.8 inHg) | 104.7 kW |
| 5800 | 1722 mbar (50.8 inHg) | 119.0 kW |

The boost target rises 75 mbar from 5000 to 5500 rpm and 238 mbar from 5500 to 5800: the entire takeoff boost increment, and a 14% power step, is scheduled inside the last 300 rpm. §2.1 states the same targets (1480 mbar at 5500, 1690 at 5800, 25–35 °C). The logged data sits exactly on this curve: across one cycle the plenum pressure moves between ~1520 and ~1690 mbar as rpm swings about the setpoint. The ECU is doing what the manual says.

**Airmaster side.** The AC300F governs rpm by driving blade pitch with an electric actuator through a digital control loop; the operator's manual describes a non-linear response with software-set parameters and a governing band of roughly ±100 rpm. It is inherently slower than a hydraulic governor.

**The loop.** Rpm droops slightly → ECU lowers the boost target (wastegate opens) → power falls → rpm droops further → governor fines pitch → rpm rises past the setpoint → ECU raises boost → power rises → rpm rises further. Turbo spool lag on one side and actuator lag on the other give a natural period of ~4.4 s. In Climb mode (5400 rpm) the boost target is nearly flat with rpm, so there is nothing to feed back and the governor holds steady. Note that the setpoint is already 100 rpm below the engine limit — the usual "set TO to 5700" advice for Airmaster/Rotax installations is already applied and does not prevent the loop.

**Hot-and-high exceptions.** The engine deck shows the same ramp at 3000 and 6000 ft, so the ramp does not disappear with altitude. At KBIL and KHLN (DA ~6000–6350 ft) MAP sat flat at 51.4–51.5 inHg (~1744 mbar), at the 1750 mbar "not to exceed" value the OM says the boost control uses. With boost pinned at its ceiling it no longer varies with rpm, the feedback path is open, and only ordinary governing ripple remains. (A contributing factor may be the prop sitting closer to its fine-pitch stop at altitude, reducing governor authority.)

**Attribution.** The boost ramp is universal to every 916iS; the overwhelming majority of 916 TSis fly MT hydraulic governors and show no reported hunting, and Rotax certified the engine against a hydraulic governor. The variable is governor response. This is therefore an Airmaster tuning question for the AP431/AC200 on the 916iS, not an engine fault — and not an Airmaster defect either, but a combination neither party appears to have tested for. The AP431 for the 916 shipped in 2025; N117ZS is one of the earliest installs.

## 4. Hypotheses considered and eliminated
- Governor hunting alone (constant boost): no — MAP swings 5–7 inHg in lockstep with rpm.
- ECU speed-limiter intervention: no — no fuel/EGT signature; the oscillation starts at 5600, well below the limit, and its amplitude is set by the governor, not clipped by the limiter.
- Overload clutch slip (SB-916i-003 signature: spike to 6500 then dip to 4000): no — wrong waveform.
- Touch-and-go / boost-transient specific: no — present on every normal takeoff.
- Slipring/brush/actuator wear: no — amplitude identical from 28 hr to 145 hr. (Slipring inspection still worth doing at next opportunity per Airmaster schedule, 145 hr with none recorded.)
- Turbulence or OAT: no correlation.
- Display artifact: no — identical rpm amplitude on G3X and AXIS.

## 5. Why it went unnoticed for 145 hours
Onset is at rotation, when attention is outside; it ends at the Climb selection ~40 s later. The G3X damped engine data and a ±90 rpm needle movement on a 6000-rpm arc is not conspicuous; the AXIS shows raw CAN values. The surge is ~0.04 g, which is masked by light chop and only stands out in calm air. A TAF test pilot, the CFI, and the owner all flew behind it without noticing; nobody missed anything obvious.

## 6. Limits status (OM-916 i A/C24 §2.1, §3.5)
- Manifold pressure: limit 1800 hPa (53.15 inHg); boost-control "not to exceed" 1750 mbar. Logged maximum 51.5 inHg (~1744 mbar). **Inside limits.**
- Engine speed: limit 5800 rpm (max 5 min). Governor setpoint 5700, 100 rpm below the limit; the cycle is a swing about that setpoint. Logged values were reviewed against the OM §3.5 exceedance rule and the MML (05-50-00) as part of this investigation; any logbook entry required is the owner's, outside this document.
- Hot-and-high plenum pressure (1744 mbar) exceeds the engine-deck value for those conditions (1711–1731) but is below the 1750 boost-control ceiling.

## 7. Resolution path (supersedes the diagnostic test plan)
Airmaster has identified the cause on their side and will update controller and hub firmware by remote session (website lists AC300 firmware 10_158, 9 Apr 2026, and hub DSD firmware 1_50, 28 Mar 2026; N117ZS has 10.139 / 1.43 from Nov 2025). Plan:
1. Remote session with Airmaster: diagnostics download (before), firmware update, parameter check. Record versions and any preset changes in the propeller logbook.
2. After the update: one normal takeoff in TO mode at KAWO on a cool day with AXIS logging; compare rpm/MAP amplitude and period against the Appendix A baseline on the same plot. Target: no sustained cycling.
3. If residual hunting remains ("teething problems"): send Airmaster the AXIS log and a controller diagnostics download for the same takeoff.
4. Interim operation until the update: Climb mode (5400) for routine takeoffs from long runways gives a steady ~100 kW (≈ 915iS takeoff power); TO mode where performance is needed. Not an engine-protection necessity on the data, but it removes the cycling.

The Hold/Manual discrimination flight (checklist rev 2) is retained in the project only as a record; it is no longer needed.

## 8. Open questions
- What the firmware changes (gain, deadband, rate) and what the remaining "teething problems" look like on other 916 installs — ask during the session.
- Whether the TO preset stays at 5700 after the update.
- Rotax Installation Manual: any governor response requirement or guidance on in-flight-adjustable props with the 916 boost schedule. Also the "CSA — Constant Speed Actuator" abbreviation in the OM suggests ECU provisions for a constant-speed system; ask Rotax what the ECU exposes.
- Rotax ECU (BUDS) log of a takeoff: PCV duty cycle and TPS on the same timeline as rpm would close the boost-loop description.

## 9. References
- Rotax OM-916 i A/C24 Series, Ed0 Rev1 (Dec 2023): §2.1 operating limits (engine speed, manifold pressure, target pressures), §3.5 exceedance of operational limits, §7.6 air intake and boost pressure control, Ch. 5 engine deck.
- Airmaster AP3/4/5 series Operator's Manual V5-1A (Hold and Manual mode operation, control loop description).
- Airmaster SI-006 AC200 Operator Program Instructions R2b (operator-changeable flight variables; Hold RPM Max ≥ 100 rpm below engine max; A0117 cable). N117ZS has an AC300F — confirm the equivalent procedure with Airmaster.
- N117ZS Airmaster Propeller Logbook, Leading Particulars (propeller) and Leading Particulars (controller), Rev1a.
- Rotax SB-916i-003 / 915i-014 (overload clutch overspeed signature — ruled out).
- Rotax-Owner.com thread 10523 (Airmaster governing band ±100 rpm; T/O preset 5700 practice).
- Reproducible in SlingologyEIS Research (Spec 06): the *Full-power segment* preset over the flights dated through 2026-10-28 gives the Appendix A slice set; tests 7.1–7.4 give the swing, coupling, DA dependence and the two clean outliers. The app's period estimators give 3.8 s (IQR 3.5–4.1) where this write-up's peak count gave 4.4 s; see Spec 06 Q11.

---

## Appendix A — Every full-power segment, Apr–Oct 2026

Swing = median 12-s rpm peak-to-peak about the 5700 setpoint. Class: OSC ≥ 130, weak 91–129, clean ≤ 90. Times are local. Eng hrs from G3X header (not present in AXIS logs).

| Date | Eng hrs | Src | Start | Dur s | Swing | MAP min | MAP max | Period s | OAT | DA ft | Wind | Class |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-04-08 | 28.2 | G3X | 14:43:37 | 59 | 200 | 35.1 | 50.4 | 4.8 | 25.0 | 1682 |  | OSC |
| 2026-04-09 | 29 | G3X | 13:00:27 | 38 | 230 | 38.3 | 49.8 | 5.3 | 21.0 | 894 |  | OSC |
| 2026-04-17 | 29.4 | G3X | 11:46:01 | 60 | 220 | 39.8 | 49.5 | 4.2 | 22.0 | 1353 |  | OSC |
| 2026-04-21 | 30.2 | G3X | 22:05:48 | 76 | 180 | 44.1 | 49.5 | 3.9 | 20.6 | 1298 | 13 | OSC |
| 2026-04-21 | 30.2 | G3X | 23:07:36 | 55 | 170 | 37.8 | 49.1 | 5.4 | 19.4 | 1085 |  | OSC |
| 2026-04-22 | 32.5 | G3X | 18:53:37 | 39 | 230 | 38.5 | 49.0 | 4.8 | 20.4 | 652 |  | OSC |
| 2026-04-23 | 33 | G3X | 14:23:01 | 377 | 125 | 43.6 | 49.9 | 4.8 | 12.1 | 3977 | 13 | weak |
| 2026-04-23 | 38.2 | G3X | 20:30:58 | 58 | 170 | 43.8 | 48.6 | 4.1 | 13.0 | 294 | 20 | OSC |
| 2026-04-30 | 42.8 | G3X | 18:57:18 | 56 | 180 | 44.0 | 49.1 | 4.2 | 20.0 | 969 |  | OSC |
| 2026-04-30 | 42.8 | G3X | 19:27:09 | 71 | 160 | 32.1 | 49.3 | 3.9 | 19.0 | 1369 | 2 | OSC |
| 2026-04-30 | 42.8 | G3X | 19:32:18 | 147 | 150 | 37.8 | 49.8 | 4.3 | 17.9 | 1908 | 4 | OSC |
| 2026-05-08 | 44.1 | G3X | 18:43:12 | 65 | 180 | 40.3 | 48.6 | 4.0 | 13.6 | 284 | 10 | OSC |
| 2026-05-08 | 44.8 | G3X | 20:56:51 | 47 | 220 | 39.2 | 48.8 | 4.6 | 14.6 | 748 |  | OSC |
| 2026-05-08 | 44.8 | G3X | 21:33:20 | 68 | 190 | 21.6 | 48.4 | 3.7 | 12.2 | 873 | 18 | OSC |
| 2026-05-08 | 46.9 | G3X | 23:10:42 | 57 | 180 | 32.7 | 48.9 | 4.3 | 15.5 | 839 |  | OSC |
| 2026-05-18 | 50.3 | G3X | 20:08:17 | 72 | 190 | 35.9 | 49.4 | 4.2 | 17.0 | 752 | 8 | OSC |
| 2026-05-18 | 50.3 | G3X | 20:12:51 | 37 | 190 | 34.1 | 48.7 | 4.0 | 16.3 | 209 | 4 | OSC |
| 2026-05-18 | 51.1 | G3X | 21:18:30 | 63 | 190 | 38.0 | 48.8 | 4.1 | 15.8 | 371 |  | OSC |
| 2026-05-20 | 51.8 | G3X | 18:37:03 | 52 | 160 | 40.8 | 48.3 | 4.6 | 12.6 | -274 |  | OSC |
| 2026-05-20 | 51.8 | G3X | 19:04:22 | 69 | 150 | 41.9 | 48.6 | 3.6 | 12.0 | 676 | 10 | OSC |
| 2026-05-27 | 53.5 | G3X | 14:52:49 | 73 | 180 | 34.7 | 48.6 | 4.2 | 12.0 | 84 | 4 | OSC |
| 2026-05-27 | 56.2 | G3X | 20:20:40 | 273 | 100 | 35.3 | 50.5 | 7.0 | 16.1 | 4882 | 8 | weak |
| 2026-06-02 | 58.4 | G3X | 18:09:19 | 83 | 180 | 39.5 | 49.8 | 4.3 | 24.2 | 1629 | 2 | OSC |
| 2026-06-02 | 59.1 | G3X | 20:40:46 | 59 | 190 | 38.4 | 49.7 | 4.1 | 27.0 | 1715 |  | OSC |
| 2026-06-04 | 60 | G3X | 21:39:19 | 44 | 180 | 43.9 | 48.7 | 4.3 | 16.4 | 392 |  | OSC |
| 2026-06-04 | 60 | G3X | 21:44:30 | 43 | 170 | 36.8 | 48.5 | 4.2 | 14.5 | 187 | 2 | OSC |
| 2026-06-04 | 60 | G3X | 21:49:43 | 43 | 180 | 34.8 | 48.5 | 4.2 | 14.6 | 163 | 2 | OSC |
| 2026-06-08 | 60.4 | G3X | 18:13:37 | 85 | 180 | 39.2 | 48.8 | 4.2 | 14.3 | 965 | 4 | OSC |
| 2026-06-08 | 60.4 | G3X | 18:43:10 | 63 | 180 | 33.2 | 49.0 | 4.8 | 14.9 | 1387 |  | OSC |
| 2026-06-13 | 61.6 | G3X | 19:46:45 | 63 | 200 | 35.8 | 49.5 | 4.4 | 24.5 | 1305 |  | OSC |
| 2026-06-13 | 61.6 | G3X | 20:12:01 | 56 | 190 | 31.6 | 48.2 | 4.2 | 21.7 | 995 | 7 | OSC |
| 2026-06-13 | 61.6 | G3X | 20:31:32 | 56 | 190 | 37.7 | 49.3 | 4.6 | 21.8 | 1190 | 8 | OSC |
| 2026-06-13 | 61.6 | G3X | 20:55:23 | 52 | 200 | 36.8 | 49.3 | 4.2 | 22.0 | 1137 | 7 | OSC |
| 2026-06-17 | 63.5 | G3X | 14:50:05 | 54 | 210 | 38.9 | 48.5 | 4.8 | 14.6 | 109 |  | OSC |
| 2026-06-18 | 66.3 | G3X | 14:18:37 | 52 | 170 | 31.0 | 49.3 | 5.1 | 17.6 | 3500 |  | OSC |
| 2026-07-03 | 70.4 | G3X | 19:37:27 | 56 | 160 | 39.8 | 49.1 | 4.2 | 20.2 | 858 |  | OSC |
| 2026-07-06 | 71.5 | G3X | 15:33:12 | 45 | 180 | 32.5 | 49.2 | 4.4 | 17.2 | 489 |  | OSC |
| 2026-07-06 | 72.2 | G3X | 18:48:37 | 43 | 180 | 37.0 | 49.9 | 3.8 | 24.0 | 1268 |  | OSC |
| 2026-07-08 | 72.5 | G3X | 16:44:57 | 49 | 180 | 43.9 | 49.2 | 4.4 | 16.7 | 248 |  | OSC |
| 2026-07-08 | 72.5 | G3X | 16:49:40 | 50 | 160 | 36.2 | 48.7 | 4.5 | 15.7 | 161 | 7 | OSC |
| 2026-07-08 | 72.5 | G3X | 16:54:50 | 44 | 170 | 32.0 | 48.7 | 3.6 | 15.7 | 84 | 6 | OSC |
| 2026-07-08 | 72.5 | G3X | 16:59:56 | 51 | 175 | 32.5 | 48.8 | 3.8 | 15.8 | 156 | 6 | OSC |
| 2026-07-08 | 72.5 | G3X | 17:05:09 | 46 | 200 | 34.1 | 48.7 | 3.8 | 15.9 | 274 | 7 | OSC |
| 2026-07-08 | 72.5 | G3X | 17:09:53 | 47 | 160 | 34.6 | 48.7 | 3.8 | 15.9 | 167 | 7 | OSC |
| 2026-07-08 | 72.5 | G3X | 17:14:35 | 49 | 170 | 34.9 | 48.8 | 3.7 | 15.9 | 229 | 5 | OSC |
| 2026-07-08 | 72.5 | G3X | 17:19:18 | 56 | 170 | 33.1 | 48.9 | 3.7 | 15.8 | 296 | 6 | OSC |
| 2026-07-08 | 72.5 | G3X | 17:23:50 | 47 | 190 | 32.0 | 48.9 | 4.2 | 16.0 | 300 | 5 | OSC |
| 2026-07-14 | 73.5 | G3X | 21:24:16 | 65 | 190 | 35.4 | 50.2 | 4.0 | 27.6 | 1718 |  | OSC |
| 2026-07-14 | 73.5 | G3X | 21:46:54 | 62 | 200 | 33.0 | 50.0 | 4.4 | 25.8 | 2034 |  | OSC |
| 2026-07-17 | 75.3 | G3X | 11:36:00 | 111 | 170 | 35.2 | 48.9 | 4.1 | 14.6 | 735 | 9 | OSC |
| 2026-07-17 | 80.3 | G3X | 18:19:44 | 74 | 70 | 29.2 | 51.4 | 12.2 | 29.8 | 6022 | 6 | clean |
| 2026-07-18 | 85.4 | G3X | 14:29:27 | 54 | 190 | 33.6 | 49.9 | 4.8 | 26.0 | 2405 |  | OSC |
| 2026-07-22 | 87.7 | G3X | 14:32:40 | 52 | 180 | 36.9 | 49.8 | 4.2 | 19.0 | 1450 |  | OSC |
| 2026-07-22 | 90.9 | G3X | 19:21:52 | 42 | 160 | 36.2 | 49.8 | 5.1 | 25.1 | 2422 |  | OSC |
| 2026-07-23 | 93.8 | G3X | 12:54:27 | 53 | 140 | 31.0 | 49.9 | 6.5 | 18.0 | 4284 |  | OSC |
| 2026-07-23 | 97.8 | G3X | 18:12:17 | 66 | 80 | 28.2 | 51.5 | 8.1 | 29.4 | 6348 |  | clean |
| 2026-08-10 | 102 | G3X | 19:09:42 | 47 | 170 | 44.0 | 49.4 | 4.2 | 19.7 | 675 |  | OSC |
| 2026-08-10 | 102 | G3X | 19:15:27 | 45 | 220 | 37.8 | 49.2 | 4.4 | 17.9 | 540 | 4 | OSC |
| 2026-08-10 | 102 | G3X | 19:20:40 | 55 | 180 | 33.3 | 48.8 | 4.2 | 18.2 | 784 | 3 | OSC |
| 2026-08-11 | 102.5 | G3X | 20:23:16 | 62 | 200 | 34.4 | 49.8 | 4.4 | 24.6 | 1372 |  | OSC |
| 2026-08-11 | 103.2 | G3X | 21:48:49 | 72 | 180 | 32.3 | 49.5 | 4.7 | 24.8 | 1426 | 6 | OSC |
| 2026-08-11 | 103.2 | G3X | 22:01:06 | 54 | 180 | 40.7 | 49.0 | 4.4 | 19.4 | 891 | 11 | OSC |
| 2026-08-11 | 103.2 | G3X | 22:26:26 | 65 | 210 | 38.4 | 49.4 | 4.3 | 21.0 | 873 |  | OSC |
| 2026-08-14 | 104.4 | G3X | 19:12:48 | 52 | 240 | 37.9 | 49.4 | 4.6 | 22.6 | 1190 |  | OSC |
| 2026-08-14 | 105 | G3X | 20:42:45 | 66 | 170 | 34.9 | 49.3 | 4.6 | 21.2 | 1180 | 5 | OSC |
| 2026-08-25 | 105.9 | G3X | 18:32:47 | 57 | 170 | 33.5 | 50.0 | 4.7 | 26.1 | 1706 |  | OSC |
| 2026-08-25 | 105.9 | G3X | 18:54:55 | 50 | 210 | 35.1 | 50.5 | 4.5 | 25.6 | 2139 |  | OSC |
| 2026-08-26 | 107.2 | G3X | 18:42:51 | 54 | 180 | 31.8 | 48.9 | 4.4 | 18.2 | 647 |  | OSC |
| 2026-08-26 | 107.2 | G3X | 18:52:02 | 49 | 190 | 35.9 | 48.9 | 4.0 | 17.0 | 583 | 5 | OSC |
| 2026-08-31 | 107.6 | G3X | 19:19:14 | 51 | 180 | 38.4 | 49.2 | 4.2 | 21.3 | 1204 |  | OSC |
| 2026-08-31 | 107.6 | G3X | 19:36:37 | 70 | 180 | 36.5 | 49.2 | 4.6 | 21.0 | 1253 | 8 | OSC |
| 2026-08-31 | 107.6 | G3X | 20:15:27 | 71 | 160 | 32.6 | 49.6 | 4.4 | 20.4 | 1321 | 11 | OSC |
| 2026-09-02 | 109 | G3X | 17:36:33 | 50 | 170 | 33.3 | 49.2 | 4.1 | 20.0 | 1241 |  | OSC |
| 2026-09-02 | 109.4 | G3X | 19:00:32 | 47 | 220 | 36.3 | 49.4 | 5.1 | 19.6 | 1753 |  | OSC |
| 2026-09-02 | 109.4 | G3X | 19:40:14 | 45 | 140 | 27.1 | 49.1 | 4.9 | 14.8 | 1221 | 12 | OSC |
| 2026-09-02 | 109.4 | G3X | 20:25:43 | 64 | 180 | 26.5 | 49.3 | 5.7 | 12.5 | 1146 | 21 | OSC |
| 2026-09-02 | 111.9 | G3X | 21:37:28 | 55 | 170 | 38.1 | 48.9 | 4.5 | 15.9 | 1499 |  | OSC |
| 2026-09-25 | 112.5 | G3X | 17:31:27 | 35 | 170 | 36.2 | 48.8 | 4.9 | 15.5 | 657 |  | OSC |
| 2026-09-25 | 112.5 | G3X | 17:35:58 | 31 | 150 | 34.8 | 49.1 | 7.5 | 15.6 | 713 | 15 | OSC |
| 2026-09-27 | 113 | G3X | 18:23:46 | 47 | 180 | 35.2 | 48.5 | 4.6 | 14.0 | 72 |  | OSC |
| 2026-09-27 | 115 | G3X | 21:32:05 | 47 | 190 | 31.5 | 49.2 | 4.6 | 21.9 | 1747 |  | OSC |
| 2026-09-30 | 116.7 | G3X | 19:42:31 | 46 | 180 | 37.5 | 48.8 | 5.0 | 16.5 | 329 |  | OSC |
| 2026-10-05 | 117.7 | G3X | 17:27:41 | 54 | 170 | 37.0 | 49.0 | 4.8 | 14.6 | 216 |  | OSC |
| 2026-10-05 | 118.2 | G3X | 20:50:52 | 53 | 160 | 33.5 | 49.3 | 5.2 | 17.3 | 482 |  | OSC |
| 2026-10-14 |  | AXIS | 17:26:12 | 58 | 170 | 43.5 | 50.6 | 4.4 | 15.6 | 77 | 12 | OSC |
| 2026-10-14 |  | AXIS | 17:57:20 | 41 | 185 | 44.1 | 50.6 | 4.4 | 14.6 | -24 | 14 | OSC |
| 2026-10-14 |  | AXIS | 18:27:54 | 56 | 190 | 44.4 | 50.9 | 5.0 | 16.9 | 294 | 7 | OSC |
| 2026-10-16 |  | AXIS | 20:27:20 | 50 | 190 | 43.8 | 51.5 | 4.1 | 23.9 | 1332 | 15 | OSC |
| 2026-10-16 |  | AXIS | 21:01:20 | 45 | 170 | 44.2 | 50.8 | 4.0 | 17.7 | 1026 | 9 | OSC |
| 2026-10-18 |  | AXIS | 20:00:03 | 58 | 200 | 43.3 | 50.5 | 4.4 | 14.2 | 261 | 11 | OSC |
| 2026-10-18 |  | AXIS | 21:02:03 | 58 | 200 | 44.5 | 50.6 | 4.1 | 14.0 | 455 | 9 | OSC |
| 2026-10-18 |  | AXIS | 21:27:34 | 47 | 175 | 41.6 | 50.1 | 5.1 | 9.8 | 534 | 14 | OSC |
| 2026-10-24 |  | AXIS | 15:26:12 | 46 | 170 | 42.5 | 50.0 | 3.8 | 4.6 | -915 | 11 | OSC |
| 2026-10-24 |  | AXIS | 15:50:56 | 51 | 180 | 42.7 | 49.9 | 5.0 | 5.8 | -302 | 13 | OSC |
| 2026-10-24 |  | AXIS | 16:22:11 | 41 | 180 | 44.4 | 49.9 | 4.0 | 6.6 | -677 | 5 | OSC |
| 2026-10-28 |  | AXIS | 19:28:37 | 48 | 210 | 42.9 | 50.1 | 4.7 | 10.1 | -72 | 18 | OSC |
| 2026-10-28 |  | AXIS | 19:33:14 | 32 | 150 | 45.1 | 49.6 | 5.2 | 8.9 | -257 | 14 | OSC |
| 2026-10-28 |  | AXIS | 19:37:36 | 34 | 140 | 44.6 | 49.7 | 8.2 | 8.9 | -252 | 15 | OSC |

Note: the 2026-04-23 14:23 segment (377 s) and 2026-05-27 20:20 segment (273 s) are extended full-power periods, probably Phase 1 climb testing, not takeoffs; they are kept because they show the altitude dependence.
