"use client";

import Link from "next/link";
import { ReactNode, Suspense } from "react";
import { usePathname } from "next/navigation";
import { GlobalStatus } from "@/components/global-status";

const navigation = [
  ["Dashboard", "/"], ["Data", "/data"], ["Experiments", "/experiments"], ["Agents", "/agents"], ["Market Regimes", "/regimes"],
  ["Self-Improvement", "/improvements"], ["Validation", "/validation"], ["Live", "/live"], ["Activity", "/activity"], ["Reports", "/reports"], ["System", "/system"],
];

function GlobalStatusFallback() {
  return <section className="global-status" aria-busy="true"><div className="status-cluster"><strong className="topbar-brand">FINAGENT</strong><span className="status-divider"/><span>Loading workspace context…</span></div></section>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return <div className="app-shell"><aside className="terminal-sidebar"><Link className="brand" href="/"><span className="brand-mark">FA</span><span className="brand-name">FINAGENT</span><small>V1.1 · RESEARCH TERMINAL</small></Link><div className="sidebar-mode"><span className="status-dot"/> RESEARCH MONITORING · NO EXECUTION</div><nav aria-label="Primary navigation">{navigation.map(([label, href], index) => <Link className={pathname === href || (href !== "/" && pathname.startsWith(href)) ? "active" : ""} href={href} key={href}><span className="nav-index">{String(index + 1).padStart(2, "0")}</span>{label}</Link>)}</nav><div className="sidebar-note"><span>HISTORICAL + LIVE RESEARCH</span><strong>NO EXECUTION</strong><small>Live signals are monitoring evidence, never orders.</small></div></aside><main className="workspace"><Suspense fallback={<GlobalStatusFallback/>}><GlobalStatus /></Suspense><div className="workspace-content">{children}</div></main></div>;
}
