import { useState } from "react";
import type { Insight, ReferenceChangeMarker, RuleTopic, TopicHelp } from "../types/contract";
import { partitionTopicCards, type TopicCardModel } from "../lib/topicRoster";
import { SeverityBadge } from "./SeverityBadge";
import { TopicHelpButton, UnverifiedTag } from "./TopicHelpButton";
import { TriggerSummary } from "./TriggerSummary";

// Spec 03 v0.16 §5.2 — topic cards under the roster rule: a card is
// expanded only when it has something to say (a fired insight, a mirrored
// badge, a reference/rule-changed marker, a validity note); every other
// topic is one roster line — name · analysis · ? — expandable by tap.
// Expanded cards come first in severity order, then the roster. The
// analysis sentence (the "why nothing is wrong" half) is always there,
// one tap away at most.

export interface TopicCardsProps {
  cards: TopicCardModel[];
  helpById: Record<string, TopicHelp>;
  engineId: string;
  units: "imperial" | "metric";
  mixedAircraftCount: number | null; // > 1 in a blended workspace
  historyDerived: Set<string>;
  ruleFor: (topicId: string) => RuleTopic | null;
  canEditRules: (topicId: string) => boolean;
  onEditRules: (topicId: string, opts?: { enable?: boolean }) => void;
  onOpenInsight: (insight: Insight) => void;
  onRevertMarker: (marker: ReferenceChangeMarker) => void;
  onOpenFlights: () => void;
}

function titleOf(c: TopicCardModel, help: Record<string, TopicHelp>): string {
  return help[c.topic.topic_id]?.title ?? c.topic.topic_id.replace(/_/g, " ");
}

// limit_exceedances' sentence introduced its event rows (it ends in ":");
// those rows live in Events now (v0.16), so the card reads as a sentence.
function analysisText(c: TopicCardModel): string {
  const text = c.topic.analysis.text;
  return c.topic.topic_id === "limit_exceedances" ? text.replace(/:\s*$/, ".") : text;
}

export function TopicCards(props: TopicCardsProps) {
  const { expanded, roster } = partitionTopicCards(props.cards);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
      {expanded.length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
          {expanded.map((c) => <TopicCard key={c.topic.topic_id} card={c} {...props} />)}
        </div>
      )}
      {roster.length > 0 && (
        <div style={{ background: "var(--panel)", borderRadius: 10, padding: "4px 0" }} data-testid="topic-roster">
          {roster.map((c) => <RosterLine key={c.topic.topic_id} card={c} {...props} />)}
        </div>
      )}
    </div>
  );
}

