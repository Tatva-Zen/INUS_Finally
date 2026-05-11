'use client';
import { useState } from 'react';
import { Market } from '@/lib/types';
import { executeTrade } from '@/lib/api';

interface Props {
  activeMarket: Market;
  onTradeComplete: () => void;
}

function isValidTickerForMarket(ticker: string, market: Market): boolean {
  const isIndian = ticker.endsWith('.NS') || ticker.endsWith('.BO');
  if (market === 'us') return !isIndian;
  if (market === 'in') return isIndian;
  return false;
}

export default function TradeBar({ activeMarket, onTradeComplete }: Props) {
  const [ticker, setTicker] = useState('');
  const [quantity, setQuantity] = useState('');
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [loading, setLoading] = useState(false);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(''), 3000);
  };

  const validate = (): boolean => {
    const t = ticker.trim().toUpperCase();
    if (!t) { setError('Enter a ticker'); return false; }
    if (!isValidTickerForMarket(t, activeMarket)) {
      const other = activeMarket === 'us' ? 'India' : 'US';
      setError(`${t} is an ${other} ticker — switch to ${other} to trade it`);
      return false;
    }
    const qty = parseFloat(quantity);
    if (!qty || qty <= 0) { setError('Enter a valid quantity'); return false; }
    setError('');
    return true;
  };

  const doTrade = async (side: 'buy' | 'sell') => {
    if (!validate()) return;
    setLoading(true);
    try {
      await executeTrade(activeMarket, ticker.trim().toUpperCase(), side, parseFloat(quantity));
      showToast(`${side === 'buy' ? 'Bought' : 'Sold'} ${quantity} ${ticker.trim().toUpperCase()}`);
      setTicker('');
      setQuantity('');
      onTradeComplete();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="border-t border-[#21262d] bg-[#0d1117] px-4 py-2 flex items-center gap-3 flex-shrink-0">
      <span className="text-xs text-gray-500 uppercase tracking-wider">Trade</span>
      <input
        value={ticker}
        onChange={e => setTicker(e.target.value.toUpperCase())}
        onKeyDown={e => e.key === 'Enter' && doTrade('buy')}
        placeholder="Ticker"
        className="w-28 bg-[#1a1a2e] border border-[#21262d] rounded px-2 py-1.5 text-sm font-mono text-white placeholder-gray-600 focus:outline-none focus:border-[#209dd7]"
      />
      <input
        type="number"
        value={quantity}
        onChange={e => setQuantity(e.target.value)}
        placeholder="Qty"
        min="0.001"
        step="0.001"
        className="w-24 bg-[#1a1a2e] border border-[#21262d] rounded px-2 py-1.5 text-sm font-mono text-white placeholder-gray-600 focus:outline-none focus:border-[#209dd7]"
      />
      <button
        onClick={() => doTrade('buy')}
        disabled={loading}
        className="px-4 py-1.5 bg-[#209dd7] text-white text-sm font-semibold rounded hover:opacity-80 disabled:opacity-50"
      >Buy</button>
      <button
        onClick={() => doTrade('sell')}
        disabled={loading}
        className="px-4 py-1.5 bg-[#753991] text-white text-sm font-semibold rounded hover:opacity-80 disabled:opacity-50"
      >Sell</button>
      {error && <span className="text-red-400 text-xs">{error}</span>}
      {toast && <span className="text-green-400 text-xs">{toast}</span>}
    </div>
  );
}
