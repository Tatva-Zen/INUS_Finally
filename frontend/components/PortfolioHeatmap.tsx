'use client';
import { Market, Portfolio, PriceTick } from '@/lib/types';
import { Treemap, ResponsiveContainer } from 'recharts';

interface Props {
  activeMarket: Market;
  prices: Map<string, PriceTick>;
  portfolio: Portfolio | null;
}

interface HeatmapEntry {
  name: string;
  size: number;
  pnlPct: number;
  [key: string]: unknown;
}

interface ContentProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  name?: string;
  pnlPct?: number;
}

const CustomContent = (props: ContentProps) => {
  const { x = 0, y = 0, width = 0, height = 0, name, pnlPct } = props;
  if (width < 20 || height < 20) return null;
  const pnl = pnlPct ?? 0;
  const intensity = Math.min(Math.abs(pnl) / 10, 1);
  const isPositive = pnl >= 0;
  const color = isPositive
    ? `rgba(34, 197, 94, ${0.2 + intensity * 0.5})`
    : `rgba(239, 68, 68, ${0.2 + intensity * 0.5})`;
  const textColor = isPositive ? '#86efac' : '#fca5a5';
  return (
    <g>
      <rect x={x} y={y} width={width} height={height} fill={color} stroke="#21262d" strokeWidth={1} />
      {width > 40 && height > 25 && (
        <>
          <text x={x + width / 2} y={y + height / 2 - 5} textAnchor="middle" fill="white" fontSize={11} fontWeight="600">{name}</text>
          <text x={x + width / 2} y={y + height / 2 + 10} textAnchor="middle" fill={textColor} fontSize={10}>
            {pnl >= 0 ? '+' : ''}{pnl.toFixed(1)}%
          </text>
        </>
      )}
    </g>
  );
};

export default function PortfolioHeatmap({ activeMarket, prices, portfolio }: Props) {
  const positions = portfolio?.positions ?? [];

  const data: HeatmapEntry[] = positions.map(p => {
    const tick = prices.get(p.ticker);
    const currentPrice = tick?.price ?? p.avg_cost;
    const value = p.quantity * currentPrice;
    const pnlPct = p.avg_cost > 0 ? ((currentPrice - p.avg_cost) / p.avg_cost) * 100 : 0;
    return { name: p.ticker, size: value, pnlPct };
  });

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-1.5 border-b border-[#21262d] text-xs font-semibold text-gray-300">
        Portfolio Heatmap
      </div>
      <div className="flex-1 p-1">
        {data.length === 0 ? (
          <div className="h-full flex items-center justify-center text-gray-600 text-sm">No positions</div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <Treemap data={data} dataKey="size" content={<CustomContent />} />
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}
