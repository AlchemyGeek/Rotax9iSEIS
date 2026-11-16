# The Claude Desktop extension — developer note

How the extension bundle (Spec 16 §7) is built, what it runs and how to work
on it. The user's side is the walkthrough
[Install the extension](walkthroughs/install-extension.md).

## What the bundle is

An MCP Bundle (`.mcpb`, a zip with `manifest.json` at its root), one per macOS
architecture: `slingology-eis-<version>-macos-arm64.mcpb` and `…-macos-x86_64.mcpb`.

| Part | What |
|---|---|
| `manifest.json` | `manifest_version` 0.3; `server.type` `binary` — the command is the bundled Python, so Claude Desktop needs no runtime of its own |
| `python/` | A standalone CPython 3.12 ([python-build-standalone](https://github.com/astral-sh/python-build-standalone), release and checksum pinned in `scripts/build_extension.py`) with the engine wheel and its `investigations` extra installed (numpy, pandas, scipy, matplotlib, pypdf). The wheel carries the built UI. |
| `icon.png` | The 512 px app icon |

About 100 MB packed, 280 MB unpacked. No bytecode ships: the first start
writes it into the extension's folder (about 9 s), later starts take a fraction of a second.

## What Claude Desktop runs

```
${__dirname}/python/bin/python3 -I -m slingology_eis.investigations.extension \
    --data-root ${user_config.data_root} --aircraft ${user_config.aircraft} \
    --log-folders ${user_config.log_folders}
```

`slingology_eis/investigations/extension.py` turns that into
`slingology-eis mcp serve --serve --port 8420 --log-file [--aircraft …] [--log-folder …]`:

- **One process**: the MCP server on stdio, and the EIS pages on
  `http://127.0.0.1:8420/` on a thread. Desktop starts it and stops it (closing
  stdin ends it). If the port is taken — `slingology-eis serve` is already
  running — the pages aren't served from this process and the tools carry on.
- **User configuration** (all optional): the data folder (empty → the one the
  pages use, Spec 02 §5.8.1), the aircraft (empty → the only one, else the most
  recently opened, D10), log folders (linked to the workspace the tools open
  once it exists; added, never removed). An unset setting arrives empty or as
  the literal placeholder; both mean *not set*.
- **Logs**: Claude Desktop's own MCP logs (`~/Library/Logs/Claude/`, one file
  per server, named after it) and `cache/mcp.log`
  under the data root (started afresh past 2 MB).

## Building

```bash
cd web && npm ci && npm run build && npm run build:browser && cd ..   # UI → web/dist, wheel in web/dist/engine/
python scripts/build_extension.py --wheel web/dist/engine/slingology_eis-*.whl --out dist-ext
```

It must run on the architecture it targets (pip picks the running Python's
wheels for numpy, scipy…). It downloads the standalone Python once into
`~/.cache/slingology-eis` (`--cache` to change), installs the wheel, prunes what
isn't needed at run time (the test suite, IDLE, Tk), replaces symlinks with
copies, checks the bundled engine imports with its UI, then validates and packs
with `npx @anthropic-ai/mcpb` (pinned). CI does the same on `macos-15` (arm64)
and `macos-15-intel` (x86_64) after the main job, keeps the bundles as
artifacts and attaches them to the release on a `v*` tag.

## Trying a build without installing it

```bash
mkdir /tmp/eis-ext && cd /tmp/eis-ext && unzip -q …/slingology-eis-*-macos-arm64.mcpb
python/bin/python3 -I -m slingology_eis.investigations.extension \
    --data-root /path/to/a/copy --aircraft "" --port 8432 --log-folders
```

then type MCP requests on stdin (`{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}`),
or open `http://127.0.0.1:8432/`. Always point it at a copy of a data root.
`tests/unit/test_extension.py` covers the entry, the folder linking, the log
file, the busy port and the manifest.

## Signing

Not yet signed. `mcpb sign` signs a bundle with a PEM certificate and key, and
`mcpb info` shows a bundle's signature status. Claude Desktop warns before it
installs an unsigned bundle; the walkthrough tells the user what to expect.
Signing with a CA-issued certificate is a later step.
