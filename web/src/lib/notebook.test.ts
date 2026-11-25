// Spec 16 §5.3: the page's notebook markup is the HTML export's, string for
// string — both checked against one golden (tests/unit/test_nbhtml_parity.py
// writes and checks the engine side).
import { describe, expect, it } from "vitest";
import view from "../fixtures/research-notebook.json";
import golden from "../fixtures/research-notebook.render.json";
import { cellFlags, markdown, metaLine, nbMeta, outputHtml, outputsLine, outputsState, sanitizeTable, summaryBlock, text, type Notebook } from "./notebook";
import { cardLine } from "./notebookCard";
import { shortWindow } from "./timeLabel";
import type { NotebookCard } from "../types/contract";

const nb = view.notebook as unknown as Notebook;
const g = golden as unknown as {
  meta_line: string; outputs_line: string; summary: string; card_line: string; summary_block: string;
  short_windows: Record<string, string>;
  cells: Record<string, { markdown?: string; outputs?: string[]; flags?: string[] }>;
};

describe("notebook markup = the HTML export's", () => {
  it("header lines", () => {
    expect(metaLine(nbMeta(nb))).toBe(g.meta_line);
    expect(outputsLine(outputsState(nb))).toBe(g.outputs_line);
    expect(markdown(nbMeta(nb).summary ?? "")).toBe(g.summary);
    // Spec 03 v0.34: the card's line, the summary block with the earlier ones inside, short window strings.
    expect(cardLine(nbMeta(nb).card as NotebookCard)).toBe(g.card_line);
    expect(summaryBlock(nbMeta(nb).summary ?? "", [{ summary: "Earlier.", finished: "2026-01-01T00:00:00Z" }])).toBe(g.summary_block);
    for (const [label, short] of Object.entries(g.short_windows)) expect(shortWindow(label)).toBe(short);
  });
  for (const c of nb.cells) {
    it(`cell ${c.id}`, () => {
      const want = g.cells[c.id];
      if (c.cell_type === "markdown") expect(markdown(text(c.source), view.files)).toBe(want.markdown);
      else {
        expect((c.outputs ?? []).map(outputHtml)).toEqual(want.outputs);
        expect(cellFlags(c)).toEqual(want.flags);
      }
    });
  }
  it("a table claiming the mark keeps only table tags", () => {
    expect(sanitizeTable('<table onload="x()"><tr><td><script>alert(1)</script><img src=x onerror=y></td></tr></table>'))
      .toBe('<table class="eis-table"><tr><td>alert(1)</td></tr></table>');
  });
});
