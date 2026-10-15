import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Link, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, afterEach } from "vitest";
import { LocalServerClient } from "./engineClient";
import { ErrorBoundary } from "../components/ErrorBoundary";
import { useLocation } from "react-router-dom";

// A server started before the CAS-events change sends filters with a
// top-level limit_id and no `target`; the web must read that shape, not
// crash on filter.target.kind (seen live: Journal → Limit filters went
// black on a server running since 2026-10-11).

function serve(results: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn(async (_url: string, init: { body: string }) => {
    const { op } = JSON.parse(init.body);
    return { json: async () => ({ ok: true, result: results[op] }) };
  }));
}

afterEach(() => vi.unstubAllGlobals());

describe("filter shapes from an older server", () => {
  it("list, health, rebaseline and copy gain a limit target", async () => {
    const old = { id: "flt_1", limit_id: "fuel_press_max", note: "", reference: { flight_ids: [], set_at: "" }, created_at: "", history: [] };
    serve({
      list_filters: { filters: [{ filter: old, limit: { label: "Fuel pressure maximum" }, valid: true, diagnostics: [], summary: "up to +5 psi" }] },
      filter_health: { health: [{ filter_id: "flt_1", limit_id: "fuel_press_max", valid: true, status: "stable", reasons: [], diagnostics: [], series: [] }], attention_count: 0 },
      rebaseline_filter: old,
      copy_filters: { copied: [], skipped: [{ limit_id: "volts_min", reason: "exists" }] },
    });
    const c = new LocalServerClient("http://x");
    const list = await c.listFilters();
    expect(list.filters[0].filter.target).toEqual({ kind: "limit", limit_id: "fuel_press_max" });
    expect(list.filters[0].target_label).toBe("Fuel pressure maximum");
    expect((await c.filterHealth()).health[0].target).toEqual({ kind: "limit", limit_id: "fuel_press_max" });
    expect((await c.rebaselineFilter("flt_1")).target).toEqual({ kind: "limit", limit_id: "fuel_press_max" });
    expect((await c.copyFilters("ws")).skipped[0].target).toEqual({ kind: "limit", limit_id: "volts_min" });
  });

  it("leaves a current-shape target alone", async () => {
    const cas = { target: { kind: "cas", cas_id: "ENGINE ECU" } };
    serve({ filter_health: { health: [{ filter_id: "f", ...cas }], attention_count: 0 } });
    expect((await new LocalServerClient("http://x").filterHealth()).health[0].target).toEqual(cas.target);
  });
});

function Boom(): never {
  throw new Error("kaboom");
}

function Shell() {
  const location = useLocation();
  return (
    <>
      <Link to="/ok">go</Link>
      <ErrorBoundary resetKey={location.pathname}>
        <Routes>
          <Route path="/broken" element={<Boom />} />
          <Route path="/ok" element={<div>fine page</div>} />
        </Routes>
      </ErrorBoundary>
    </>
  );
}

describe("ErrorBoundary", () => {
  it("contains a page's render error and recovers on navigation", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<MemoryRouter initialEntries={["/broken"]}><Shell /></MemoryRouter>);
    expect(screen.getByRole("alert").textContent).toContain("kaboom");
    fireEvent.click(screen.getByText("go"));
    expect(screen.getByText("fine page")).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
