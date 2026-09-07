"use client";

import { useMemo, useState } from "react";
import type { AgentDecision } from "@/lib/api";
import { label, percent } from "@/lib/format";

type AgentName = "all" | "technical" | "regime" | "strategy" | "risk";
type TimelineEvent = { agent: Exclude<AgentName, "all">; timestamp: string; decision: string; confidence?: number; detail: string; item: AgentDecision };

function eventsFor(items: AgentDecision[]): TimelineEvent[] {
  return items.flatMap((item) => [
    { agent: "technical" as const, timestamp: item.timestamp, decision: String(item.technical.trend), confidence: Number(item.technical.confidence), detail: `momentum=${String(item.technical.momentum)} · volatility=${String(item.technical.volatility)} · RSI=${String(item.technical.rsi)}`, item },
    { agent: "regime" as const, timestamp: item.timestamp, decision: item.regime.regime, confidence: item.regime.confidence, detail: `causal regime=${item.regime.regime}`, item },
    { agent: "strategy" as const, timestamp: item.timestamp, decision: item.proposal.action, confidence: item.proposal.confidence, detail: `${item.proposal.selected_strategy} · ${item.proposal.reason_codes.join(", ")}`, item },
    { agent: "risk" as const, timestamp: item.timestamp, decision: item.risk.approved ? "APPROVED" : "REJECTED", detail: `${percent(item.risk.adjusted_position_size)} position · ${item.risk.reason_code}`, item },
  ]);
}

export function AgentDecisionTimeline({ items, onSelect }: { items: AgentDecision[]; onSelect: (timestamp: string) => void }) {
  const [agent, setAgent] = useState<AgentName>("all");
  const [decision, setDecision] = useState("all");
  const events = useMemo(() => eventsFor(items).filter((item) => (agent === "all" || item.agent === agent) && (decision === "all" || item.decision === decision)), [agent, decision, items]);
  const decisions = [...new Set(eventsFor(items).map((item) => item.decision))];
  if (!items.length) return <p className="subtle">This experiment did not persist agent decision records.</p>;
  return <div className="agent-feed"><div className="feed-controls"><label>Agent<select value={agent} onChange={(event) => setAgent(event.target.value as AgentName)}><option value="all">All agents</option><option value="technical">Technical</option><option value="regime">Regime</option><option value="strategy">Strategy</option><option value="risk">Risk</option></select></label><label>Decision<select value={decision} onChange={(event) => setDecision(event.target.value)}><option value="all">All decisions</option>{decisions.map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></label><span>{events.length} events</span></div><div className="agent-events">{events.slice().reverse().map((event, index) => <button type="button" className={`agent-event ${event.agent}`} key={`${event.agent}-${event.timestamp}-${index}`} onClick={() => onSelect(event.timestamp)}><time>{event.timestamp.slice(0, 19).replace("T", " ")}</time><strong>{event.agent.toUpperCase()}</strong><span>{label(event.decision)}</span>{event.confidence !== undefined && !Number.isNaN(event.confidence) && <em>{percent(event.confidence)}</em>}<small>{event.detail}</small></button>)}</div></div>;
}
