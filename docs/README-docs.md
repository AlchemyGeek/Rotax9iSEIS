# Building the documentation site

The pilot documentation lives in this folder and is built with [MkDocs](https://www.mkdocs.org/) and the Material theme.

```bash
pip install mkdocs-material
python3 docs/tools/gen_om_limits.py     # regenerate reference/om-limits.md from engines/*.json
mkdocs serve                             # live preview at http://127.0.0.1:8000
mkdocs build --strict                    # static site into site/
mkdocs gh-deploy                         # publish to GitHub Pages
```

Layout:

- `concepts/` — one page per concept; *In brief* on top, *how it works* below, specs and paper as further reading
- `walkthroughs/` — picture-led, task-shaped pages
- `reference/` — limits (generated), settings, glossary, further reading
- `diagrams/` — hand-drawn SVGs inlined into concept pages (they follow the site's light/dark theme)
- `img/` — screenshots taken from the N117ZS workspace; retake as a batch after a UI change
- `specs/` and the research paper are kept here for developers and excluded from the site nav
