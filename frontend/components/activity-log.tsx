"use client";

import { useEffect, useMemo, useState } from "react";
import { api, type ActivityEvent } from "@/lib/api";
import { dateTime, label } from "@/lib/format";
import { filterActivity } from "@/lib/terminal";

export function ActivityLog() {
  const [events, setEvents] = useState<ActivityEvent[]>([]); const [status, setStatus] = useState<"loading" | "ready" | "error">("loading"); const [error, setError] = useState("");
  const [eventType, setEventType] = useState(""); const [source, setSource] = useState(""); const [search, setSearch] = useState("");
  async function fetchEvents() { setStatus("loading"); try { const result = await api.activity("?limit=100"); setEvents(result.items); setStatus("ready"); } catch (reason) { setStatus("error"); setError(reason instanceof Error ? reason.message : "Activity is unavailable."); } }
  useEffect(() => { void fetchEvents(); }, []);
  const filtered = useMemo(() => filterActivity(events, { eventType, source, search }), [events, eventType, source, search]);
  const eventTypes = [...new Set(events.map((item) => item.event_type))]; const sources = [...new Set(events.map((item) => item.source))];
  return <section className="panel"><div className="panel-title-row"><div><h2>Research activity</h2><p className="subtle">Persisted lifecycle evidence and simulated events. No request payloads, credentials, or stack traces are displayed.</p></div><button type="button" className="text-button" onClick={() => void fetchEvents()}>Refresh</button></div><div className="feed-controls"><label>Event type<select value={eventType} onChange={(event) => setEventType(event.target.value)}><option value="">All events</option>{eventTypes.map((value) => <option value={value} key={value}>{label(value)}</option>)}</select></label><label>Source<select value={source} onChange={(event) => setSource(event.target.value)}><option value="">All sources</option>{sources.map((value) => <option value={value} key={value}>{label(value)}</option>)}</select></label><label className="search-field">Search<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Event, source, artifact"/></label></div>{status === "loading" && <div className="skeleton-list" aria-label="Loading research activity"><i/><i/><i/><i/></div>}{status === "error" && <div className="request-state error"><span>Activity unavailable</span><p>{error}</p><button type="button" onClick={() => void fetchEvents()}>Retry</button></div>}{status === "ready" && (filtered.length ? <div className="activity-list">{filtered.map((item, index) => <article key={`${item.event_type}-${item.artifact_id}-${item.timestamp}-${index}`}><time>{dateTime(item.timestamp)}</time><strong>{label(item.event_type)}</strong><span>{item.summary}</span><small>{label(item.source)}{item.artifact_id ? ` · ${item.artifact_id}` : ""}</small></article>)}</div> : <div className="state compact"><h2>No matching activity</h2><p>Change the filters or fetch a dataset, run an experiment, or start an existing validation workflow.</p></div>)}</section>;
}
