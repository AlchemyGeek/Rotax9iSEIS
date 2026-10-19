import { useEffect, useState } from "react";
import { getEngineClient } from "./engineClient";
import type { HostCapabilities } from "../types/contract";

// Spec 04 v0.7 §9.5 / Spec 03 §6.4: one build; the UI gates on the host's
// features, never on which host it is. Unknown (an older server, a test
// with a mocked client) behaves as the local server always has.

let loading: Promise<HostCapabilities | null> | null = null;
let known: HostCapabilities | null = null;

export function loadCapabilities(): Promise<HostCapabilities | null> {
  if (!loading) {
    loading = Promise.resolve()
      .then(() => getEngineClient().getCapabilities())
      .then((c) => (known = c ?? null), () => null);
  }
  return loading;
}

export function useCapabilities(): HostCapabilities | null {
  const [caps, setCaps] = useState<HostCapabilities | null>(known);
  useEffect(() => {
    let live = true;
    loadCapabilities().then((c) => { if (live) setCaps(c); });
    return () => { live = false; };
  }, []);
  return caps;
}

/** Tests: forget what was loaded. */
export function resetCapabilities() {
  loading = null;
  known = null;
}
