'use client';
import { useEffect, useRef } from 'react';
import { Market, PriceTick } from '@/lib/types';
import { createChart, LineSeries, IChartApi, ISeriesApi, LineData, Time } from 'lightweight-charts';

interface Props {
  ticker: string;
  prices: Map<string, PriceTick>;
  activeMarket: Market;
}

export default function MainChart({ ticker, prices, activeMarket }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Line'> | null>(null);
  const dataRef = useRef<LineData[]>([]);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height: containerRef.current.clientHeight,
      layout: { background: { color: '#1a1a2e' }, textColor: '#9ca3af' },
      grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
      rightPriceScale: { borderColor: '#21262d' },
      timeScale: { borderColor: '#21262d', timeVisible: true, secondsVisible: true },
    });
    const series = chart.addSeries(LineSeries, { color: '#209dd7', lineWidth: 2 });
    chartRef.current = chart;
    seriesRef.current = series;
    dataRef.current = [];

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth, height: containerRef.current.clientHeight });
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [ticker]);

  useEffect(() => {
    const tick = prices.get(ticker);
    if (!tick || !seriesRef.current) return;
    const time = Math.floor(new Date(tick.timestamp).getTime() / 1000) as Time;
    const point: LineData = { time, value: tick.price };
    // Avoid duplicate times
    const last = dataRef.current[dataRef.current.length - 1];
    if (last && last.time === time) {
      dataRef.current[dataRef.current.length - 1] = point;
    } else {
      dataRef.current.push(point);
    }
    // Keep last 500 points
    if (dataRef.current.length > 500) dataRef.current = dataRef.current.slice(-500);
    try { seriesRef.current.setData(dataRef.current); } catch { /* ignore errors */ }
  }, [ticker, prices]);

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-1.5 border-b border-[#21262d] text-xs font-semibold text-gray-300">
        {ticker} — Live Chart
      </div>
      <div ref={containerRef} className="flex-1" />
    </div>
  );
}
