"use client";

import { useEffect, useState } from "react";
import { api, type OhlcvSeries } from "@/lib/api";
import { MarketChart } from "@/components/market-chart";

export function DatasetMarketPanel({ datasetId }: { datasetId: string }) {
  const [series, setSeries] = useState<OhlcvSeries | null>(null); const [error, setError] = useState("");
  useEffect(() => { let active = true; api.datasetOhlcv(datasetId).then((result) => { if (active) setSeries(result); }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Dataset preview is unavailable."); }); return () => { active = false; }; }, [datasetId]);
  if (error) return <div className="request-state error"><span>Dataset preview unavailable</span><p>{error}</p></div>;
  if (!series) return <div className="skeleton-chart" aria-label="Loading historical price preview"/>;
  return <MarketChart rows={series.items} trades={[]} experimentId={datasetId} strategy="dataset preview"/>;
}
