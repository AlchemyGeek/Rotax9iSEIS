# Sharing a study

*Ten minutes, two people. How to send another owner of the same engine the rule and questions that found something on your aircraft, and how they run it on theirs — without either of you sending a single flight log. Also how to receive one. To follow along alone, make a second workspace pointing at a different folder of logs and play both parts.*

## What a study carries, and what it doesn't

A `.eisstudy` holds your slice rules, your questions and their settings, your references and notes, and the measurements and finding you saw — plus the per-slice table and a chart, for anyone who only wants to read it. It names your flights by **fingerprint**: a code derived from each log that means nothing to anyone who does not hold the same file. Your logs do not travel, and the recipient's never leave their machine.

## Sending

### 1. Check what the recipient will see

Open the study. Everything on the page — findings, charts, tables, notes — is what they will see, read-only. If a note names a person or a place you'd rather not send, edit it now. **Save**.

### 2. Export

**Export .eisstudy**. The file is small — tens of kilobytes. Send it however you like, with a line saying what you found and what you'd like them to try.

<!-- screenshot: wt-share-01-export.png — the study page's actions with Export .eisstudy -->

## Receiving

### 3. Import

On your **Research** page, **Import a study…** and pick the file. The app matches the study's flights against your workspace.

### 4. Read it — as theirs

If none of the sender's flights are in your workspace (the usual case between two aircraft), the study opens **read-only**, with a label across the top that cannot be missed: **Sender's results — none of these flights are in this workspace.** Every control is visible but greyed, so the page reads exactly as the sender's did; nothing on it is about your engine yet.

<!-- screenshot: wt-share-02-readonly.png — an imported study with the read-only label and the one enabled action -->

### 5. Run this on my flights

Press **Run this on my flights**. The app creates a new study in your workspace with the sender's rules, questions, references and settings, over your own flights, and runs it. It opens as a normal, editable study of yours.

Now the finding sentence is about your aircraft:

> RPM cycles every 4.1 s (IQR 3.9–4.3), swing 60 rpm (40–80), in 12 of 71 slices.

Put it beside theirs — *every 3.8 s, swing 180 rpm, in 93 of 98*. Same rule, same question, two engines; the count and the swing tell you at once whether you share the behaviour or not.

<!-- screenshot: wt-share-03-mine.png — the new study over the recipient's flights, its own finding -->

### 6. Keep both

The read-only study stays in your Research list as the sender's record; your run is a second study. Rename yours so the two are clear — *Takeoff rpm — N117ZS (sender)* and *Takeoff rpm — mine*. **Save**.

## If some flights do match

If the sender also gave you their logs (a shared workspace, say), the study opens as an ordinary study over the flights you both hold; flights you lack are listed at the top and simply contribute no slices.

## Sending it onward

Your own study exports the same way. Two aircraft showing the same shape is a stronger message to a manufacturer than one; the evidence packages from both, side by side, are the attachment.

## Where to go next

- [Studies: saving and sharing](../concepts/research-studies.md) — what a study is.
- [From a finding to action](../concepts/research-action.md) — writing to a manufacturer with two aircraft's evidence.
- [Export and import](export-import.md) — sharing a whole workspace, logs included, when that is what's needed.
