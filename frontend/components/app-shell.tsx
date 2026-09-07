"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { GlobalStatus } from "@/components/global-status";

const navigation = [
  ["Dashboard", "/"], ["Data", "/data"], ["Experiments", "/experiments"], ["Agents", "/agents"], ["Market Regimes", "/regimes"],
  ["Self-Improvement", "/improvements"], ["Validation", "/validation"], ["Activity", "/activity"], ["Reports", "/reports"], ["System", "/system"],
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return <div className="app-shell"><aside className="terminal-sidebar"><Link className="brand" href="/"><span className="brand-mark">FA</span><span className="brand-name">FINAGENT</span><small>V1.0.0 · RESEARCH TERMINAL</small></Link><div className="sidebar-mode"><span className="status-dot"/> HISTORICAL SIMULATION ONLY</div><nav aria-label="Primary navigation">{navigation.map(([label, href], index) => <Link className={pathname === href || (href !== "/" && pathname.startsWith(href)) ? "active" : ""} href={href} key={href}><span className="nav-index">{String(index + 1).padStart(2, "0")}</span>{label}</Link>)}</nav><div className="sidebar-note"><span>RESEARCH ENVIRONMENT</span><strong>NO EXECUTION</strong><small>Deterministic historical evidence only.</small></div></aside><main className="workspace"><GlobalStatus /><div className="workspace-content">{children}</div></main></div>;
}
