import { useState } from 'react';
import AgentChat from './AgentChat';

export default function ChatBubble() {
  const [open, setOpen] = useState(false);

  return (
    <>
      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-20 right-4 z-40 w-[380px] h-[520px] bg-gray-950 border border-gray-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in">
          {/* Close bar */}
          <div className="flex items-center justify-between px-4 py-2 border-b border-gray-800 bg-gray-950">
            <div className="flex items-center gap-2">
              <span className="text-emerald-400 text-sm font-mono">AI</span>
              <span className="text-xs text-gray-400 font-medium">Banking Assistant</span>
            </div>
            <button
              onClick={() => setOpen(false)}
              className="text-gray-500 hover:text-gray-300 text-lg leading-none transition-colors"
            >
              ×
            </button>
          </div>
          <div className="flex-1 overflow-hidden">
            <AgentChat compact />
          </div>
        </div>
      )}

      {/* Bubble button */}
      <button
        onClick={() => setOpen(!open)}
        className={`fixed bottom-4 right-4 z-40 w-12 h-12 rounded-full shadow-lg flex items-center justify-center transition-all ${
          open
            ? 'bg-gray-800 border border-gray-600 text-gray-400 hover:text-gray-200'
            : 'bg-emerald-600 text-white hover:bg-emerald-500 hover:scale-105'
        }`}
      >
        {open ? (
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 6L6 18M6 6l12 12" />
          </svg>
        ) : (
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" />
          </svg>
        )}
      </button>
    </>
  );
}
