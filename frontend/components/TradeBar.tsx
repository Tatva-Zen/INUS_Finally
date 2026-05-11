'use client';
import { useState } from 'react';
import { Market } from '@/lib/types';
import { executeTrade } from '@/lib/api';

interface Props {
  activeMarket: Market;
  onTradeComplete: () => void;
}

/** Resolve a ticker to its canonical form for the given market.
 *  India market: bare names (BEL) are tried as BEL.NS first.
 *  US market: reject any .NS/.BO suffix.
 *  Returns null if the ticker is clearly for the wrong market.
 */
function resolveTickerForMarket(raw: string, market: Market): { ticker: string } | { error: string } {
  const t = raw.trim().toUpperCase();
  const isIndian = t.endsWith('.NS') || t.endsWith('.BO');

  if (market === 'us') {
    if (isIndian) return { error: `${t} is an India ticker — switch to India to trade it` };
    return { ticker: t };
  }

  // India market: accept .NS/.BO as-is; auto-append .NS for bare names
  if (isIndian) return { ticker: t };
  return { ticker: `${t}.NS` };  // backend will reject if it doesn't exist
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

  const doTrade = async (side: 'buy' | 'sell') => {
    const raw = ticker.trim().toUpperCase();
    if (!raw) { setError('Enter a ticker'); return; }
    const qty = parseFloat(quantity);
    if (!qty || qty <= 0) { setError('Enter a valid quantity'); return; }

    const resolved = resolveTickerForMarket(raw, activeMarket);
    if ('error' in resolved) { setError(resolved.error); return; }

    setError('');
    setLoading(true);
    try {
      await executeTrade(activeMarket, resolved.ticker, side, qty);
      showToast(`${side === 'buy' ? 'Bought' : 'Sold'} ${qty} ${resolved.ticker}`);
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
