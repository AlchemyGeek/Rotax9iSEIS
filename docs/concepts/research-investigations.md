# Investigations: asking Claude about your engine

<div class="in-brief" markdown>
**In brief.** With the EIS extension installed in Claude Desktop, you ask Claude about your engine the way you would ask a knowledgeable friend — *"the climb after my touch-and-go at KBLI on Oct 24 felt like a surge; look into it"* — and Claude investigates: it cuts the slices, runs the questions, writes code against your logs where no question fits, reads the manuals you've given it, and writes what it found into EIS as a **notebook** study you can read, re-run and share. Your logs stay on your computer. Claude is where you think; EIS is the instrument and the record.
</div>

## What an investigation is

The oscillation case — 180 rpm of cycling on nearly every takeoff, inside every limit, unchanged for 145 hours — was found by a loop: cut every full-power segment, notice manifold pressure moving in step with rpm, read the engine manual's boost schedule, form a hypothesis about the governor and the boost control arguing, test it against altitude, rule out two other explanations, and write it up so the propeller manufacturer recognised it from one email. The measurements took minutes; the loop took judgement. Claude did the loop, with the owner steering.

An investigation is that loop, done by your Claude with EIS as its instrument. You give it the question and the context; it does the looking, measuring, reading and writing; you steer and decide.

<!-- diagram: research-investigation-loop.svg — question → tools on the EIS instrument → code against the logs → manuals and context → notebook in EIS; the pilot steering from Claude -->

## What you need

- **The Claude Desktop app** with your own Claude account. The app runs no AI itself and holds no key: the conversation is yours, on your account.
- **The EIS extension** for Claude Desktop — one install. It carries the EIS engine, runs the EIS pages on your computer, and gives Claude its connection to them.
- **Your logs** in a folder the extension can read, as on the website.
- **Context worth giving it**: the engine's Operators Manual, service bulletins, the propeller and controller manuals, your aircraft's configuration. A Claude Project for the aircraft holds these once, so every investigation starts informed. The app never ships the manuals; they are your copies.

## How it goes

1. In Claude, open a chat with the EIS connection and ask in words. Name the flight, the feeling, the question.
2. Claude works. You see its steps in Claude — *looking at the 24 Oct flight … cutting every full-power segment across 60 flights … rpm and manifold pressure correlate at 0.93 … checking the engine deck above 5,500 rpm …* — and the study forming on the EIS Research page.
3. Steer. *"Compare with every other takeoff." "Does it depend on altitude?" "What does the controller manual say about its governing band?"*
4. Read the notebook in EIS: narrative, code cells and their outputs, figures, tables, with every number traceable. Save it, note it in the Journal, build the evidence package, share it.

<!-- screenshot: research-investigation-notebook.png — a Claude-authored study rendered on the Research page: narrative, a code cell with its output, a figure, the per-slice table -->

## The inbox

You don't have to notice something to start. After each import the app runs its own cheap scan — no AI — on the preset slices and keeps only patterns that hold across many recent flights: a repeating cycle in governed rpm, a measurement that has shifted against your fleet reference, a group of slices that stand apart. Those land in the **inbox** on the Research page with their evidence table. Ask Claude to look into one, or set a schedule — *"every Sunday, review anything new in my EIS inbox"* — and Claude's own scheduled tasks will do it. "Nothing here" is a legitimate result and is recorded so the same candidate isn't investigated twice.

The inbox never puts anything on a flight's cards, and a single odd flight is not an inbox item: that is what the Flight view is for.

## What stays true

- **No verdicts.** A notebook says what the data did, how big, how often, compared with what; it never says *fault* or *abnormal* without the reference beside it. The judgement is yours, with the Operators Manual and the people who built the parts.
- **Traceable.** Every claim in a notebook comes from a tool result, a code cell's output, or a cited document — or it is labelled a hypothesis. The code is there to read.
- **Private.** Logs never leave your computer. What travels is what Claude asked the instrument for, inside your own conversation.
- **Fenced on a Mac — and only there.** On a Mac, macOS itself fences in the code Claude runs on your computer: it can't reach the internet, start other programs, or change any file outside its own study folder. That fence exists only on a Mac, and the macOS tool it uses is one Apple has deprecated, though it still works today; on Windows and Linux only EIS's own, weaker check applies. On every computer the code can *read* any file you can, and what it reads can end up in your conversation with Claude.
- **The website is unchanged.** Without the extension you have the whole instrument by hand; investigations are the reason to install.

## What to do with this

If you fly behind an engine and something has ever felt odd, install the extension and ask. If you'd rather see the instrument first, the walkthrough [Reproducing a takeoff investigation](../walkthroughs/research-takeoff.md) shows the same case worked by hand.

## How it works

The extension bundles the EIS engine with an **MCP server** — the standard way Claude Desktop talks to local tools. Claude Desktop starts it when you open a chat; it talks to the engine on your computer, and the engine's web pages see the same workspace, so a notebook cell written by Claude appears in your browser as it is written. Claude calls tools: list flights, read channels, cut slices, run a question, run Python against the workspace, read a document you placed there, append a notebook cell. The AI never opens a log file; the engine answers tool calls. The design is [Spec 16 — Investigations](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/16-investigations.md); the instrument it drives is [Spec 06 — Research](https://github.com/AlchemyGeek/Rotax9iSEIS/blob/main/docs/specs/06-research.md).
