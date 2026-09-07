"use client";

import { useEffect, useRef } from "react";
import { ColorType, createChart, type IChartApi, type Time } from "lightweight-charts";
import type { AgentDecision, OhlcvRow, Trade } from "@/lib/api";

type Props = {
  rows: OhlcvRow[]; trades: Trade[]; decisions?: AgentDecision[]; experimentId: string; strategy: string; highlightTimestamp?: string | null;
};

const regimeColor = "#efc66b";

export function MarketChart({ rows, trades, decisions = [], experimentId, strategy, highlightTimestamp }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!container.current || !rows.length) return;
    const chart = createChart(container.current, {
      autoSize: true, height: 440,
      layout: { background: { type: ColorType.Solid, color: "#0b1524" }, textColor: "#a7b7d0" },
      grid: { vertLines: { color: "#17273c" }, horzLines: { color: "#17273c" } },
      rightPriceScale: { borderColor: "#2b405f" }, timeScale: { borderColor: "#2b405f", timeVisible: false },
      crosshair: { vertLine: { color: "#7085a8", labelBackgroundColor: "#263b5a" }, horzLine: { color: "#7085a8", labelBackgroundColor: "#263b5a" } },
      handleScroll: true, handleScale: true,
    });
    chartRef.current = chart;
    const candles = chart.addCandlestickSeries({
      upColor: "#58d6aa", downColor: "#ff8490", borderVisible: false,
      wickUpColor: "#58d6aa", wickDownColor: "#ff8490", priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    candles.setData(rows.map((row) => ({ time: row.timestamp.slice(0, 10) as Time, open: row.open, high: row.high, low: row.low, close: row.close })));
    const volume = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "volume", color: "#5577aa77" });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volume.setData(rows.map((row) => ({ time: row.timestamp.slice(0, 10) as Time, value: row.volume, color: row.close >= row.open ? "#58d6aa55" : "#ff849055" })));
    candles.setMarkers(trades.map((trade) => {
      const decision = decisions.find((item) => item.timestamp.slice(0, 10) === trade.timestamp.slice(0, 10));
      const context = decision ? ` · ${(decision.proposal.confidence * 100).toFixed(0)}% · ${decision.risk.approved ? "risk approved" : "risk rejected"}` : "";
      return { time: trade.timestamp.slice(0, 10) as Time, position: trade.side === "BUY" ? "belowBar" : "aboveBar", color: trade.side === "BUY" ? "#58d6aa" : "#ff8490", shape: trade.side === "BUY" ? "arrowUp" : "arrowDown", text: `${trade.side} · ${strategy}${context}` };
    }));
    chart.timeScale().fitContent();
    if (highlightTimestamp) {
      const selected = rows.find((row) => row.timestamp.slice(0, 10) === highlightTimestamp.slice(0, 10));
      if (selected) {
        candles.createPriceLine({ price: selected.close, color: regimeColor, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "Selected event" });
        const index = rows.indexOf(selected);
        chart.timeScale().setVisibleRange({
          from: rows[Math.max(0, index - 18)].timestamp.slice(0, 10) as Time,
          to: rows[Math.min(rows.length - 1, index + 18)].timestamp.slice(0, 10) as Time,
        });
      }
    }
    return () => { chart.remove(); chartRef.current = null; };
  }, [rows, trades, strategy, highlightTimestamp]);

  if (!rows.length) return <p className="subtle">No persisted OHLCV rows are available for this experiment.</p>;
  const selected = highlightTimestamp ? trades.find((trade) => trade.timestamp.slice(0, 10) === highlightTimestamp.slice(0, 10)) : undefined;
  const selectedDecision = highlightTimestamp ? decisions.find((item) => item.timestamp.slice(0, 10) === highlightTimestamp.slice(0, 10)) : undefined;
  return <div className="market-chart-wrap"><div ref={container} className="market-chart" aria-label="Interactive historical candlestick chart" />
    <div className="chart-caption"><span>Candles · pan, zoom, crosshair, and volume are enabled.</span><span>{trades.length} persisted trade marker{trades.length === 1 ? "" : "s"}</span></div>
    {selected && <div className="selected-event"><strong>{selected.side}</strong> {selected.timestamp.slice(0, 10)} · {selected.price.toFixed(2)} · {strategy} · {experimentId}{selectedDecision ? ` · ${(selectedDecision.proposal.confidence * 100).toFixed(0)}% · risk ${selectedDecision.risk.approved ? "approved" : "rejected"}` : ""}</div>}
  </div>;
}
