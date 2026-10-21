# Open the app and your first workspace

*About fifteen minutes, most of it the app working. You need a computer with a current browser — the app is tested on macOS Chrome and Safari — and a folder of engine logs from your Garmin G3X, Garmin Pilot or AXIS. Nothing to install.*

## 1. Open the app

Open **[SlingologyEIS](https://alchemygeek.github.io/Rotax9iSEIS/app/)** in your browser. The first time, the page sets up the analysis engine — about 30 MB, downloaded once and kept by your browser — and shows its progress. Later visits take a few seconds, and work without a network: the app starts from the copy your browser kept. When a new version is published, the next visit with a network picks it up and says *Updated to version …* once.

Everything the app does from here on happens inside your browser, on your computer. Your logs are read from your own folders and never uploaded; the results are kept by your browser, on this device. There is no account and no server holding your data.

!!! note "Prefer to run it yourself?"
    The same app can run as a small program on your own computer instead, with the workspace kept in an ordinary folder. See [Running the app on your own computer](#running-the-app-on-your-own-computer) at the end of this page. Everything else in this guide is the same either way.

## 2. Create a workspace

The app asks for a workspace **name** and the **engine model**, with an optional tail number. Name it after the aircraft. Choose the engine carefully — it decides which Operators Manual limits apply and cannot be changed later (you would make a new workspace).

<figure class="screenshot" markdown>
![An empty workspace, inviting you to add your logs](../img/workspace-empty.png){ .screenshot }
<figcaption>Your new workspace, before any logs.</figcaption>
</figure>

## 3. Point it at your logs

!!! tip "No logs yet?"
    Skip this step and the next: [download the sample workspace](https://github.com/AlchemyGeek/Rotax9iSEIS/releases/download/sample-workspace/SlingologyEIS-sample-N117ZS.zip) (10 MB) and use **Settings → App → Import workspace…** instead. It is a season of flights from the aircraft the app was developed on, decisions included. Pick up again at step 5 — the sample has four ground runs in *Skipped*, and the [export and import](export-import.md) walkthrough explains what an import does.

Click **Choose folder…** and pick the folder where you keep your logs — subfolders are included. Or drop files onto the page. The app only *reads* this folder; it never copies, moves or renames anything in it. You can add more folders later, and if you move logs around, **Sync** finds them again.

How the browser remembers the folder differs:

- **Chrome** keeps the folder from one visit to the next. Now and then it asks you to confirm — the folder row shows **Allow access**; one click and you are back.
- **Safari** does not keep folder access between visits. Your flights and analyses are all still there; the folder row says **Not connected — reconnect**, and you pick the folder again only when you want to sync new logs or open a flight's charts. The app says this once, on the row, the first time.

The app lists everything it found with *Needs analysis* beside each log, and an **Analyze N** button appears.

## 4. Analyze

Click **Analyze**. The app reads each log, decides whether it is a flight, works out the phases of flight, checks the Operators Manual limits and builds your reference. A season of logs takes a minute or two; the page shows progress per log. Leave the tab open until it finishes — the browser warns you if you try to close it mid-way.

When it finishes, a notice sums up what happened — *58 new flights analyzed · 59 skipped — not a flight* — and the list fills in.

<figure class="screenshot" markdown>
![The Flights page after the first analysis](../img/flights-overview.png){ .screenshot }
<figcaption>Every flight with its date, duration, engine hours, insights and source file.</figcaption>
</figure>

!!! warning "This workspace lives in your browser"
    Clearing the site's data would remove it. Before you go further, see [step 7, Keep a copy](#7-keep-a-copy) — an export takes a few seconds.

## 5. Look at what was skipped

Click **Skipped**. Logs that did not become flights are listed with the reason: a ground run, a flight under ten minutes, a log with a gap in it. This is normal — every engine start writes a log, and most of a year's logs are not flights. If one looks wrong, open it to check and click **Include**.

<figure class="screenshot" markdown>
![The Skipped list](../img/flights-skipped.png){ .screenshot }
<figcaption>Skipped logs, each with its reason, each includable.</figcaption>
</figure>

## 6. What to expect from the first flights

Your reference needs about ten flights before it can say what is *usual* for your engine. Until then, cards show their numbers with *still building* instead of a comparison, and the Trends page says *building reference*. The Operators Manual checks work from the first flight.

## 7. Keep a copy

Your workspace lives in your browser's storage for this site. That survives closing the tab, restarting the browser and app updates — but it is gone if you clear the site's data, and a browser short of disk space — or Safari, after a long time without a visit — may clear it on its own. *Settings → App → Storage* shows how much space the app uses and whether the browser has agreed to keep it. **Export workspace…** on the same page writes a single file that restores everything; make one once your first analysis is done, and again after you have made decisions you would not want to redo. The [export and import](export-import.md) walkthrough has the details.

**Next:** [Reading your first flight](first-flight.md). To understand what just happened, [Logs, flights and workspaces](../concepts/logs-flights-workspaces.md).

---

## Running the app on your own computer

The app can also run as a small program on your Mac, Windows or Linux computer, with the workspace kept in an ordinary folder (`~/SlingologyEIS`) rather than in the browser. Pilots choose this when they want the data in a folder they can back up like any other, when several browsers on one machine should share one workspace, or when they add log folders by typing a path. The screens, the analysis and the results are identical.

You need Python 3.10 or later. Download the latest `slingology_eis…whl` file from the project's [releases page](https://github.com/AlchemyGeek/Rotax9iSEIS/releases), then in a terminal:

```bash
pip install slingology_eis-<version>-py3-none-any.whl
slingology-eis serve
```

The last line prints an address — `http://127.0.0.1:8420/` — open it in your browser. Leave the terminal window open while you use the app; `Ctrl-C` there stops it. Nothing listens on your network; the app is reachable only from this computer.

The differences you will notice: log folders are added by typing their path (or dropping files) and stay connected without any browser permissions; *Settings → App* shows **Data location** instead of *Storage*; and the workspace is in that folder, so the browser's site data does not matter. A workspace export from one way of running the app imports into the other.
