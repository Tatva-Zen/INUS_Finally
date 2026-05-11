'use client';
import { useRef, useEffect, useState } from 'react';
import { Market } from '@/lib/types';
import { useChatHistory } from '@/hooks/useChatHistory';

export default function ChatPanel({ activeMarket }: { activeMarket: Market }) {
  const { messages, sending, send } = useChatHistory(activeMarket);
  const [input, setInput] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput('');
    send(text);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-1.5 border-b border-[#21262d] text-xs font-semibold text-gray-300 flex items-center gap-2">
        <span>AI Assistant</span>
        <span className="text-[#ecad0a] text-xs">{activeMarket === 'us' ? 'US' : 'India'}</span>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {messages.length === 0 && (
          <p className="text-gray-600 text-xs text-center mt-4">Ask me to analyze your portfolio, execute trades, or manage your watchlist.</p>
        )}
        {messages.map(msg => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] rounded px-2.5 py-1.5 text-xs ${
              msg.role === 'user'
                ? 'bg-[#209dd7] text-white'
                : 'bg-[#1a1a2e] border border-[#21262d] text-gray-200'
            }`}>
              <p className="whitespace-pre-wrap">{msg.content}</p>
              {msg.actions && Array.isArray(msg.actions?.trades) && msg.actions.trades.length > 0 && (
                <div className="mt-1 pt-1 border-t border-[#30363d] text-[10px] text-green-400">
                  Executed: {msg.actions.trades.map((t: any) => `${t.side} ${t.quantity} ${t.ticker}`).join(', ')}
                </div>
              )}
            </div>
          </div>
        ))}
        {sending && (
          <div className="flex justify-start">
            <div className="bg-[#1a1a2e] border border-[#21262d] rounded px-3 py-2 text-xs text-gray-400">
              <span className="animate-pulse">Thinking&#8230;</span>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="border-t border-[#21262d] p-2 flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
          placeholder="Ask FinAlly anything..."
          disabled={sending}
          className="flex-1 bg-[#1a1a2e] border border-[#21262d] rounded px-2 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-[#753991] disabled:opacity-50"
        />
        <button
          onClick={handleSend}
          disabled={sending || !input.trim()}
          className="bg-[#753991] text-white px-3 py-1.5 rounded text-xs font-semibold hover:opacity-80 disabled:opacity-50"
        >Send</button>
      </div>
    </div>
  );
}
