import { dashboardContextUrl } from "@/lib/dashboard-context";
import { improvementContextUrl } from "@/lib/improvement-execution";

export function isSelectionAwareRoute(pathname: string) {
  return pathname === "/" || pathname === "/improvements";
}

/** Keep global asset/experiment controls on the active selection-aware route. */
export function globalSelectionUrl(pathname: string, currentSearch: string, asset: string, experimentId?: string) {
  return pathname === "/improvements"
    ? improvementContextUrl(currentSearch, asset, experimentId)
    : dashboardContextUrl(currentSearch, asset, experimentId);
}
