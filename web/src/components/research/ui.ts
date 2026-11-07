import type { CSSProperties } from "react";

// Shared Research styles, in the app's panel idiom (Settings/Journal).
export const PANEL: CSSProperties = { background: "var(--panel)", borderRadius: 12, padding: "16px 18px" };
export const PANEL_TITLE: CSSProperties = { fontSize: 13, fontWeight: 600, marginBottom: 10, display: "flex", alignItems: "center", gap: 8 };
export const MUTED: CSSProperties = { fontSize: 11, color: "var(--text-tertiary)" };
export const BODY: CSSProperties = { fontSize: 12, color: "var(--text-secondary)" };
export const INPUT: CSSProperties = { background: "var(--bg)", border: "1px solid var(--border)", borderRadius: 6, padding: "5px 8px", color: "var(--text-primary)", fontSize: 12 };
export const SELECT: CSSProperties = { ...INPUT, padding: "5px 6px" };
export const BUTTON: CSSProperties = { padding: "5px 11px", borderRadius: 6, background: "var(--panel-control)", border: "1px solid var(--border)", color: "var(--text-primary)", fontSize: 12, cursor: "pointer" };
export const PRIMARY: CSSProperties = { ...BUTTON, background: "var(--brand)", border: "none", color: "var(--on-brand)", fontWeight: 600 };
export const LINK: CSSProperties = { background: "none", border: "none", padding: 0, color: "var(--link)", textDecoration: "underline", textDecorationColor: "var(--link-underline)", textUnderlineOffset: 2, fontSize: 11, cursor: "pointer" };
export const CHIP: CSSProperties = { display: "inline-flex", alignItems: "center", gap: 6, padding: "3px 9px", borderRadius: 999, background: "var(--panel-control)", border: "1px solid var(--border)", fontSize: 11, color: "var(--text-secondary)" };
export const TH: CSSProperties = { textAlign: "left", padding: "6px 10px", fontSize: 11, color: "var(--text-tertiary)", fontWeight: 600, whiteSpace: "nowrap", borderBottom: "1px solid var(--border)" };
export const TD: CSSProperties = { padding: "6px 10px", fontSize: 12, whiteSpace: "nowrap", borderBottom: "1px solid var(--border)" };
export const NOTICE: CSSProperties = { background: "rgba(245,165,36,0.08)", border: "1px solid rgba(245,165,36,0.3)", borderRadius: 8, padding: "8px 12px", fontSize: 12 };