function RosterLine({ card, ...props }: TopicCardsProps & { card: TopicCardModel }) {
  const [open, setOpen] = useState(false);
  const id = card.topic.topic_id;
  const title = titleOf(card, props.helpById);
  if (card.topic.enabled === false) {
    // Spec 14 §7.3 (v0.5): a disabled topic is one line — <topic> · disabled · Enable.
    return (
      <div data-testid={`roster-${id}`} style={{ padding: "7px 14px", fontSize: 12, color: "var(--text-tertiary)", borderTop: "1px solid var(--border)" }}>
        <span style={{ fontWeight: 600, color: "var(--text-secondary)" }}>{title}</span> · disabled
        {props.canEditRules(id) && (
          <>
            {" · "}
            <button type="button" onClick={() => props.onEditRules(id, { enable: true })} style={{ background: "none", border: "none", padding: 0, color: "var(--link)", textDecoration: "underline", textDecorationColor: "var(--link-underline)", textUnderlineOffset: 2, fontSize: 12, cursor: "pointer" }}>
              Enable
            </button>
          </>
        )}
      </div>
    );
  }
  if (open) {
    return (
      <div data-testid={`roster-${id}`} style={{ padding: "4px 6px", borderTop: "1px solid var(--border)" }}>
        <TopicCard card={card} {...props} onCollapse={() => setOpen(false)} flat />
      </div>
    );
  }
  return (
    <div
      data-testid={`roster-${id}`}
      role="button"
      tabIndex={0}
      onClick={() => setOpen(true)}
      onKeyDown={(e) => { if (e.key === "Enter") setOpen(true); }}
      style={{ display: "flex", alignItems: "center", gap: 6, padding: "7px 14px", fontSize: 12, cursor: "pointer", borderTop: "1px solid var(--border)", minWidth: 0 }}
    >
      <span style={{ fontWeight: 600, color: "var(--text-secondary)", flexShrink: 0 }}>{title}</span>
      <span style={{ color: "var(--text-tertiary)", flexShrink: 0 }}>·</span>
      <span style={{ color: "var(--text-tertiary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
        {analysisText(card)}
      </span>
      <span onClick={(e) => e.stopPropagation()} style={{ flexShrink: 0 }}>
        <TopicHelpButton help={props.helpById[id]} engine={props.engineId} units={props.units} />
      </span>
    </div>
  );
}

function TopicCard({ card, onCollapse, flat, ...props }: TopicCardsProps & { card: TopicCardModel; onCollapse?: () => void; flat?: boolean }) {
  const t = card.topic;
  const id = t.topic_id;
  const help = props.helpById[id];
  const badge = card.badge;
  const clickable = Boolean(badge && badge.evidence.length > 0 && id !== "limit_exceedances");
  return (
    <div
      data-testid={`card-${id}`}
      onClick={clickable ? () => props.onOpenInsight(badge!) : undefined}
      style={{ background: flat ? "transparent" : "var(--panel)", borderRadius: 10, padding: "12px 14px", cursor: clickable ? "pointer" : "default", alignSelf: "start" }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4, gap: 8 }}>
        <span style={{ display: "flex", alignItems: "center", minWidth: 0 }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)" }}>{titleOf(card, props.helpById)}</span>
          <span onClick={(e) => e.stopPropagation()}>
            <TopicHelpButton help={help} engine={props.engineId} units={props.units} />
          </span>
          {help && !help.validated && (
            <span style={{ marginLeft: 6 }}><UnverifiedTag engine={props.engineId} /></span>
          )}
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {badge && <SeverityBadge severity={badge.severity} size="sm" />}
          {onCollapse && (
            <span role="button" tabIndex={0} onClick={(e) => { e.stopPropagation(); onCollapse(); }} style={{ fontSize: 11, color: "var(--text-tertiary)", cursor: "pointer" }}>▴</span>
          )}
        </span>
      </div>
      <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.45 }}>{analysisText(card)}</div>
      {id === "limit_exceedances" && (
        <a
          href="#events"
          onClick={(e) => { e.preventDefault(); e.stopPropagation(); document.getElementById("events")?.scrollIntoView?.({ behavior: "smooth", block: "start" }); }}
          style={{ fontSize: 11, display: "inline-block", marginTop: 4 }}
        >
          See the events ↑
        </a>
      )}
      {card.mirrored && card.mirrored !== card.badge && (
        <div style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4 }}>Also: {card.mirrored.message.text}</div>
      )}
      {card.validityNotes.map((n) => (
        <div key={n} style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4 }}>{n}</div>
      ))}
      {card.markers.map(({ kind, marker }) => (
        <div key={marker.id} style={{ fontSize: 11, marginTop: 4, color: "var(--text-secondary)" }} onClick={(e) => e.stopPropagation()}>
          <strong style={{ color: "var(--severity-warning)" }}>{kind === "rule_changed" ? "rule changed" : "reference changed"}</strong>
          {` — ${marker.reason} (${marker.at.slice(0, 10)}) · `}
          <a href="#" onClick={(e) => { e.preventDefault(); props.onRevertMarker(marker); }}>Revert</a>
        </div>
      ))}
      {props.mixedAircraftCount !== null && props.mixedAircraftCount > 1 && props.historyDerived.has(id) && (
        <div
          onClick={(e) => { e.stopPropagation(); props.onOpenFlights(); }}
          style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4, cursor: "pointer" }}
        >
          Compared with all {props.mixedAircraftCount} aircraft in this workspace.
        </div>
      )}
      <TriggerSummary
        topic={t}
        rule={props.ruleFor(id)}
        onEditRules={props.canEditRules(id) ? () => props.onEditRules(id) : undefined}
      />
    </div>
  );
}
