import { useEffect, useState } from "react";
import { getEngineClient } from "./engineClient";
import { afterPageRequests } from "./pageRequests";

const client = getEngineClient();

// Spec 12 §9.5: the Trends nav badge — a passive count of open shift
// events, the same pattern as Notes' filter badge (filterAttention.ts).
// Dispatched whenever a reference is pinned/unpinned, a shift event is
// deleted, or the fleet is otherwise rebuilt, so the badge refreshes
// without polling.
export const SHIFT_HISTORY_CHANGED_EVENT = "slingology:shift-history-changed";

export function notifyShiftHistoryChanged() {
  window.dispatchEvent(new Event(SHIFT_HISTORY_CHANGED_EVENT));
}

// Number of open (uncleared) shift events; 0 when the server is
// unreachable (sample data) or there are none.
export function useShiftHistoryAttention(): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let cancelled = false;
    const load = () =>
      client
        .getFleet()
        .then((f) => !cancelled && setCount(f.shift_history.filter((e) => !e.cleared_at).length))
        .catch(() => !cancelled && setCount(0));
    // After the page's own requests (step 6): a badge is never what the page waits for.
    void afterPageRequests().then(() => { if (!cancelled) void load(); });
    window.addEventListener(SHIFT_HISTORY_CHANGED_EVENT, load);
    return () => {
      cancelled = true;
      window.removeEventListener(SHIFT_HISTORY_CHANGED_EVENT, load);
    };
  }, []);
  return count;
}
