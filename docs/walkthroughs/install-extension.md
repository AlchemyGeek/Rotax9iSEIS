# Install the extension

*Five minutes. How to add SlingologyEIS to Claude Desktop on a Mac, so Claude can investigate your engine logs on your computer. You need the Claude Desktop app, signed in with your own Claude account.*

## 1. Download the file for your Mac

Open the [latest release](https://github.com/AlchemyGeek/Rotax9iSEIS/releases/latest) and download one file:

- **Apple silicon** (M1, M2, M3, M4…): `slingology-eis-…-macos-arm64.mcpb`
- **Intel**: `slingology-eis-…-macos-x86_64.mcpb`

Not sure which you have? **Apple menu → About This Mac**: a line **Chip** naming *Apple M…* is Apple silicon; a line **Processor** naming *Intel* is Intel.

The file is about 100 MB. It holds the EIS engine, its own copy of Python and the EIS pages; you don't need to install anything else.

## 2. Install it in Claude Desktop

With Claude Desktop open, do any one of these:

- double-click the downloaded `.mcpb` file;
- drag it onto the Claude Desktop window;
- in Claude Desktop, **Settings → Extensions → Advanced settings → Install Extension…** and pick the file.

Claude Desktop opens its install view: SlingologyEIS, what it does and the tools it offers. Install it from there.

<!-- screenshot: install-extension--02-dialog.png — Claude Desktop's install view for SlingologyEIS (taken by the owner on the first install; Claude Desktop can't be shot by the docs script) -->

**The file isn't signed yet.** Claude Desktop warns you before installing an extension that isn't signed. If you downloaded it from the SlingologyEIS releases page above, install it anyway. Signing comes in a later release.

## 3. Settings — all optional

Claude Desktop shows the extension's settings during the install, and later under **Settings → Extensions → SlingologyEIS**. Each can be left empty:

| Setting | Leave empty to… | Set it when… |
|---|---|---|
| **EIS data folder** | use the folder the EIS pages use (Settings → App → Data location) | you keep EIS's data somewhere specific, e.g. on another disk |
| **Aircraft** | use your only aircraft, or the one you opened last | you have more than one aircraft in EIS |
| **Log folders** | link folders later, from the EIS pages | you want your log folders linked to the aircraft's workspace from the start |

Log folders added here are added to the workspace Claude uses; removing one is done in the EIS pages.

## 4. First start

Open a new chat in Claude Desktop. The first time, EIS takes a few seconds longer to start (about ten) while it sets itself up; after that it starts at once.

While Claude Desktop is open, the **EIS pages** are at **http://127.0.0.1:8420/** in your browser. Open them:

- With no workspace yet, they show the first-workspace steps — the same as on the website ([Open the app and your first workspace](first-workspace.md)). Creating the workspace also creates the aircraft.
- If you already run EIS on your computer (`slingology-eis serve`), the pages are served by that one; the extension leaves it alone and Claude's tools still work.

## 5. Check that Claude sees EIS

In the chat, ask:

> What does EIS have for my aircraft?

Claude calls EIS's `guide` and tells you the aircraft, the workspace it uses, how many flights, and anything waiting in the inbox. In the chat's **+** menu you'll find the four EIS prompts — **Investigate**, **Look at this inbox item**, **Before / after**, **Review new flights** ([the prompts](../reference/investigation-prompts.md)).

Next: [Set up your aircraft and documents](aircraft-documents.md), then [Your first investigation](first-investigation.md).

## If something is wrong

- **Nothing happens when you open the file.** Use **Settings → Extensions → Advanced settings → Install Extension…** instead, and make sure Claude Desktop is up to date.
- **Claude says *no workspace yet*.** Open http://127.0.0.1:8420/ and create a workspace (step 4), then ask again.
- **The pages don't open.** Something else is using port 8420, or Claude Desktop isn't running. Check **Settings → Extensions**: SlingologyEIS should be enabled.
- **Logs to send with a problem report**: Claude Desktop's own, in `~/Library/Logs/Claude/`, and EIS's, `cache/mcp.log` inside your EIS data folder.

To turn the extension off or remove it, open it under **Settings → Extensions**. Your workspaces and logs stay where they are.
