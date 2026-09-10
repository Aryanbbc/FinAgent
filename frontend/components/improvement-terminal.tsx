"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, publicMutationControlsEnabled, type Critique, type Improvement, type ImprovementContext, type Version } from "@/lib/api";
import { number, percent } from "@/lib/format";
import { humanCode, metric, promotionChecks, reasonExplanation, valueText } from "@/lib/improvement-display";

type Props = { improvements: Improvement[]; versions: Version[]; context: ImprovementContext };

function tone(status: string) { return status === "PROMOTED" ? "pass" : status === "REJECTED" ? "fail" : "unknown"; }
function candidateStatus(candidate: Improvement) { return candidate.status === "PROMOTED" ? "PROMOTED" : "REJECTED"; }
function changes(candidate: Improvement) { return candidate.parameter_changes ?? []; }

function Metric({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return <section className="improvement-metric"><span title={hint}>{label}</span><strong>{value}</strong></section>;
}

function CandidateCard({ candidate, selected, onOpen }: { candidate: Improvement; selected: boolean; onOpen: (candidate: Improvement) => void }) {
  const metrics = candidate.candidate_metrics;
  return <button type="button" className={`candidate-card ${tone(candidate.status)} ${selected ? "selected" : ""}`} onClick={() => onOpen(candidate)}>
    <div className="candidate-card-head"><span>{candidate.run_id}</span><b>{candidateStatus(candidate)}</b></div>
    <div className="candidate-changes">{changes(candidate).length ? changes(candidate).map((change, index) => <p key={`${String(change.parameter)}-${index}`}><strong>{humanCode(String(change.parameter))}</strong><small>{valueText(change.previous_value)} → {valueText(change.proposed_value)}</small></p>) : <p><small>No persisted parameter delta</small></p>}</div>
    <div className="candidate-card-metrics"><span>WF {candidate.window_count}</span><span>Sharpe {metric(metrics, "sharpe_ratio")?.toFixed(2) ?? "—"}</span><span>Return {percent(metric(metrics, "total_return"))}</span><span>DD {percent(metric(metrics, "maximum_drawdown"))}</span><span>Turn {metric(metrics, "turnover")?.toFixed(2) ?? "—"}</span><span>Pass {percent(candidate.window_pass_rate, 0)}</span></div>
  </button>;
}

function CriticFindings({ critique }: { critique: Critique | null }) {
  const findings = useMemo(() => {
    if (!critique) return [];
    const seen = new Set<string>();
    return [...critique.weaknesses, ...critique.failure_modes].filter((item) => !seen.has(item.code) && !!seen.add(item.code));
  }, [critique]);
  return <section className="terminal-panel improvement-critic">
    <div className="terminal-panel-head"><div><span className="terminal-overline">Parent experiment evidence</span><h2>Critic findings</h2></div>{critique && <span className="terminal-meta">{percent(critique.confidence)} confidence</span>}</div>
    {findings.length ? <div className="finding-grid">{findings.map((finding) => <article key={finding.code} className="finding-card"><strong>{humanCode(finding.code)}</strong><p>{finding.summary}</p></article>)}</div> : <div className="compact-empty"><strong>No parent critique linked</strong><span>The selected parent version has no persisted critique record to display.</span></div>}
  </section>;
}

function GatePanel({ candidate, thresholdsPersisted }: { candidate: Improvement | undefined; thresholdsPersisted: boolean }) {
  if (!candidate) return <section className="terminal-panel"><span className="terminal-overline">Promotion gate</span><h2>No candidate selected</h2><p className="subtle">Select a persisted candidate to inspect its recorded promotion result.</p></section>;
  return <section className="terminal-panel improvement-gate">
    <div className="terminal-panel-head"><div><span className="terminal-overline">Promotion gate · {candidate.run_id}</span><h2>Recorded promotion checks</h2></div><span className={`gate-decision ${tone(candidate.status)}`}>{candidateStatus(candidate)}</span></div>
    <div className="gate-grid">{promotionChecks(candidate).map((check) => <div className={`gate-check ${check.state}`} key={check.id}><span title={check.tooltip}>{check.label}</span><strong>{check.state === "pass" ? "PASS" : check.state === "fail" ? "FAIL" : "UNAVAILABLE"}</strong><small>{check.evidence}</small></div>)}</div>
    {!thresholdsPersisted && <p className="gate-note">Historic records preserve each gate outcome and reason code, but not the numeric policy thresholds used at run time.</p>}
  </section>;
}

function CandidateDrawer({ candidate, detail, status, error, onClose }: { candidate: Improvement | null; detail: Improvement | null; status: "idle" | "loading" | "ready" | "error"; error: string; onClose: () => void }) {
  useEffect(() => {
    if (!candidate) return;
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [candidate, onClose]);
  if (!candidate) return null;
  const record = detail ?? candidate;
  const windows = record.windows ?? [];
  return <div className="candidate-drawer-backdrop" role="presentation" onMouseDown={onClose}><aside className="candidate-drawer" role="dialog" aria-modal="true" aria-label={`${candidate.run_id} candidate detail`} onMouseDown={(event) => event.stopPropagation()}>
    <div className="candidate-drawer-head"><div><span className="terminal-overline">Candidate evidence</span><h2>{candidate.run_id}</h2></div><button type="button" className="text-button" onClick={onClose}>Close</button></div>
    {status === "loading" && <div className="skeleton-list"><i/><i/><i/></div>}
    {status === "error" && <div className="request-state error"><span>Candidate detail unavailable</span><p>{error}</p></div>}
    {status === "ready" && <>
      <section><h3>Full parameter delta</h3><div className="drawer-changes">{changes(record).map((change, index) => <div key={`${String(change.parameter)}-${index}`}><strong>{humanCode(String(change.parameter))}</strong><span>{valueText(change.previous_value)} → {valueText(change.proposed_value)}</span></div>)}</div></section>
      <section><h3>Validation metrics</h3><div className="drawer-metrics"><Metric label="OOS Sharpe" value={metric(record.candidate_metrics, "sharpe_ratio")?.toFixed(3) ?? "—"}/><Metric label="OOS return" value={percent(metric(record.candidate_metrics, "total_return"))}/><Metric label="OOS drawdown" value={percent(metric(record.candidate_metrics, "maximum_drawdown"))}/><Metric label="Turnover" value={number(metric(record.candidate_metrics, "turnover"))}/><Metric label="Pass rate" value={percent(record.window_pass_rate)}/></div></section>
      <section><h3>Exact recorded gate outcome</h3><div className="drawer-checks">{promotionChecks(record).map((check) => <div key={check.id} className={check.state}><strong>{check.state.toUpperCase()}</strong><span>{check.label}</span><small>{check.evidence}</small></div>)}</div></section>
      <section><h3>Rejection reasons</h3>{record.reason_codes.filter((code) => !["REJECTED", "PROMOTED"].includes(code)).length ? <ul className="reason-list">{record.reason_codes.filter((code) => !["REJECTED", "PROMOTED"].includes(code)).map((code) => <li key={code}><strong>{humanCode(code)}</strong><span>{reasonExplanation(code)}</span></li>)}</ul> : <p className="good">No rejection reason was recorded.</p>}</section>
      <section><h3>Chronological walk-forward windows ({windows.length})</h3>{windows.length ? <div className="table-wrap drawer-window-table"><table><thead><tr><th>Window</th><th>Test period</th><th>Parent Sharpe</th><th>Candidate Sharpe</th><th>Return</th><th>Drawdown</th></tr></thead><tbody>{windows.map((window, index) => { const parent = window.parent_metrics as Record<string, number | null>; const candidateMetrics = window.candidate_metrics as Record<string, number | null>; return <tr key={String(window.window_index ?? index)}><td>{String(window.window_index ?? index + 1)}</td><td>{String(window.test_start ?? "").slice(0, 10)} – {String(window.test_end ?? "").slice(0, 10)}</td><td>{parent.sharpe_ratio?.toFixed(2) ?? "—"}</td><td>{candidateMetrics.sharpe_ratio?.toFixed(2) ?? "—"}</td><td>{percent(candidateMetrics.total_return)}</td><td>{percent(candidateMetrics.maximum_drawdown)}</td></tr>; })}</tbody></table></div> : <p className="subtle">No persisted walk-forward window detail is available for this candidate.</p>}</section>
    </>}
  </aside></div>;
}

export function ImprovementTerminal({ improvements, versions, context }: Props) {
  const router = useRouter();
  const candidates = context.parent_version_id ? improvements.filter((item) => item.parent_version_id === context.parent_version_id) : improvements;
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [drawerCandidate, setDrawerCandidate] = useState<Improvement | null>(null);
  const [detail, setDetail] = useState<Improvement | null>(null);
  const [drawerStatus, setDrawerStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [drawerError, setDrawerError] = useState("");
  const [runStatus, setRunStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [runMessage, setRunMessage] = useState("");
  const selected = candidates.find((item) => item.run_id === selectedId) ?? candidates[0];
  const noPromotion = context.candidates_evaluated > 0 && context.candidates_promoted === 0;
  async function openCandidate(candidate: Improvement) {
    setSelectedId(candidate.run_id); setDrawerCandidate(candidate); setDetail(null); setDrawerError(""); setDrawerStatus("loading");
    try { setDetail(await api.improvement(candidate.run_id)); setDrawerStatus("ready"); }
    catch (reason) { setDrawerError(reason instanceof Error ? reason.message : "Candidate detail could not be loaded."); setDrawerStatus("error"); }
  }
  async function runCycle() {
    setRunStatus("loading"); setRunMessage("");
    try { await api.run("improvements", "config/improvement.yaml"); setRunStatus("success"); setRunMessage("The configured deterministic improvement workflow completed. Refreshing persisted evidence…"); router.refresh(); }
    catch (reason) { setRunStatus("error"); setRunMessage(reason instanceof Error ? reason.message : "The improvement workflow could not be started."); }
  }

  if (!versions.length && !improvements.length) return <div className="state"><h2>No controlled improvement evidence</h2><p>Run a completed historical experiment and its configured deterministic improvement workflow to populate this terminal.</p></div>;
  return <div className="improvement-terminal">
    <section className="improvement-summary terminal-panel">
      <div className="terminal-panel-head"><div><span className="terminal-overline">Controlled learning pipeline</span><h2>Self-Improvement Summary</h2><p className="subtle">Parent version → critic findings → bounded candidates → chronological validation → strict promotion gate.</p></div>{publicMutationControlsEnabled && <button type="button" disabled={runStatus === "loading"} onClick={() => void runCycle()}>{runStatus === "loading" ? "Running improvement…" : "Run Improvement Cycle"}</button>}</div>
      <div className="improvement-summary-grid"><Metric label="Current FinAgent version" value={context.current_version?.version_id ?? "—"}/><Metric label="Parent version" value={context.parent_version_id ?? "—"}/><Metric label="Candidates generated" value={String(context.candidates_generated)}/><Metric label="Evaluated" value={String(context.candidates_evaluated)}/><Metric label="Promoted" value={String(context.candidates_promoted)}/><Metric label="Rejected" value={String(context.candidates_rejected)}/><Metric label="Latest recorded outcome" value={context.latest_candidate_status ?? "No decision"}/></div>
      {runStatus !== "idle" && <div className={`request-state ${runStatus === "error" ? "error" : runStatus === "success" ? "success" : ""}`}><span>{runStatus === "error" ? "Improvement unavailable" : runStatus === "success" ? "Improvement completed" : "Running workflow"}</span><p>{runMessage || "The backend is evaluating only its configured, deterministic workflow."}</p></div>}
      {!context.cycle_boundaries_persisted && <p className="summary-note">Candidate counts are exact for the displayed parent version. Historic records do not store explicit cycle boundaries.</p>}
    </section>
    {noPromotion && <section className="no-promotion"><strong>NO CANDIDATE PROMOTED</strong><span>Every displayed candidate remains part of the research record; none met every deterministic promotion safeguard.</span></section>}

    <section className="pipeline-flow" aria-label="Controlled self-improvement pipeline"><div><span>01</span><strong>{context.parent_version_id ?? "Parent unavailable"}</strong><small>Parent version</small></div><i>→</i><div><span>02</span><strong>Critic</strong><small>Persisted findings</small></div><i>→</i><div><span>03</span><strong>{context.candidates_generated}</strong><small>Bounded candidates</small></div><i>→</i><div><span>04</span><strong>{context.candidates_evaluated}</strong><small>Walk-forward evaluated</small></div><i>→</i><div><span>05</span><strong>Gate</strong><small>Strict evidence checks</small></div><i>→</i><div className={noPromotion ? "rejected" : "promoted"}><span>06</span><strong>{noPromotion ? "Rejected" : context.candidates_promoted ? "Promoted" : "Awaiting evidence"}</strong><small>Version outcome</small></div></section>

    <CriticFindings critique={context.parent_critique}/>

    <section className="terminal-panel candidate-pipeline"><div className="terminal-panel-head"><div><span className="terminal-overline">Candidate generation and held-out evidence</span><h2>Candidate pipeline</h2></div><span className="terminal-meta">{candidates.length} displayed</span></div>{candidates.length ? <div className="candidate-card-grid">{candidates.map((candidate) => <CandidateCard candidate={candidate} key={candidate.run_id} selected={selected?.run_id === candidate.run_id} onOpen={(item) => void openCandidate(item)}/>)}</div> : <div className="compact-empty"><strong>No evaluated candidate for this parent</strong><span>Candidate configurations may not yet have reached a persisted evaluation.</span></div>}</section>

    <div className="improvement-gate-layout"><GatePanel candidate={selected} thresholdsPersisted={context.gate_thresholds_persisted}/><section className="terminal-panel rejection-explanations"><span className="terminal-overline">Decision interpretation</span><h2>Rejection reason explanation</h2>{selected ? <ul className="reason-list">{selected.reason_codes.filter((code) => !["REJECTED", "PROMOTED"].includes(code)).map((code) => <li key={code}><strong>{humanCode(code)}</strong><span>{reasonExplanation(code)}</span></li>)}</ul> : <p className="subtle">Select a candidate to inspect its persisted reason codes.</p>}</section></div>

    <section className="terminal-panel candidate-comparison"><div className="terminal-panel-head"><div><span className="terminal-overline">Comparable OOS evidence</span><h2>Candidate comparison</h2></div><span className="terminal-meta">Click any row for all windows</span></div><div className="table-wrap"><table><thead><tr><th>Candidate</th><th>Changes</th><th title="Out-of-sample Sharpe ratio">OOS Sharpe</th><th>OOS Return</th><th>OOS Drawdown</th><th>Trades/year</th><th>Avg hold</th><th title="Gross traded notional relative to average equity">Turnover</th><th title="Share of walk-forward windows improving on the parent">Window pass rate</th><th>Status</th></tr></thead><tbody>{candidates.map((candidate) => { const metrics = candidate.candidate_metrics; return <tr key={candidate.run_id} className={selected?.run_id === candidate.run_id ? "selected-row" : ""} onClick={() => void openCandidate(candidate)}><td><button type="button" className="text-button">{candidate.run_id}</button></td><td className="changes-cell">{changes(candidate).map((change) => `${humanCode(String(change.parameter))}: ${valueText(change.previous_value)} → ${valueText(change.proposed_value)}`).join("; ") || "—"}</td><td>{metric(metrics, "sharpe_ratio")?.toFixed(3) ?? "—"}</td><td>{percent(metric(metrics, "total_return"))}</td><td>{percent(metric(metrics, "maximum_drawdown"))}</td><td>{number(metric(metrics, "trades_per_year"))}</td><td>{number(metric(metrics, "average_holding_period_bars"))} bars</td><td>{number(metric(metrics, "turnover"))}</td><td>{percent(candidate.window_pass_rate, 0)}</td><td><span className={`status-chip ${tone(candidate.status)}`}>{candidateStatus(candidate)}</span></td></tr>; })}</tbody></table></div></section>

    <section className="terminal-panel learning-timeline"><div className="terminal-panel-head"><div><span className="terminal-overline">Immutable research history</span><h2>Learning timeline</h2></div><span className="terminal-meta">Rejected evidence remains visible</span></div><div className="learning-lineage">{versions.map((version, index) => <div className="learning-version" key={version.version_id}>{index > 0 && <i>→</i>}<article className={tone(version.status)}><span>{version.status === "BASELINE" ? "PARENT" : "VERSION"}</span><strong>{version.version_id}</strong><small>{version.status}</small></article></div>)}{improvements.map((candidate) => <div className="learning-candidate" key={candidate.run_id}><i>→</i><button type="button" className={tone(candidate.status)} onClick={() => void openCandidate(candidate)}><span>CANDIDATE</span><strong>{candidate.run_id}</strong><small>{candidateStatus(candidate)}</small></button></div>)}<div className="learning-future"><i>→</i><article><span>FUTURE</span><strong>Next qualifying version</strong><small>Created only after every gate passes</small></article></div></div></section>
    <CandidateDrawer candidate={drawerCandidate} detail={detail} status={drawerStatus} error={drawerError} onClose={() => { setDrawerCandidate(null); setDrawerStatus("idle"); }}/>
  </div>;
}
