import { useEffect, useState } from "react";
import { getEngineClient } from "./engineClient";
import { afterPageRequests } from "./pageRequests";

const client = getEngineClient();

// The Notes nav badge and the Flights banner (Spec 09 §10.4) listen for
// this, so they refresh as soon as a filter changes on the Notes page or
// in the Flight view's editor.
export const FILTERS_CHANGED_EVENT = "slingology:filters-changed";

export function notifyFiltersChanged() {
  window.dispatchEvent(new Event(FILTERS_CHANGED_EVENT));
}

// Number of filters that are Breached or Drifting; 0 when the server is
// unreachable (sample data) or the workspace has none.
export function useFilterAttention(): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      client
        .filterHealth()
        .then((r) => !cancelled && setCount(r.attention_count))
        .catch(() => !cancelled && setCount(0));
    // After the page's own requests (step 6): a badge is never what the page waits for.
    void afterPageRequests().then(() => { if (!cancelled) void load(); });
    window.addEventListener(FILTERS_CHANGED_EVENT, load);
    return () => {
      cancelled = true;
      window.removeEventListener(FILTERS_CHANGED_EVENT, load);
    };
  }, []);
  return count;
}
