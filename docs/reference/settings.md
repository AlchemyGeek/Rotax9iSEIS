# Settings and their defaults

Everything you can change, where it lives, its shipped default, and what changing it does. Each entry is the same sentence shown behind the **ⓘ** in the app. Settings marked *workspace* apply to every flight in the active workspace; those marked *app* apply to every workspace.

## Settings → Reference & Models

| Setting | Default | Scope | What it does |
|---|---|---|---|
| **Contributing flights** | all admitted flights | workspace | The flights that define what normal looks like for your engine — every other flight is judged against them. Exclude a flight from its header or an insight; *Rebuild reference* applies the change. |
| **Outlier z-threshold** | 2.0 | workspace | How far from your usual a flight must be before it is called out — lower flags more flights, including more ordinary variation. |
| **n_min** (per trigger) | 10 | workspace | How many of your other flights are needed before this check runs — lower starts checking sooner, against a less settled picture of normal. Shown here; edited on each topic's card. |
| **Recent window (hours)** | 10 h | workspace | How many of your latest flights Trends checks against the reference — a smaller window shows a change sooner but can be swayed by one odd flight. |
| **Min / max flights in window** | 5 / 15 | workspace | The window always holds at least the minimum and never more than the maximum, whatever the hours say. |
| **OM margin fraction** | 0.25 | workspace | Where Trends draws the headroom line: 0.25 means a shift is declared when the recent average has used 75 % of the way to an Operators Manual limit. |
| **Reference per metric** | rolling | workspace | Pinning freezes which flights count as normal for a metric, so new flights are compared with those flights instead of with everything flown so far. Pin from a Trends panel; unpin here or there. |
| **Stratification** | fixed | — | Temperatures and EGT are compared with flights flown in similar outside air temperature, and cruise fuel figures with flights at similar density altitude, so weather is not mistaken for an engine change. The bands are shown for information. |
| **Models** | — | workspace | The takeoff-boost model's fit (R², number of takeoffs, scatter) and a *Refit* button. |

## Settings → Engine

| Setting | Default | Scope | What it does |
|---|---|---|---|
| **Engine profile** | chosen at workspace creation | workspace | Which Operators Manual the limits come from. Cannot be changed afterwards; make a new workspace. |
| **OM limits** | per engine | read-only | The full table; see [Operators Manual limits by engine](om-limits.md). The *Suppression* column says when a limit is checked — only in some flight phases, or only once it has been exceeded for a set time — so expected moments such as takeoff power are not reported as exceedances. |
| **Engine overrides** | none | read-only | *None* means every limit is the Operators Manual value shown; nothing has been changed for this aircraft. |
| **Log channels** | not assigned | workspace | What a general-purpose input carries depends on how your aircraft's EIS is configured, so the app never guesses — an unassigned channel stays viewable under its raw name. Assigning one (for example *CO ppm*) is recorded in the Journal and triggers re-analysis. |

## Topic card → Edit rules…

| Setting | Default | Scope | What it does |
|---|---|---|---|
| **enabled** | on | workspace | Stops this topic reporting on every flight; past Journal entries stay. The card remains, collapsed, with *Enable*. |
| **n_min** | 10 | workspace | As above, per trigger. |
| **r2_min** (trend triggers) | 0.5 | workspace | How clearly the points must line up before a trend is reported — lower reports trends sooner, with more false alarms. |
| **z** (boost-at-takeoff threshold) | 2.0 | workspace | How far from your own boost model a takeoff must sit, in multiples of your usual scatter, before it is flagged. |
| **severity** | per trigger | workspace | The label an insight carries. Display only. |
| **Preview counts** | — | — | Counts flights, not insights: newly flagged flights gain an insight from this topic, cleared ones lose it, and changed ones keep it at a different severity. |

Triggers that follow an Operators Manual limit are shown as such and have no number to edit.

## Settings → App

| Setting | Default | Scope | What it does |
|---|---|---|---|
| **Units** | Imperial | app | °F / psi / inHg / gal, or °C / bar / hPa / L. Changes display only. |
| **Workspace that reopens on launch** | last used | app | |
| **Share a workspace** — Include logs / Anonymise logs | on / off | — | See [Sharing a workspace](../concepts/sharing-a-workspace.md). |
| **Storage** | — | app | Shown when the app runs in your browser. Space used by each workspace; whether the browser has agreed to keep the data (if not, *export a copy to be safe*); **Export all workspaces…**; **Delete all data** on this device. Logs are never stored here. |
| **Data location** | `~/SlingologyEIS` | app | Shown instead of *Storage* when the app runs as a program on your computer. Where workspaces, their results and app settings are kept. Log folders stay where they are. *Change…* moves the data or adopts data already there. |
| **Chart presets** | six shipped | app | The channel sets offered above the Flight view chart. Make your own from the chart's *Save as preset…*; rename, reorder, duplicate or delete here. |

## Journal

| Item | What it means |
|---|---|
| **Live effect** | What this decision is doing to your flights right now — events hidden, insights added or removed, verdicts changed — recounted from your current analyses each time the Journal opens. |
| **Change notices** | A decision whose basis has moved since you made it — for example, a limit filter whose recent flights now breach or drift from its band, or one that no longer changes anything — so you can check it still holds. |

## Flight view header

| Item | What it means |
|---|---|
| **Excluded from reference** | This flight is still analysed, but it no longer shapes what normal looks like for your other flights. |

## Fixed values you will see mentioned

These are part of how the app works and are not settings:

| Value | What |
|---|---|
| 10 min | Minimum airborne time for a log to count as a flight. |
| 5 min | Longest gap inside a log before it is treated as corrupt. |
| 30 s | How long a reading must stay back inside a limit before an event ends. |
| 3 s | Shortest engine-computer alert that counts as more than a blip. |
| 20 flights | How many recent flights a new filter freezes as its reference. |
| 25 h / 50 h | Engine hours before a WARNING / CAUTION filter says *Review due*. |
| OAT bands | cold < 5 °C · mild 5–20 °C · warm 20–30 °C · hot > 30 °C |
| DA bands | low < 2,000 ft · moderate 2,000–5,000 · high 5,000–9,000 · very high > 9,000 |
