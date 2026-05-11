'use client';
import { Market, Portfolio, PriceTick } from '@/lib/types';
import { formatCurrency, formatPct } from '@/lib/format';

interface Props {
  activeMarket: Market;
  prices: Map<string, PriceTick>;
  portfolio: Portfolio | null;
}

export default function PositionsTable({ activeMarket, prices, portfolio }: Props) {
  const positions = portfolio?.positions ?? [];

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-1.5 border-b border-[#21262d] text-xs font-semibold text-gray-300">Positions</div>
      {positions.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-sm">No positions</div>
      ) : (
        <div className="flex-1 overflow-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-[#0d1117]">
              <tr className="text-gray-500 border-b border-[#21262d]">
                <th className="text-left px-3 py-1.5">Ticker</th>
                <th className="text-right px-2 py-1.5">Qty</th>
                <th className="text-right px-2 py-1.5">Avg Cost</th>
                <th className="text-right px-2 py-1.5">Price</th>
                <th className="text-right px-2 py-1.5">P&amp;L</th>
                <th className="text-right px-3 py-1.5">%</th>
              </tr>
            </thead>
            <tbody>
              {positions.map(p => {
                const tick = prices.get(p.ticker);
                const currentPrice = tick?.price ?? p.avg_cost;
                const pnl = p.quantity * (currentPrice - p.avg_cost);
                const pnlPct = p.avg_cost > 0 ? ((currentPrice - p.avg_cost) / p.avg_cost) * 100 : 0;
                const pnlColor = pnl >= 0 ? 'text-green-400' : 'text-red-400';
                return (
                  <tr key={p.ticker} className="border-b border-[#21262d] hover:bg-[#1a1a2e]">
                    <td className="px-3 py-1.5 font-semibold">{p.ticker}</td>
                    <td className="text-right px-2 py-1.5 font-mono">{p.quantity}</td>
                    <td className="text-right px-2 py-1.5 font-mono">{formatCurrency(p.avg_cost, activeMarket)}</td>
                    <td className="text-right px-2 py-1.5 font-mono">{tick ? formatCurrency(currentPrice, activeMarket) : '—'}</td>
                    <td className={`text-right px-2 py-1.5 font-mono ${pnlColor}`}>{pnl >= 0 ? '+' : ''}{formatCurrency(pnl, activeMarket)}</td>
                    <td className={`text-right px-3 py-1.5 ${pnlColor}`}>{formatPct(pnlPct)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
