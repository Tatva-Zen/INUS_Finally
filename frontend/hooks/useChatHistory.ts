'use client';
import { useCallback, useEffect, useState } from 'react';
import { fetchChatHistory, sendChatMessage as apiSend } from '../lib/api';
import { ChatMessage, Market } from '../lib/types';

export function useChatHistory(market: Market) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const data = await fetchChatHistory(market);
      setMessages(data);
    } catch (e) { console.error(e); }
  }, [market]);

  useEffect(() => { setMessages([]); refresh(); }, [market, refresh]);

  const send = async (text: string): Promise<void> => {
    setSending(true);
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
      market,
    };
    setMessages(prev => [...prev, userMsg]);
    try {
      await apiSend(market, text);
      await refresh();
    } catch (e: any) {
      console.error(e);
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: `Error: ${e.message}`,
        created_at: new Date().toISOString(),
        market,
      }]);
    } finally {
      setSending(false);
    }
  };

  return { messages, sending, send, refresh };
}
