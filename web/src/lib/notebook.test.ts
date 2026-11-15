// Spec 16 §5.3: the page's notebook markup is the HTML export's, string for
// string — both checked against one golden (tests/unit/test_nbhtml_parity.py
// writes and checks the engine side).
import { describe, expect, it } from "vitest";
import view from "../fixtures/research-notebook.json";
import golden from "../fixtures/research-notebook.render.json";
import { cellFlags, markdown, metaLine, nbMeta, outputHtml, outputsLine, outputsState, sanitizeTable, text, type Notebook } from "./notebook";

const nb = view.notebook as unknown as Notebook;
const g = golden as unknown as {
  meta_line: string; outputs_line: string; summary: string;
  cells: Record<string, { markdown?: string; outputs?: string[]; flags?: string[] }>;
};

describe("notebook markup = the HTML export's", () => {
  it("header lines", () => {
    expect(metaLine(nbMeta(nb))).toBe(g.meta_line);
    expect(outputsLine(outputsState(nb))).toBe(g.outputs_line);
    expect(markdown(nbMeta(nb).summary ?? "")).toBe(g.summary);
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
