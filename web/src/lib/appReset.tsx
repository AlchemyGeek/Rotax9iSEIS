import { useEffect, useState, type ReactNode } from "react";

// Spec 14 v0.17 §5.2.1 / Spec 03 v0.25 §6.3: after Delete all data on this
// device the app returns to the first-run state itself — every page and the
// workspace menu are mounted afresh and read the (now empty) data root.

const listeners = new Set<() => void>();

export function resetApp() {
  for (const fn of listeners) fn();
}

export function AppReset({ children }: { children: ReactNode }) {
  const [epoch, setEpoch] = useState(0);
  useEffect(() => {
    const fn = () => setEpoch((e) => e + 1);
    listeners.add(fn);
    return () => { listeners.delete(fn); };
  }, []);
  return <div key={epoch} style={{ display: "contents" }}>{children}</div>;
}
