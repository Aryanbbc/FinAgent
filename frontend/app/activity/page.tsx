import { ActivityLog } from "@/components/activity-log";

export default function ActivityPage() {
  return <><header className="page-head"><div><p className="eyebrow">Research Event Feed</p><h1>Activity</h1><p className="subtle">A structured timeline of historical research artifacts and simulated events.</p></div></header><ActivityLog/></>;
}
