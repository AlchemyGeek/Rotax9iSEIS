# Sharing a notebook

*Ten minutes, two people. How to send another owner of the same engine the notebook that found something on your aircraft, and how they run it on theirs — without either of you sending a single flight log. Also how to send it to someone with no EIS at all. To follow along alone, make a second workspace pointing at a different folder of logs and play both parts.*

## What a notebook carries, and what it doesn't

The exported notebook holds the question, Claude's narrative, the code and every output — numbers, tables, figures, the pictures of its log views — and any files Claude wrote. It names your flights by **fingerprint**: a code derived from each log that means nothing to anyone who does not hold the same file. Your logs do not travel, and the recipient's never have to.

## Sending

### 1. Read it as they will

Open the notebook on the Research page and press **Export as a page (.html)**. Open the page in your browser: that is everything the recipient will read. If a note or a cell names a person or a place you'd rather not send, ask Claude to change it.

### 2. Export

- For another EIS owner: **Export notebook (.zip)**.
- For a mechanic, a manufacturer or a forum: the **.html** page from step 1 — it opens in any browser.

Send it however you like, with a line saying what you found and what you'd like them to look at.

## Receiving

### 3. Import

On your **Research** page, **Import a notebook…** and pick the `.zip` (or a bare `.ipynb`). EIS matches the notebook's flights against your workspace and opens it.

### 4. Read it — as theirs

If none of the sender's flights are in your workspace (the usual case between two aircraft), each log view shows the sender's saved picture and every output is the sender's; the line under the title says the outputs are read-only and not about this workspace.

### 5. Run this on my flights

With EIS on your computer, press **Run this on my flights**. EIS copies the notebook as a new one — *… — my flights* — and runs every code cell against your own flights. Now the measurements are about your aircraft: put its count and swing beside the sender's, and you see at once whether you share the behaviour.

A cell that named one of the sender's flights has no flight to load here; ask Claude to point it at the matching flight of yours ("the first takeoff on my last flight").

### 6. Keep both

The imported notebook stays in your list as the sender's record; your run is a second notebook.

## If some flights do match

If the sender also gave you their logs (a shared workspace, say), cells whose flights you hold are live, and the rest show the sender's outputs.

## Where to go next

- [Notebooks you keep and share](../concepts/research-studies.md) — what a notebook is.
- [From a finding to action](../concepts/research-action.md) — writing to a manufacturer with two aircraft's evidence.
