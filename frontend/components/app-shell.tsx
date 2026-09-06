import Link from "next/link";
import { ReactNode } from "react";

const navigation = [
  ["Dashboard", "/"], ["Data", "/data"], ["Experiments", "/experiments"], ["Agents", "/agents"], ["Market Regimes", "/regimes"],
  ["Self-Improvement", "/improvements"], ["Validation", "/validation"], ["Reports", "/reports"], ["System", "/system"],
];

export function AppShell({ children }: { children: ReactNode }) {
  return <div className="app-shell"><aside><Link className="brand" href="/"><span>FIN</span>AGENT<small>V0.8 · Local Research</small></Link><nav>{navigation.map(([label, href]) => <Link href={href} key={href}>{label}</Link>)}</nav><div className="sidebar-note">Historical research only<br />No live or paper trading</div></aside><main>{children}</main></div>;
}
