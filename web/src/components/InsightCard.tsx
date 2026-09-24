import type { Insight } from "../types/contract";
import { SeverityBadge } from "./SeverityBadge";

// Insights are the entry point, charts are the evidence (Spec 03
// principle 2) — clicking a card with evidence jumps/zooms the chart to
// the window that justifies it; cards with none render as plain info.
export function InsightCard({ insight, topicId, onClick }: { insight: Insight; topicId: string; onClick?: () => void }) {
  const clickable = Boolean(onClick && insight.evidence.length > 0);
  const Wrapper = clickable ? "a" : "div";
  return (
    <Wrapper
      href={clickable ? "#timeline" : undefined}
      onClick={clickable ? (e: React.MouseEvent) => { e.preventDefault(); onClick?.(); } : undefined}
      style={{
        display: "block",
        background: "var(--panel)",
        borderRadius: 10,
        padding: "13px 14px",
        cursor: clickable ? "pointer" : "default",
      }}
    >
      <div style={{ marginBottom: 6 }}>
        <SeverityBadge severity={insight.severity} />
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 3 }}>
        {topicId.replace(/_/g, " ")}
      </div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.4 }}>{insight.message.text}</div>
      {clickable && <div style={{ fontSize: 11, marginTop: 6 }}>View evidence →</div>}
    </Wrapper>
  );
}
