import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Spec 16 D16 — the Flight view's *Mark for Claude*: with a window
// selected, a note and the question it belongs to (a new one with a title,
// an open one, or none); a confirmation says where it went. The pin holds
// flight, window, channels and the note — nothing measured. Synthetic.

const state = vi.hoisted(() => ({ calls: [] as Record<string, unknown>[], open: [] as Record<string, unknown>[] }));

vi.mock("../lib/engineClient", async () => {
  const actual = await vi.importActual<typeof import("../lib/engineClient")>("../lib/engineClient");
  const client = {
    pinsList: async () => ({ questions: state.open, unassigned: [], counts: {}, pins: 0, newest_open: state.open.at(-1)?.id ?? null }),
    flightPin: async (args: Record<string, unknown>) => {
      state.calls.push(args);
      const q = args.question;
      const title = q && typeof q === "object" ? (q as { title: string }).title : typeof q === "string" ? state.open.find((x) => x.id === q)?.title : null;
      return { pin: { id: "p-1" }, question: title ? { id: "q-1", title } : null,
        where: title ? `under “${title}” (1 mark) in Research → Inbox` : "in Research → Inbox, under Unassigned" };
    },
  };
  return { ...actual, getEngineClient: () => client };
});

import { MarkForClaude } from "./MarkForClaude";

beforeEach(() => {
  state.calls = [];
  state.open = [];
});

function mark(zoomed = true) {
  render(<MarkForClaude flightId="fa" window={[616.2, 661.7]} channels={["rpm", "map_inhg"]} zoomed={zoomed} />);
}

describe("Mark for Claude (D16)", () => {
  it("needs a window: without a zoom the button is off and says why", () => {
    mark(false);
    const b = screen.getByTestId("mark-open") as HTMLButtonElement;
    expect(b.disabled).toBe(true);
    expect(b.title).toContain("Zoom the chart");
  });

  it("a new question with a title: the pin is flight, window, channels and the note — and the confirmation says where", async () => {
    mark();
    fireEvent.click(screen.getByTestId("mark-open"));
    const dialog = await screen.findByTestId("mark-dialog");
    expect(screen.getByTestId("mark-window").textContent).toBe("10:16–11:02 into the flight · RPM, MAP");
    expect((screen.getByTestId("mark-save") as HTMLButtonElement).disabled).toBe(true);   // a new question needs a title
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "rpm wanders by about 100" } });
    fireEvent.change(screen.getByLabelText("New question title"), { target: { value: "rough climbs" } });
    fireEvent.click(screen.getByTestId("mark-save"));
    await waitFor(() => expect(state.calls).toEqual([{ flight_id: "fa", start_s: 616, end_s: 662, channels: ["rpm", "map_inhg"],
      note: "rpm wanders by about 100", question: { title: "rough climbs" } }]));
    expect((await screen.findByTestId("mark-done")).textContent).toBe(
      "Marked 10:16–11:02 under “rough climbs” (1 mark) in Research → Inbox. In Claude Desktop, choose Investigate — with no text it takes your newest open question.");
    expect(dialog.isConnected).toBe(false);
  });

  it("an open question is offered first, the newest chosen", async () => {
    state.open = [{ id: "q-a", title: "oil warm", pin_count: 1 }, { id: "q-b", title: "rough climbs", pin_count: 2 }];
    mark();
    fireEvent.click(screen.getByTestId("mark-open"));
    const select = (await screen.findByLabelText("Open question")) as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(["oil warm (1 mark)", "rough climbs (2 marks)"]);
    await waitFor(() => expect(select.value).toBe("q-b"));
    fireEvent.click(screen.getByTestId("mark-save"));
    await waitFor(() => expect(state.calls[0]).toMatchObject({ question: "q-b", note: null }));
  });

  it("none for now: an unassigned mark", async () => {
    mark();
    fireEvent.click(screen.getByTestId("mark-open"));
    await screen.findByTestId("mark-dialog");
    fireEvent.click(screen.getByLabelText("None for now (unassigned)"));
    fireEvent.click(screen.getByTestId("mark-save"));
    await waitFor(() => expect(state.calls[0]).toMatchObject({ question: null }));
    expect((await screen.findByTestId("mark-done")).textContent).toContain("in Research → Inbox, under Unassigned");
  });
});
