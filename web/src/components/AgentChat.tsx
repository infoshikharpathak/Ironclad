import { useState, useRef, useEffect } from 'react';
import { agentChat, agentReset, type ChatResponse, type ToolCallInfo } from '../lib/api';
import { useBank } from '../context/BankContext';

interface Message {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  toolCalls?: ToolCallInfo[];
}

let msgId = 0;
let persistedMessages: Message[] = [];

export default function AgentChat({ compact = false }: { compact?: boolean }) {
  const { refreshAccounts } = useBank();
  const [messages, setMessages] = useState<Message[]>(persistedMessages);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    persistedMessages = messages;
  }, [messages]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: Message = { id: ++msgId, role: 'user', content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setLoading(true);

    try {
      const res: ChatResponse = await agentChat(text);
      const assistantMsg: Message = {
        id: ++msgId,
        role: 'assistant',
        content: res.reply,
        toolCalls: res.tool_calls,
      };
      setMessages((prev) => [...prev, assistantMsg]);
      if (res.tool_calls.some((tc) => tc.tool === 'initiate_transfer' && !tc.blocked)) {
        await refreshAccounts();
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: ++msgId, role: 'assistant', content: 'Something went wrong. Please try again.' },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const reset = async () => {
    await agentReset();
    persistedMessages = [];
    setMessages([]);
  };

  const suggestions = [
    'What are my account balances?',
    'Who can I send money to?',
    'Send $50 to Alice Johnson',
  ];

  return (
    <div className="flex flex-col h-full">
      {/* Header — only in full mode */}
      {!compact && (
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <span className="text-emerald-400 text-sm font-mono">AI</span>
            <span className="text-sm text-gray-300 font-medium">Banking Assistant</span>
            <span className="text-[10px] text-gray-600 font-mono bg-gray-800 px-1.5 py-0.5 rounded">
              anvil-governed
            </span>
          </div>
          <button
            onClick={reset}
            className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            Clear chat
          </button>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-4">
        {messages.length === 0 && (
          <div className={`text-center ${compact ? 'py-6' : 'py-12'}`}>
            <p className="text-gray-500 text-sm mb-3">
              {compact ? 'Ask me anything about your accounts.' : 'Ask me about your accounts, balances, or transfers.'}
            </p>
            <div className="flex flex-wrap justify-center gap-2">
              {suggestions.map((q) => (
                <button
                  key={q}
                  onClick={() => { setInput(q); }}
                  className="text-xs text-gray-400 border border-gray-700 rounded-lg px-3 py-1.5 hover:border-gray-600 hover:text-gray-300 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${
                msg.role === 'user'
                  ? 'bg-emerald-600/20 border border-emerald-700/30 text-gray-200'
                  : 'bg-gray-800 border border-gray-700 text-gray-300'
              }`}
            >
              <div className="whitespace-pre-wrap">{msg.content}</div>

              {/* Tool calls accordion */}
              {msg.toolCalls && msg.toolCalls.length > 0 && (
                <ToolCallDetails calls={msg.toolCalls} />
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-800 border border-gray-700 rounded-xl px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce [animation-delay:0ms]" />
                  <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce [animation-delay:150ms]" />
                  <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full animate-bounce [animation-delay:300ms]" />
                </div>
                <span className="text-xs text-gray-500">Thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="px-4 py-3 border-t border-gray-800">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && send()}
            placeholder="Ask the AI assistant..."
            disabled={loading}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500 transition-colors disabled:opacity-50"
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="px-4 py-2.5 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

function ToolCallDetails({ calls }: { calls: ToolCallInfo[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-2 pt-2 border-t border-gray-700/50">
      <button
        onClick={() => setOpen(!open)}
        className="text-[11px] text-gray-500 hover:text-gray-400 flex items-center gap-1"
      >
        <span className={`transition-transform ${open ? 'rotate-90' : ''}`}>▸</span>
        {calls.length} tool call{calls.length !== 1 ? 's' : ''}
        {calls.some((c) => c.blocked) && (
          <span className="text-amber-500 ml-1">⚠ blocked</span>
        )}
      </button>
      {open && (
        <div className="mt-1.5 space-y-1.5">
          {calls.map((tc, i) => (
            <div
              key={i}
              className={`text-[11px] font-mono rounded-md px-2 py-1.5 ${
                tc.blocked
                  ? 'bg-red-900/20 border border-red-800/30 text-red-300'
                  : 'bg-gray-900 border border-gray-700/50 text-gray-400'
              }`}
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className={tc.blocked ? 'text-red-400' : 'text-emerald-400'}>
                  {tc.blocked ? '✗' : '✓'}
                </span>
                <span className="text-gray-300">{tc.tool}</span>
              </div>
              {Object.keys(tc.input).length > 0 && (
                <div className="text-gray-500 truncate">
                  {JSON.stringify(tc.input)}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
