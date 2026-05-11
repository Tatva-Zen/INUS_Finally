'use client';
import { useCallback, useEffect, useState } from 'react';
import { fetchPortfolio } from '../lib/api';
import { Portfolio, Market } from '../lib/types';

export function usePortfolio(market: Market) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchPortfolio(market);
      setPortfolio(data);
    } catch (e) {
      console.error('Portfolio fetch error:', e);
    } finally {
      setLoading(false);
    }
  }, [market]);

  useEffect(() => {
    setLoading(true);
    refresh();
  }, [market, refresh]);

  return { portfolio, loading, refresh };
}
