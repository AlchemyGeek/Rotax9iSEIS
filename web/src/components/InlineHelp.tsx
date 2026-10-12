import { INLINE_HELP, type InlineHelpId } from "../lib/inlineHelp";

// Spec 14 §7.4 — inline help, disclosed: an ⓘ whose sentence shows on
// hover or focus, never a paragraph in the layout. Text comes only from
// the INLINE_HELP registry.
export function InlineHelp({ id }: { id: InlineHelpId }) {
  const text = INLINE_HELP[id];
  return (
    <span
      role="img"
      tabIndex={0}
      aria-label={text}
      title={text}
      data-help-id={id}
      onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
      style={{ marginLeft: 5, fontSize: 11, color: "var(--text-tertiary)", cursor: "help", fontWeight: 400 }}
    >
      ⓘ
    </span>
  );
}
