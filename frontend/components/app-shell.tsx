"use client";

import Link from "next/link";
import { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { GlobalStatus } from "@/components/global-status";

const navigation = [
  ["Dashboard", "/"], ["Data", "/data"], ["Experiments", "/experiments"], ["Agents", "/agents"], ["Market Regimes", "/regimes"],
  ["Self-Improvement", "/improvements"], ["Validation", "/validation"], ["Reports", "/reports"], ["System", "/system"],
];

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  return <div className="app-shell"><aside><Link className="brand" href="/"><span>FIN</span>AGENT<small>V1.0.0 · Historical Research</small></Link><nav aria-label="Primary navigation">{navigation.map(([label, href]) => <Link className={pathname === href || (href !== "/" && pathname.startsWith(href)) ? "active" : ""} href={href} key={href}>{label}</Link>)}</nav><div className="sidebar-note">Historical research only<br />No live or paper trading</div></aside><main><GlobalStatus />{children}</main></div>;
}
