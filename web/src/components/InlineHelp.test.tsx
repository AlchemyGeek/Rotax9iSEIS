import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { InlineHelp } from "./InlineHelp";
import { INLINE_HELP } from "../lib/inlineHelp";

describe("InlineHelp", () => {
  it("shows its sentence on click and closes on Escape or a click elsewhere", () => {
    render(<div><InlineHelp id="trigger.r2_min" /><span>elsewhere</span></div>);
    expect(screen.queryByRole("tooltip")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "What is this?" }));
    expect(screen.getByRole("tooltip").textContent).toBe(INLINE_HELP["trigger.r2_min"]);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "What is this?" }));
    fireEvent.mouseDown(screen.getByText("elsewhere"));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("does not toggle a surrounding label's checkbox", () => {
    render(<label><span>enabled<InlineHelp id="trigger.enabled" /></span><input type="checkbox" defaultChecked /></label>);
    fireEvent.click(screen.getByRole("button", { name: "What is this?" }));
    expect((screen.getByRole("checkbox") as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole("tooltip")).toBeTruthy();
  });
});
