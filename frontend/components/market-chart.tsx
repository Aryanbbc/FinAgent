"use client";

import { useEffect, useRef, useState } from "react";
import { ColorType, createChart, type IChartApi, type Time } from "lightweight-charts";
import type { AgentDecision, LiveSignal, OhlcvRow, Trade } from "@/lib/api";

type Props = {
  rows: OhlcvRow[]; trades?: Trade[]; signals?: LiveSignal[]; decisions?: AgentDecision[]; experimentId?: string; strategy?: string; highlightTimestamp?: string | null; live?: boolean;
};

const regimeColor = "#efc66b";

function chartTime(timestamp: string, live: boolean): Time { return (live ? Math.floor(Date.parse(timestamp) / 1000) : timestamp.slice(0, 10)) as Time; }
function chartKey(timestamp: string, live: boolean) { return String(chartTime(timestamp, live)); }

export function MarketChart({ rows, trades = [], signals = [], decisions = [], experimentId = "", strategy = "research", highlightTimestamp, live = false }: Props) {
  const container = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const [hovered, setHovered] = useState<OhlcvRow | null>(null);

  useEffect(() => {
    if (!container.current || !rows.length) return;
    const chart = createChart(container.current, {
      autoSize: true, height: 440,
      layout: { background: { type: ColorType.Solid, color: "#0b1524" }, textColor: "#a7b7d0" },
      grid: { vertLines: { color: "#17273c" }, horzLines: { color: "#17273c" } },
      rightPriceScale: { borderColor: "#2b405f" }, timeScale: { borderColor: "#2b405f", timeVisible: live, secondsVisible: live },
      crosshair: { vertLine: { color: "#7085a8", labelBackgroundColor: "#263b5a" }, horzLine: { color: "#7085a8", labelBackgroundColor: "#263b5a" } },
      handleScroll: true, handleScale: true,
    });
    chartRef.current = chart;
    const candles = chart.addCandlestickSeries({
      upColor: "#58d6aa", downColor: "#ff8490", borderVisible: false,
      wickUpColor: "#58d6aa", wickDownColor: "#ff8490", priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    candles.setData(rows.map((row) => ({ time: chartTime(row.timestamp, live), open: row.open, high: row.high, low: row.low, close: row.close })));
    const volume = chart.addHistogramSeries({ priceFormat: { type: "volume" }, priceScaleId: "volume", color: "#5577aa77" });
    volume.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    volume.setData(rows.map((row) => ({ time: chartTime(row.timestamp, live), value: row.volume, color: row.close >= row.open ? "#58d6aa55" : "#ff849055" })));
    const tradeMarkers = trades.map((trade) => {
      const decision = decisions.find((item) => item.timestamp.slice(0, 10) === trade.timestamp.slice(0, 10));
      const context = decision ? ` · ${(decision.proposal.confidence * 100).toFixed(0)}% · ${decision.risk.approved ? "risk approved" : "risk rejected"}` : "";
      const exit = trade.side === "EXIT";
      return { time: chartTime(trade.timestamp, live), position: trade.side === "BUY" ? "belowBar" as const : "aboveBar" as const, color: trade.side === "BUY" ? "#58d6aa" : exit ? "#efc66b" : "#ff8490", shape: trade.side === "BUY" ? "arrowUp" as const : "arrowDown" as const, text: `${trade.side} · ${strategy}${context}` };
    });
    const liveMarkers = signals.map((signal) => ({
      time: chartTime(signal.timestamp, live),
      position: signal.action === "BUY" ? "belowBar" as const : "aboveBar" as const,
      color: signal.action === "BUY" ? "#58d6aa" : signal.action === "EXIT" ? "#efc66b" : "#6e829f",
      shape: signal.action === "BUY" ? "arrowUp" as const : "circle" as const,
      text: `${signal.action} · ${signal.strategy.selected_strategy} · risk ${signal.risk.approved ? "approved" : "rejected"}`,
    }));
    candles.setMarkers([...tradeMarkers, ...liveMarkers]);
    if (live && rows.at(-1)) candles.createPriceLine({ price: rows.at(-1)!.close, color: "#53bfd0", lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "Latest" });
    const rowsByTime = new Map(rows.map((row) => [chartKey(row.timestamp, live), row]));
    chart.subscribeCrosshairMove((event) => {
      const time = event.time;
      const key = typeof time === "string" || typeof time === "number" ? String(time) : typeof time === "object" && time && "year" in time ? `${time.year}-${String(time.month).padStart(2, "0")}-${String(time.day).padStart(2, "0")}` : "";
      setHovered(rowsByTime.get(key) ?? null);
    });
    chart.timeScale().fitContent();
    if (highlightTimestamp) {
      const selected = rows.find((row) => row.timestamp.slice(0, 10) === highlightTimestamp.slice(0, 10));
      if (selected) {
        candles.createPriceLine({ price: selected.close, color: regimeColor, lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: "Selected event" });
        const index = rows.indexOf(selected);
        chart.timeScale().setVisibleRange({
          from: chartTime(rows[Math.max(0, index - 18)].timestamp, live),
          to: chartTime(rows[Math.min(rows.length - 1, index + 18)].timestamp, live),
        });
      }
    }
    return () => { chart.remove(); chartRef.current = null; };
  }, [rows, trades, signals, strategy, highlightTimestamp, live]);

  if (!rows.length) return <p className="subtle">{live ? "No recent live OHLCV bars are buffered yet." : "No persisted OHLCV rows are available for this experiment."}</p>;
  const selected = highlightTimestamp ? trades.find((trade) => trade.timestamp.slice(0, 10) === highlightTimestamp.slice(0, 10)) : undefined;
  const selectedDecision = highlightTimestamp ? decisions.find((item) => item.timestamp.slice(0, 10) === highlightTimestamp.slice(0, 10)) : undefined;
  const displayed = hovered ?? rows.at(-1);
  return <div className="market-chart-wrap"><div ref={container} className="market-chart" aria-label={live ? "Interactive live market candlestick chart" : "Interactive historical candlestick chart"} />
    <div className="chart-caption terminal-chart-caption"><span>Candles · pan, zoom, crosshair, and volume are enabled.</span>{displayed && <span>O {displayed.open.toFixed(2)} · H {displayed.high.toFixed(2)} · L {displayed.low.toFixed(2)} · C <strong>{displayed.close.toFixed(2)}</strong></span>}<span>Last {rows.at(-1)?.close.toFixed(2) ?? "—"} · {trades.length + signals.length} marker{trades.length + signals.length === 1 ? "" : "s"}</span></div>
    {selected && <div className="selected-event"><strong>{selected.side}</strong> {selected.timestamp.slice(0, 10)} · {selected.price.toFixed(2)} · {strategy} · {experimentId}{selectedDecision ? ` · ${(selectedDecision.proposal.confidence * 100).toFixed(0)}% · risk ${selectedDecision.risk.approved ? "approved" : "rejected"}` : ""}</div>}
  </div>;
}
