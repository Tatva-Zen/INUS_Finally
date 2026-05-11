'use client';
import { useState, useEffect } from 'react';
import { Market } from '@/lib/types';
import { useSSE } from '@/hooks/useSSE';
import { usePortfolio } from '@/hooks/usePortfolio';
import Header from '@/components/Header';
import WatchlistPanel from '@/components/WatchlistPanel';
import MainChart from '@/components/MainChart';
import PortfolioHeatmap from '@/components/PortfolioHeatmap';
import PnLChart from '@/components/PnLChart';
import PositionsTable from '@/components/PositionsTable';
import TradeBar from '@/components/TradeBar';
import ChatPanel from '@/components/ChatPanel';

export default function TradingTerminal() {
  const [activeMarket, setActiveMarket] = useState<Market>('us');
  const [selectedTicker, setSelectedTicker] = useState<string>('AAPL');
  const [chatOpen, setChatOpen] = useState(true);

  // Load persisted market from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('finally_market') as Market | null;
    if (saved === 'us' || saved === 'in') setActiveMarket(saved);
  }, []);

  const handleMarketChange = (m: Market) => {
    setActiveMarket(m);
    localStorage.setItem('finally_market', m);
    setSelectedTicker(m === 'us' ? 'AAPL' : 'RELIANCE.NS');
  };

  const { prices, flashes, status } = useSSE();
  const usPortfolio = usePortfolio('us');
  const inPortfolio = usePortfolio('in');

  const handleTradeComplete = () => {
    usPortfolio.refresh();
    inPortfolio.refresh();
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <Header
        activeMarket={activeMarket}
        onMarketChange={handleMarketChange}
        usPortfolio={usPortfolio.portfolio}
        inPortfolio={inPortfolio.portfolio}
        prices={prices}
        connectionStatus={status}
        onChatToggle={() => setChatOpen(o => !o)}
      />

      <div className="flex flex-1 overflow-hidden">
        {/* Left: Watchlist */}
        <div className="w-64 flex-shrink-0 border-r border-[#21262d] overflow-y-auto">
          <WatchlistPanel
            activeMarket={activeMarket}
            prices={prices}
            flashes={flashes}
            selectedTicker={selectedTicker}
            onSelectTicker={setSelectedTicker}
          />
        </div>

        {/* Center: Charts + Positions + Trade */}
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex-1 grid grid-rows-2 gap-0 overflow-hidden">
            {/* Top row */}
            <div className="grid grid-cols-3 border-b border-[#21262d] overflow-hidden">
              <div className="col-span-2 border-r border-[#21262d]">
                <MainChart
                  ticker={selectedTicker}
                  prices={prices}
                  activeMarket={activeMarket}
                />
              </div>
              <div>
                <PortfolioHeatmap
                  activeMarket={activeMarket}
                  prices={prices}
                  portfolio={activeMarket === 'us' ? usPortfolio.portfolio : inPortfolio.portfolio}
                />
              </div>
            </div>
            {/* Bottom row */}
            <div className="grid grid-cols-2 overflow-hidden">
              <div className="border-r border-[#21262d] overflow-y-auto">
                <PositionsTable
                  activeMarket={activeMarket}
                  prices={prices}
                  portfolio={activeMarket === 'us' ? usPortfolio.portfolio : inPortfolio.portfolio}
                />
              </div>
              <div className="overflow-y-auto">
                <PnLChart activeMarket={activeMarket} />
              </div>
            </div>
          </div>

          {/* Trade Bar */}
          <TradeBar
            activeMarket={activeMarket}
            onTradeComplete={handleTradeComplete}
          />
        </div>

        {/* Right: Chat */}
        {chatOpen && (
          <div className="w-80 flex-shrink-0 border-l border-[#21262d]">
            <ChatPanel activeMarket={activeMarket} />
          </div>
        )}
      </div>
    </div>
  );
}
