# The study file

What a `.eisstudy` contains, what it does not, and what happens when one is imported. For anyone about to send a study, or wondering what they have been sent.

## The file

A `.eisstudy` is an ordinary zip archive. Rename it `.zip` and any file manager opens it:

| Inside | What it is | Who it's for |
|---|---|---|
| `study.json` | The study itself: selection, slice rules, hand slices, questions and their settings, references, notes, the results as the sender saw them, and the cache of per-slice measurements | The app |
| `evidence/NN-question.csv` | One per question: the per-slice table — every slice's measurements and conditions — as a spreadsheet | A reader without the app; a mechanic; a manufacturer |
| `charts/NN-question.svg` | One per question: the result's chart as an image | The same readers |

The file is small — tens of kilobytes for a hundred slices.

## What it does not contain

- **No flight logs**, and no second-by-second samples. The aligned view cannot be drawn from a study file alone; it needs the logs.
- **No file names or paths.** Flights are named by **fingerprint**, a code derived from each log's contents. Two people holding the same log compute the same fingerprint; nobody can recover the log from it.
- **Nothing about the sender's workspace** beyond the study — no decisions, filters, Journal entries or other studies. For those, share a workspace ([Export and import](../walkthroughs/export-import.md)).

The per-slice tables and the notes are the sender's words and numbers: dates, times, engine hours, altitudes and temperatures of each slice, and anything typed into the notes. Read them before sending if that matters.

## What the study stores, in outline

```
name, created, updated
selection      all flights | chosen flights (by fingerprint) | a split (source, DA band, OAT band, date)
slice rules    conditions, minimum duration, merge gap, phase, pad — the preset they came from, if any
hand slices    flight (fingerprint), start and end seconds, label, offset (reserved for the splicer)
references     label, channel, kind, value, source
questions      which question, which channels, settings, and the result as last run
notes
cache          per-slice measurements, keyed by flight fingerprint and engine version
```

Results and the cache are *derived*: the app may drop and recompute them. Everything else is the study.

## Importing

**Import a study…** on the Research page always creates a **new** study; it never overwrites one. The app then matches the study's fingerprints against the workspace:

| Match | What opens |
|---|---|
| All or some flights present | A normal study over the flights present; missing flights are listed and contribute no slices |
| No flights present | A **read-only** study showing the sender's results under the label *Sender's results — none of these flights are in this workspace*, with one action: **Run this on my flights**, which creates a new study of yours from the sender's definitions over your own selection |

A read-only study re-exports unchanged, so it can be passed on exactly as received.

## Cache and versions

The cached measurements are trusted only while the flight's fingerprint and the engine version that produced them match the workspace; otherwise they are recomputed when the study is next run. A study made with one version of the app opens in a later one; its saved results carry the engine version that produced them.

## Studies inside a workspace export

Studies live in the workspace and are carried by a workspace export along with your decisions, so a shared workspace brings its studies with it; the recipient re-runs them on the copied logs.

Spec 06 §10 defines the study, its file and import.
