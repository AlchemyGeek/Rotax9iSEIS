# Sharing a workspace

<div class="in-brief" markdown>
**In brief.** *Settings → App → Export workspace…* writes a file you can send to another pilot, your mechanic, or someone helping you read your engine. It carries your settings and decisions and — with *Include logs* — the logs themselves, so the recipient opens it and sees exactly what you see. *Anonymise logs* replaces the aircraft identity with a pseudonym and blanks the position and radio data. The recipient uses *Import workspace…* and gets a new workspace of their own.
</div>

## Why export a whole workspace

The export is also how a workspace moves between browsers or computers, and your backup against the browser clearing its storage — the same file does all three. The useful thing to share is rarely one number. It is "look at this engine" — the flights, the way the limits have been tolerated, the trend that worried you. A workspace export carries all of that in one file, so the person at the other end sees your Flight views, your Trends and your Journal rather than a screenshot and a description.

## What the export contains

**Always:** the workspace's settings, its reference and model settings, which flights are excluded and why, pinned references, every filter and rule edit, the Journal, your annotations, and a list of the flights in it. Not carried: the analysis results themselves (the recipient's app recomputes them from the logs), your folder paths, or anything about your computer.

**With *Include logs*** (on by default): the log files, zipped together with the workspace. Without them the export is a small file that describes a workspace but cannot show one; the recipient sees *Link your logs to see this workspace's analysis*. Sharing with the logs is the normal case.

**With *Anonymise logs***: the tail number and avionics system ID are replaced by a pseudonym (one per aircraft), GPS position and the nav/com columns are blanked, and the files are renamed `flight_001.csv`, `flight_002.csv` … Dates, times and engine hours are **not** changed — they are what makes the analysis work. Nor is anything you typed: your notes, filter reasons and the workspace name go as written, and the export dialog lists where your tail number appears in them so you can edit first.

To share only some flights, make a workspace that points at a folder with just those logs, and export that.

<figure class="screenshot" markdown>
![The Share a workspace section under Settings → App](../img/settings-export.png){ .screenshot }
<figcaption>Settings → App: export with or without logs, anonymised or not, with the privacy note.</figcaption>
</figure>

## What the recipient gets

*Import workspace…* (under *Settings → App*, or from the workspace switcher) always creates a **new** workspace, named after yours with *(imported)* added. It first shows a summary — whose it is, which engine, how many flights, how many filters and rule edits — then unpacks the logs into a folder of its own and matches them against your flight list: *38 of 40 flights found · 2 missing · 12 other logs held out*. Then the usual analysis runs.

The recipient sees your workspace as you saw it: your filters, your exclusions, your pins, your Journal. A flight whose log did not arrive is listed under Skipped as *In the sender's workspace — log not found*, and your decisions about it wait until the log appears. A log that was in the zip but not in your workspace — perhaps you had skipped it — is *held out*, listed with *Include* if they want it.

An import from a newer version of the app than the recipient is running is refused with a message; from an older one it proceeds with a notice.

## Privacy

An engine log carries more than engine data: your tail number, your avionics' serial number, the date and time of every flight, and your GPS track. Anonymising removes the identity and the track; it leaves the dates and times, because trends over engine hours need them. If that is more than you want to share, share fewer flights. The app shows this notice every time you export.

---

*Walkthrough: [Export and import](../walkthroughs/export-import.md).*
