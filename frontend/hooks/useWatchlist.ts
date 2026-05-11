'use client';
import { useCallback, useEffect, useState } from 'react';
import { fetchWatchlist, addToWatchlist as apiAdd, removeFromWatchlist as apiRemove } from '../lib/api';
import { WatchlistItem, Market } from '../lib/types';

export function useWatchlist(market: Market) {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchWatchlist(market);
      setItems(data);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [market]);

  useEffect(() => { setItems([]); setLoading(true); refresh(); }, [market, refresh]);

  const addTicker = async (ticker: string) => {
    const item = await apiAdd(market, ticker);
    setItems(prev => [...prev, item]);
    return item;
  };

  const removeTicker = async (ticker: string) => {
    await apiRemove(market, ticker);
    setItems(prev => prev.filter(i => i.ticker !== ticker));
  };

  return { items, loading, refresh, addTicker, removeTicker };
}
