"""
The Claude Desktop extension's entry (Spec 16 §7): what the bundle's
manifest runs, with the bundled Python —

    python3 -I -m slingology_eis.investigations.extension \
        --data-root ${user_config.data_root} --aircraft ${user_config.aircraft} \
        --log-folders ${user_config.log_folders}

and it becomes `slingology-eis mcp --serve --log-file …`: one process, the
MCP server on stdio and the EIS pages on 127.0.0.1:8420, until Claude
Desktop stops it. The user configuration arrives as Desktop substitutes it:
a setting left empty is an empty string (or, in some Desktop versions, the
placeholder itself), and a multiple-directory setting expands into one
argument per folder — so everything after --log-folders is a folder. An
empty data root means the one the pages use (Spec 02 §5.8.1); an empty
aircraft means the registry's only one, else the most recently opened (D10).
"""
from __future__ import annotations

import os
import sys
from typing import Optional

PORT = 8420


def _given(value: Optional[str]) -> Optional[str]:
    """A configured value, or None for empty / an unsubstituted placeholder."""
    v = (value or "").strip()
    return None if not v or v.startswith("${") else v


def translate(argv: list[str]) -> tuple[Optional[str], list[str]]:
    """(the data root to set, the `slingology-eis` argv)."""
    data_root = aircraft = None
    folders: list[str] = []
    port = PORT
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--log-folders":
            folders = [f for f in (_given(x) for x in argv[i + 1:]) if f]
            break
        nxt = argv[i + 1] if i + 1 < len(argv) else None
        if a == "--data-root":
            data_root = _given(nxt)
        elif a == "--aircraft":
            aircraft = _given(nxt)
        elif a == "--port":
            port = int(nxt) if _given(nxt) else PORT
        else:
            raise SystemExit(f"slingology-eis extension: unexpected argument {a!r}")
        i += 2
    out = ["mcp", "serve", "--serve", "--port", str(port), "--log-file", "--quiet"]
    if aircraft:
        out += ["--aircraft", aircraft]
    for f in folders:
        out += ["--log-folder", f]
    return data_root, out


def main(argv: Optional[list[str]] = None) -> int:
    data_root, args = translate(sys.argv[1:] if argv is None else argv)
    if data_root:
        os.environ["SLINGOLOGY_EIS_HOME"] = os.path.expanduser(data_root)
    from ..cli import main as cli_main
    return cli_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
