'use client';
import { useState, useEffect, useRef } from 'react';
import { Market, PriceTick } from '@/lib/types';
import { FlashState } from '@/hooks/useSSE';
import { useWatchlist } from '@/hooks/useWatchlist';
import { formatCurrency } from '@/lib/format';

interface Props {
  activeMarket: Market;
  prices: Map<string, PriceTick>;
  flashes: Map<string, FlashState>;
  selectedTicker: string;
  onSelectTicker: (t: string) => void;
}

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return <span className="text-xs text-gray-600">&#8211;</span>;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const w = 60, h = 20;
  const pts = data.map((v, i) =>
    `${(i / (data.length - 1)) * w},${h - ((v - min) / range) * h}`
  ).join(' ');
  const color = data[data.length - 1] >= data[0] ? '#22c55e' : '#ef4444';
  return (
    <svg width={w} height={h} className="overflow-visible">
      <polyline fill="none" stroke={color} strokeWidth="1.5" points={pts} />
    </svg>
  );
}

export default function WatchlistPanel({ activeMarket, prices, flashes, selectedTicker, onSelectTicker }: Props) {
  const { items, addTicker, removeTicker } = useWatchlist(activeMarket);
  const [addInput, setAddInput] = useState('');
  const [addError, setAddError] = useState('');
  const priceHistory = useRef<Map<string, number[]>>(new Map());
  const firstPrices = useRef<Map<string, number>>(new Map());

  // Accumulate sparkline data
  useEffect(() => {
    for (const item of items) {
      const tick = prices.get(item.ticker);
      if (!tick || tick.market !== activeMarket) continue;
      if (!firstPrices.current.has(item.ticker)) {
        firstPrices.current.set(item.ticker, tick.price);
      }
      const hist = priceHistory.current.get(item.ticker) || [];
      hist.push(tick.price);
      if (hist.length > 60) hist.shift();
      priceHistory.current.set(item.ticker, hist);
    }
  }, [prices, items, activeMarket]);

  const handleAdd = async () => {
    const ticker = addInput.trim().toUpperCase();
    if (!ticker) return;
    try {
      setAddError('');
      await addTicker(ticker);
      setAddInput('');
    } catch (e: any) {
      setAddError(e.message);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-2 border-b border-[#21262d]">
        <div className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          {activeMarket === 'us' ? 'US Watchlist' : 'India Watchlist'}
        </div>
        <div className="flex gap-1">
          <input
            value={addInput}
            onChange={e => setAddInput(e.target.value.toUpperCase())}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            placeholder="Add ticker..."
            className="flex-1 bg-[#1a1a2e] border border-[#21262d] rounded px-2 py-1 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-[#209dd7]"
          />
          <button onClick={handleAdd} className="bg-[#209dd7] text-white px-2 py-1 rounded text-xs hover:opacity-80">+</button>
        </div>
        {addError && <p className="text-red-400 text-xs mt-1">{addError}</p>}
      </div>

      <div className="flex-1 overflow-y-auto">
        {items.map(item => {
          const tick = prices.get(item.ticker);
          const flash = flashes.get(item.ticker);
          const firstPrice = firstPrices.current.get(item.ticker);
          const sparkData = priceHistory.current.get(item.ticker) || [];
          const pct = tick && firstPrice ? ((tick.price - firstPrice) / firstPrice) * 100 : 0;
          const isSelected = item.ticker === selectedTicker;

          return (
            <div
              key={item.ticker}
              onClick={() => onSelectTicker(item.ticker)}
              className={`flex items-center gap-2 px-2 py-2 cursor-pointer border-b border-[#21262d] group
                ${flash ? (flash.direction === 'up' ? 'flash-up' : 'flash-down') : ''}
                ${isSelected ? 'bg-[#1a1a2e] border-l-2 border-l-[#209dd7]' : 'hover:bg-[#1a1a2e]'}`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-white">{item.ticker}</span>
                  <button
                    onClick={e => { e.stopPropagation(); removeTicker(item.ticker); }}
                    className="opacity-0 group-hover:opacity-100 text-gray-500 hover:text-red-400 text-xs"
                  >x</button>
                </div>
                <div className="flex items-center gap-2 mt-0.5">
                  <span className={`font-mono text-xs ${tick?.stale ? 'opacity-50' : ''} ${tick?.change_direction === 'up' ? 'text-green-400' : tick?.change_direction === 'down' ? 'text-red-400' : 'text-white'}`}>
                    {tick ? `${tick.stale ? '~' : ''}${formatCurrency(tick.price, activeMarket)}` : '—'}
                  </span>
                  {firstPrice && (
                    <span className={`text-xs ${pct >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                    </span>
                  )}
                </div>
              </div>
              <Sparkline data={sparkData} />
            </div>
          );
        })}
      </div>
    </div>
  );
}
