// Spec 03 v0.34 — one status vocabulary (a coloured dot and a lower-case word) across questions,
// candidates and notebooks; the ⋯ menu; channel tags in the Flight view's colours.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ActionMenu, ChannelTags, StatusMark, statusWord } from "./bits";
import { fixedChannelColor } from "../../lib/channels";

describe("status vocabulary", () => {
  it("every status is one lower-case word set, never capitals", () => {
    const all = ["new", "investigating", "watch", "acted", "nothing-here", "open", "finished", "reopened"];
    expect(all.map(statusWord)).toEqual(["new", "investigating", "watch", "acted", "nothing here", "open", "finished", "reopened"]);
    for (const s of all) {
      const { unmount } = render(<StatusMark status={s} />);
      const el = screen.getByTestId("status-mark");
      expect(el.textContent).toBe(el.textContent!.toLowerCase());
      expect((el.firstChild as HTMLElement).style.background).toMatch(/^var\(--/);
      expect(el.getAttribute("title")).toBeTruthy();
      unmount();
    }
  });
  it("a colour given (a finished notebook's resolution) replaces the status's own", () => {
    render(<StatusMark status="finished" color="var(--success)" />);
    expect((screen.getByTestId("status-mark").firstChild as HTMLElement).style.background).toBe("var(--success)");
  });
});

describe("the ⋯ menu", () => {
  it("opens on click, runs the chosen item and closes; Escape closes it", () => {
    const a = vi.fn(), b = vi.fn();
    render(<ActionMenu items={[{ label: "Watch…", onSelect: a, testid: "i-a" }, { label: "Delete", onSelect: b, testid: "i-b", danger: true }]} />);
    const btn = screen.getByTestId("item-menu");
    expect(btn.getAttribute("aria-label")).toBe("More actions");
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(btn);
    expect(screen.getAllByRole("menuitem").map((m) => m.textContent)).toEqual(["Watch…", "Delete"]);
    fireEvent.click(screen.getByTestId("i-a"));
    expect(a).toHaveBeenCalledOnce();
    expect(screen.queryByRole("menu")).toBeNull();
    fireEvent.click(btn);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("menu")).toBeNull();
    expect(b).not.toHaveBeenCalled();
  });
});

describe("channel tags", () => {
  it("short names in the Flight view's channel colours, the full name on hover", () => {
    render(<ChannelTags channels={["rpm", "map_inhg", "egt2_f", "oil_temp_f"]} />);
    const tags = [...screen.getByTestId("channel-tags").querySelectorAll<HTMLElement>("[data-channel]")];
    expect(tags.map((t) => t.textContent)).toEqual(["RPM", "MAP", "EGT 2", "OIL T"]);
    expect(tags[0].style.color).toBe(hexToRgb(fixedChannelColor("rpm")!));
    expect(tags[3].getAttribute("title")).toBe("Oil temperature (oil_temp_f)");
  });
});

function hexToRgb(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  return `rgb(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255})`;
}
