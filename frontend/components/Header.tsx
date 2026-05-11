'use client';
import { Market, Portfolio, PriceTick, ConnectionStatus } from '@/lib/types';
import { formatCurrency } from '@/lib/format';

interface Props {
  activeMarket: Market;
  onMarketChange: (m: Market) => void;
  usPortfolio: Portfolio | null;
  inPortfolio: Portfolio | null;
  prices: Map<string, PriceTick>;
  connectionStatus: ConnectionStatus;
  onChatToggle: () => void;
}

function WalletCard({ portfolio, active, prices }: {
  portfolio: Portfolio | null;
  active: boolean;
  prices: Map<string, PriceTick>;
}) {
  const market = portfolio?.market ?? 'us';
  const cash = portfolio?.cash_balance ?? 0;
  const positions = portfolio?.positions ?? [];
  // Compute total value = cash + mark-to-market positions
  const posValue = positions.reduce((sum, p) => {
    const tick = prices.get(p.ticker);
    return sum + p.quantity * (tick?.price ?? p.avg_cost);
  }, 0);
  const totalValue = cash + posValue;
  const costBasis = positions.reduce((sum, p) => sum + p.quantity * p.avg_cost, 0);
  const pnl = posValue - costBasis;

  return (
    <div className={`px-4 py-2 rounded border ${active ? 'border-[#209dd7] bg-[#1a1a2e]' : 'border-[#21262d] bg-[#0d1117] opacity-70'}`}>
      <div className="text-xs text-gray-400 mb-1">{market === 'us' ? 'US Portfolio' : 'India Portfolio'}</div>
      <div className="font-mono text-sm font-semibold">{formatCurrency(totalValue, market)}</div>
      <div className="text-xs text-gray-400">Cash: {formatCurrency(cash, market)}</div>
      <div className={`text-xs font-mono ${pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
        P&amp;L: {pnl >= 0 ? '+' : ''}{formatCurrency(pnl, market)}
      </div>
    </div>
  );
}

const dotColor: Record<ConnectionStatus, string> = {
  connected: 'bg-green-400',
  connecting: 'bg-yellow-400',
  disconnected: 'bg-red-500',
};

export default function Header({ activeMarket, onMarketChange, usPortfolio, inPortfolio, prices, connectionStatus, onChatToggle }: Props) {
  return (
    <header className="flex items-center gap-4 px-4 py-2 border-b border-[#21262d] bg-[#0d1117] flex-shrink-0">
      {/* Logo */}
      <span className="text-xl font-bold text-[#ecad0a] font-mono tracking-tight">FinAlly</span>

      {/* Market toggle */}
      <div className="flex rounded overflow-hidden border border-[#21262d]">
        {(['us', 'in'] as Market[]).map(m => (
          <button
            key={m}
            onClick={() => onMarketChange(m)}
            className={`px-3 py-1 text-sm font-medium transition-colors ${
              activeMarket === m ? 'bg-[#209dd7] text-white' : 'bg-[#1a1a2e] text-gray-400 hover:text-white'
            }`}
          >
            {m === 'us' ? 'US' : 'India'}
          </button>
        ))}
      </div>

      {/* Wallet cards */}
      <div className="flex gap-3 flex-1">
        <WalletCard portfolio={usPortfolio} active={activeMarket === 'us'} prices={prices} />
        <WalletCard portfolio={inPortfolio} active={activeMarket === 'in'} prices={prices} />
      </div>

      {/* Connection dot */}
      <div className="flex items-center gap-2">
        <div className={`w-2.5 h-2.5 rounded-full ${dotColor[connectionStatus]}`} title={connectionStatus} />
        <span className="text-xs text-gray-500 capitalize">{connectionStatus}</span>
      </div>

      {/* Chat toggle */}
      <button onClick={onChatToggle} className="text-gray-400 hover:text-white p-1 rounded border border-[#21262d]">
        AI
      </button>
    </header>
  );
}
