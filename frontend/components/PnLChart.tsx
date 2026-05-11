'use client';
import { useEffect, useState } from 'react';
import { Market, SnapshotPoint } from '@/lib/types';
import { fetchPortfolioHistory } from '@/lib/api';
import { formatCurrency } from '@/lib/format';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export default function PnLChart({ activeMarket }: { activeMarket: Market }) {
  const [data, setData] = useState<SnapshotPoint[]>([]);

  useEffect(() => {
    fetchPortfolioHistory(activeMarket).then(setData).catch(console.error);
  }, [activeMarket]);

  const formatted = data.map(d => ({
    time: new Date(d.recorded_at).toLocaleTimeString(),
    value: d.total_value,
  }));

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-1.5 border-b border-[#21262d] text-xs font-semibold text-gray-300">
        Portfolio P&amp;L
      </div>
      <div className="flex-1 p-2">
        {formatted.length < 2 ? (
          <div className="h-full flex items-center justify-center text-gray-600 text-sm">Accumulating data&#8230;</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={formatted}>
              <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#9ca3af' }} interval="preserveStartEnd" />
              <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} tickFormatter={(v: number) => formatCurrency(v, activeMarket)} width={80} />
              <Tooltip
                contentStyle={{ background: '#1a1a2e', border: '1px solid #21262d', borderRadius: 4 }}
                formatter={(v) => [formatCurrency(Number(v), activeMarket), 'Portfolio']}
              />
              <Line type="monotone" dataKey="value" stroke="#209dd7" dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
