import { SCOPE_CAPTION, type Scope } from "../lib/scope";

// Spec 14 §7.5 — the one-line scope caption at the top of a decision
// control's disclosure or dialog. Always visible, never behind an ⓘ.
export function ScopeCaption({ scope, note }: { scope: Scope; note?: string }) {
  return (
    <div data-scope={scope} style={{ fontSize: 11, color: "var(--text-tertiary)", fontWeight: 500 }}>
      {SCOPE_CAPTION[scope]}
      {note ? ` — ${note}` : ""}
    </div>
  );
}
