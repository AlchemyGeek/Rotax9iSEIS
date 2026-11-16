# Investigations: asking Claude about your engine

<div class="in-brief" markdown>
**In brief.** With the EIS extension installed in Claude Desktop, you ask Claude about your engine the way you would ask a knowledgeable friend — *"the climb after my touch-and-go at KBLI on Oct 24 felt like a surge; look into it"* — and Claude investigates: it cuts the slices, runs the questions, writes code against your logs where no question fits, reads the manuals you've given it, and writes what it found into EIS as a **notebook** study you can read, re-run and share. Your logs stay on your computer. Claude is where you think; EIS is the instrument and the record.
</div>

## What an investigation is

The oscillation case — 180 rpm of cycling on nearly every takeoff, inside every limit, unchanged for 145 hours — was found by a loop: cut every full-power segment, notice manifold pressure moving in step with rpm, read the engine manual's boost schedule, form a hypothesis about the governor and the boost control arguing, test it against altitude, rule out two other explanations, and write it up so the propeller manufacturer recognised it from one email. The measurements took minutes; the loop took judgement. Claude did the loop, with the owner steering.

An investigation is that loop, done by your Claude with EIS as its instrument. You give it the question and the context; it does the looking, measuring, reading and writing; you steer and decide.

--8<-- "diagrams/research-investigation-loop.svg"

## What you need

- **The Claude Desktop app** on a Mac, with your own Claude account. EIS runs no AI itself and holds no key: the conversation is yours, on your account.
- **The EIS extension** for Claude Desktop — one file, one install ([Install the extension](../walkthroughs/install-extension.md)). It carries the EIS engine, runs the EIS pages on your computer at `http://127.0.0.1:8420/` while Claude Desktop is open, and gives Claude its connection to them.
- **Your logs** in a folder EIS can read, as on the website.
- **Context worth giving it**, in **Settings → Aircraft** ([Set up your aircraft and documents](../walkthroughs/aircraft-documents.md)): the aircraft's configuration — propeller, controller, firmware — and **notes** on what was changed and when, which Claude reads before every investigation; and **documents folders** holding your copies of the Operators Manual, service bulletins and the propeller and controller manuals, which Claude reads in place and cites by page. EIS never ships the manuals and never copies them.

## How it goes

1. In Claude Desktop, open a chat and ask in words — or pick the **Investigate** prompt from the chat's **+** menu and type the question. Name the flight, the feeling, the question.
2. Claude works. You see its steps in the chat — *finding the 24 Oct flight … a log view of the climb … cutting every full-power segment across 60 flights … rpm and manifold pressure move together … the engine manual's boost schedule, with its page …* — and the notebook forming on the EIS Research page.
3. Steer. *"Compare with every other takeoff." "Does it depend on altitude?" "What does the controller manual say about its governing band?"*
4. Read the notebook in EIS: the question and summary at the top, then the narrative, each measurement with its output, figures, tables, and **log views** — the Flight view's chart for the window that matters, with *Open flight* to see the whole flight there. The code is folded away under *show code*. Ask Claude to put the finding in the Journal; export it; share it ([Your first investigation](../walkthroughs/first-investigation.md)).

--8<-- "diagrams/research-notebook.svg"

![A notebook Claude wrote, on the Research page: header and summary, a log view of the full-power minute](../img/investigations-notebook.png){ .screenshot }

A notebook is an ordinary Jupyter notebook. It opens unchanged in JupyterLab, where you can run it yourself against your workspace ([Run a notebook in JupyterLab](../walkthroughs/notebook-jupyterlab.md)), and *Re-run* on the Research page runs it again on your current flights, holding any output that changed for you to accept or discard. On the website, notebooks open and read the same way; running them needs EIS on your computer.

## The inbox

You don't have to notice something to start. When the Research page opens after new flights, EIS runs its own cheap scan — no AI — over the preset slices of the recent flights and keeps only patterns that hold across many of them: a repeating cycle in governed rpm, a measurement that has moved against your reference, a group of slices that stands apart. Those land in the **inbox** at the top of Research, each with what fired, the evidence table (every slice, each opening its flight at that moment) and its status.

![The inbox on Research home: a recurring rpm cycle at full power, with what fired and the sensitivity](../img/investigations-inbox.png){ .screenshot }

For each candidate you can:

- **Ask Claude** — the **Look at this inbox item** prompt in Claude Desktop takes the candidate's id; or ask in your own words. Claude's notebook links back to it, and *Open the investigation* appears on the candidate.
- **Run the question by hand** — a hand study is set up with the candidate's slices, the recent flights against the rest, and the question that matches what fired.
- **Mark it** *Nothing here*, *Watch* or *Acted*, with a note. *Nothing here* is a legitimate result; the same candidate stays out until the recent window has moved on.

How much it raises is **Settings → Research → Inbox sensitivity**: *quiet* (a pattern in 8 of the last 10 slices), *normal* (6 of 10, the default) or *curious* (4 of 10). The inbox works on the website too; there, asking Claude needs the extension.

The inbox never puts anything on a flight's cards, and a single odd flight is not an inbox item: that is what the Flight view is for. EIS never says what a candidate means — that is the investigation's.

## What stays true

- **No verdicts.** A notebook says what the data did, how big, how often, compared with what; it never says *fault* or *abnormal* without the reference beside it. The judgement is yours, with the Operators Manual and the people who built the parts.
- **Traceable.** Every claim in a notebook comes from a tool result, a code cell's output, or a cited document — or it is labelled a hypothesis. The code is there to read.
- **Private.** Logs never leave your computer. What travels is what Claude asked the instrument for, inside your own conversation.
- **Fenced on a Mac — and only there.** On a Mac, macOS itself fences in the code Claude runs on your computer: it can't reach the internet, start other programs, or change any file outside its own study folder. That fence exists only on a Mac, and the macOS tool it uses is one Apple has deprecated, though it still works today; on Windows and Linux only EIS's own, weaker check applies. On every computer the code can *read* any file you can, and what it reads can end up in your conversation with Claude.
- **The website is unchanged.** Without the extension you have the whole instrument by hand, the inbox and every notebook to read; investigations are the reason to install.

## What to do with this

If you fly behind an engine and something has ever felt odd, [install the extension](../walkthroughs/install-extension.md) and ask. If you'd rather see the instrument first, the walkthrough [Reproducing a takeoff investigation](../walkthroughs/research-takeoff.md) shows the same case worked by hand.

## How it works

The extension bundles the EIS engine, a Python of its own, the EIS pages and an **MCP server** — the standard way Claude Desktop talks to local tools — in one process that Claude Desktop starts and stops. The engine's web pages see the same workspace, so a notebook cell written by Claude appears in your browser as it is written. Claude calls tools: find flights, read channels, cut slices, run a question, run Python against the workspace, read a document from your folders, append a notebook cell ([the tools](../reference/investigation-tools.md), [the prompts](../reference/investigation-prompts.md), [the `eis` library](../reference/eis-library.md), [the notebook format](../reference/notebook-format.md)). The AI never opens a log file; the engine answers tool calls. The design is [Spec 16 — Investigations](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/16-investigations.md); the instrument it drives is [Spec 06 — Research](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/06-research.md).
