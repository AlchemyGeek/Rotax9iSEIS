import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { TopicHelpButton, renderHelpText } from "./TopicHelpButton";
import { topicHelp, topicHelp912iS } from "../lib/fixtures";

const oilTempHelp = topicHelp.topics.find((t) => t.id === "oil_temp_peak")!;
const mapAtTakeoff916 = topicHelp.topics.find((t) => t.id === "map_at_takeoff")!;
const mapAtTakeoff912 = topicHelp912iS.topics.find((t) => t.id === "map_at_takeoff")!;

describe("TopicHelpButton", () => {
  it("renders values in imperial units (canonical, °F)", () => {
    const text = renderHelpText(oilTempHelp, "imperial");
    expect(text).toContain("248°F");
    expect(text).not.toContain("{");
  });

  it("renders the same values converted to metric units (°C)", () => {
    const text = renderHelpText(oilTempHelp, "metric");
    expect(text).toContain("°C");
    expect(text).not.toContain("°F");
    expect(text).not.toContain("{");
  });

  it("opens a popover on click showing the title and formatted text", () => {
    render(<TopicHelpButton help={oilTempHelp} engine="916iS" units="imperial" />);
    const button = screen.getByRole("button", { name: `About: ${oilTempHelp.title}` });
    fireEvent.click(button);
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText(oilTempHelp.title)).toBeTruthy();
    expect(screen.getByText((t) => t.includes("248°F"))).toBeTruthy();
  });

  it("closes on Escape", () => {
    render(<TopicHelpButton help={oilTempHelp} engine="916iS" units="imperial" />);
    fireEvent.click(screen.getByRole("button", { name: `About: ${oilTempHelp.title}` }));
    expect(screen.queryByRole("dialog")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes on an outside click", () => {
    render(
      <div>
        <div data-testid="outside">outside</div>
        <TopicHelpButton help={oilTempHelp} engine="916iS" units="imperial" />
      </div>,
    );
    fireEvent.click(screen.getByRole("button", { name: `About: ${oilTempHelp.title}` }));
    expect(screen.queryByRole("dialog")).toBeTruthy();
    fireEvent.mouseDown(screen.getByTestId("outside"));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("renders no ? button for map_at_takeoff on the 912iS fixture (applies: false)", () => {
    expect(mapAtTakeoff912.applies).toBe(false);
    const { container } = render(<TopicHelpButton help={mapAtTakeoff912} engine="912iS" units="imperial" />);
    expect(container.querySelector("button")).toBeNull();
  });

  it("renders a ? button for map_at_takeoff on 916iS (applies: true)", () => {
    expect(mapAtTakeoff916.applies).toBe(true);
    render(<TopicHelpButton help={mapAtTakeoff916} engine="916iS" units="imperial" />);
    expect(screen.getByRole("button", { name: `About: ${mapAtTakeoff916.title}` })).toBeTruthy();
  });

  it("shows the unverified tag on a 912iS (Unverified) topic but not on 916iS (Admitted)", () => {
    const oilTemp912 = topicHelp912iS.topics.find((t) => t.id === "oil_temp_peak")!;
    expect(oilTemp912.validated).toBe(false);
    expect(oilTempHelp.validated).toBe(true);

    render(<TopicHelpButton help={oilTemp912} engine="912iS" units="imperial" />);
    fireEvent.click(screen.getByRole("button", { name: `About: ${oilTemp912.title}` }));
    expect(screen.getByText("Not yet validated on the 912iS")).toBeTruthy();
  });

  it("shows no unverified tag for the validated 916iS topic", () => {
    render(<TopicHelpButton help={oilTempHelp} engine="916iS" units="imperial" />);
    fireEvent.click(screen.getByRole("button", { name: `About: ${oilTempHelp.title}` }));
    expect(screen.queryByText(/Not yet validated/)).toBeNull();
  });
});
