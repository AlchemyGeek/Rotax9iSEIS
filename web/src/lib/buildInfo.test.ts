import { describe, expect, it } from "vitest";
import { APP_BUILD, describeBuild } from "./buildInfo";

describe("describeBuild", () => {
  it("names the version, the commit and when it was built", () => {
    const s = describeBuild({ version: "1.0.1", commit: "9829bd1", modified: false, built_at: "2026-10-20T21:30:00Z" }, "en-US");
    expect(s).toMatch(/^1\.0\.1 · build 9829bd1 · Oct 20, 2026/);
    expect(s).not.toContain("modified");
  });

  it("says so when built from uncommitted changes", () => {
    expect(describeBuild({ version: "1.0.1", commit: "9829bd1", modified: true, built_at: "2026-10-20T21:30:00Z" })).toMatch(/ · modified$/);
  });

  it("is stamped into the bundle", () => {
    expect(APP_BUILD.version).toMatch(/^\d+\.\d+\.\d+/);
    expect(APP_BUILD.commit).toMatch(/^[0-9a-f]{7}$|^unknown$/);
  });
});
