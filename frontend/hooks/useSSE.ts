'use client';
import { useEffect, useRef, useState } from 'react';
import { PriceTick, ConnectionStatus } from '../lib/types';

export interface FlashState {
  direction: 'up' | 'down';
  at: number; // timestamp for expiry
}

export function useSSE() {
  const [prices, setPrices] = useState<Map<string, PriceTick>>(new Map());
  const [flashes, setFlashes] = useState<Map<string, FlashState>>(new Map());
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    function connect() {
      setStatus('connecting');
      const es = new EventSource('/api/stream/prices');
      esRef.current = es;

      es.onopen = () => setStatus('connected');
      es.onerror = () => {
        setStatus('disconnected');
        // EventSource auto-reconnects; update status to reconnecting after a tick
        setTimeout(() => setStatus('connecting'), 100);
      };
      es.onmessage = (event) => {
        try {
          const tick: PriceTick = JSON.parse(event.data);
          setStatus('connected');
          setPrices(prev => {
            const next = new Map(prev);
            next.set(tick.ticker, tick);
            return next;
          });
          if (tick.change_direction !== 'flat' && !tick.stale) {
            setFlashes(prev => {
              const next = new Map(prev);
              next.set(tick.ticker, { direction: tick.change_direction as 'up' | 'down', at: Date.now() });
              return next;
            });
            // Clear flash after 600ms
            setTimeout(() => {
              setFlashes(prev => {
                const next = new Map(prev);
                next.delete(tick.ticker);
                return next;
              });
            }, 600);
          }
        } catch { /* ignore parse errors */ }
      };
      return es;
    }

    const es = connect();
    return () => { es.close(); };
  }, []);

  return { prices, flashes, status };
}
