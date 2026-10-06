import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MixedAircraftNotice } from "./MixedAircraftNotice";

const state = {
  aliases: [] as string[][],
};

vi.mock("../lib/engineClient", () => ({
  getEngineClient: () => ({
    getAircraftSummary: async () => ({
      idents: state.aliases.length ? [state.aliases[0][0]] : ["N117ZS", "N456CD"],
      raw_idents: ["N117ZS", "N456CD"],
      aliases: state.aliases,
    }),
    getWorkspaceSettings: async () => ({ anonymize_by_default: false, active_engine_profile: "916iS", aircraft_aliases: state.aliases }),
    saveWorkspaceSettings: async (s: { aircraft_aliases: string[][] }) => {
      state.aliases = s.aircraft_aliases;
      return s;
    },
  }),
}));

describe("MixedAircraftNotice", () => {
  beforeEach(() => {
    state.aliases = [];
  });

  it("shows the notice with both tail numbers when there are two distinct aircraft", async () => {
    render(<MixedAircraftNotice usingFixture={false} />);
    await screen.findByText(/This workspace contains flights from 2 aircraft/);
    expect(screen.getByText(/N117ZS, N456CD/)).toBeTruthy();
  });

  it("groups two idents and the notice disappears once they count as one aircraft", async () => {
    render(<MixedAircraftNotice usingFixture={false} />);
    await screen.findByText(/This workspace contains flights from 2 aircraft/);

    fireEvent.click(screen.getByText("These are the same aircraft…"));
    fireEvent.click(screen.getByLabelText("N117ZS"));
    fireEvent.click(screen.getByLabelText("N456CD"));
    fireEvent.click(screen.getByText("Confirm same aircraft"));

    await waitFor(() => {
      expect(screen.queryByText(/This workspace contains flights from 2 aircraft/)).toBeNull();
    });
  });

  it("renders nothing for a single-aircraft fixture workspace", () => {
    const { container } = render(<MixedAircraftNotice usingFixture={true} />);
    expect(container.textContent).toBe("");
  });
});
