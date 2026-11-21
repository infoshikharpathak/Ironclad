import { useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useBank } from '../context/BankContext';
import ChatBubble from './ChatBubble';
import TracesSidebar from './TracesSidebar';

function NavLink({ to, children }: { to: string; children: ReactNode }) {
  const { pathname } = useLocation();
  const active = pathname === to;
  return (
    <Link
      to={to}
      className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
        active
          ? 'bg-gray-800 text-white'
          : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
      }`}
    >
      {children}
    </Link>
  );
}

export default function Layout({ children }: { children: ReactNode }) {
  const { toasts, removeToast } = useBank();
  const [tracesOpen, setTracesOpen] = useState(false);

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="border-b border-gray-800 bg-gray-950/80 backdrop-blur-sm sticky top-0 z-30">
        <div className={`mx-auto px-4 sm:px-6 h-14 flex items-center gap-6 transition-all duration-300 ${tracesOpen ? 'max-w-3xl mr-auto ml-0 sm:ml-6' : 'max-w-5xl'}`}>
          <Link to="/" className="text-lg font-bold tracking-tight text-white">
            <span className="text-emerald-400">⬡</span> Ironclad
          </Link>
          <div className="flex items-center gap-1 ml-4">
            <NavLink to="/">Dashboard</NavLink>
          </div>

          <div className="ml-auto flex items-center gap-3">
            {/* Traces toggle */}
            <button
              onClick={() => setTracesOpen(!tracesOpen)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                tracesOpen
                  ? 'bg-emerald-900/40 text-emerald-300 border border-emerald-700/50'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800/50'
              }`}
            >
              <span className="text-xs">⛊</span>
              Traces
            </button>
            <span className="text-xs text-gray-500 font-mono">demo_user</span>
          </div>
        </div>
      </nav>

      {/* Content — shifts left when traces open, click to close */}
      <div
        className={`flex-1 transition-all duration-300 ${tracesOpen ? 'sm:mr-[480px]' : ''}`}
        onClick={tracesOpen ? () => setTracesOpen(false) : undefined}
      >
        <main className={`mx-auto w-full px-4 sm:px-6 py-8 transition-all duration-300 ${tracesOpen ? 'max-w-3xl mr-auto ml-0 sm:ml-6 cursor-pointer' : 'max-w-5xl'}`}>
          {children}
        </main>
      </div>

      {/* Traces sidebar */}
      <TracesSidebar open={tracesOpen} onClose={() => setTracesOpen(false)} />

      {/* Chat bubble */}
      <ChatBubble />

      {/* Toasts */}
      <div className={`fixed bottom-20 z-50 flex flex-col gap-2 pointer-events-none transition-all duration-300 ${tracesOpen ? 'right-[500px]' : 'right-20'}`}>
        {toasts.map((t) => (
          <div
            key={t.id}
            role="alert"
            onClick={() => removeToast(t.id)}
            className={`pointer-events-auto cursor-pointer px-4 py-3 rounded-lg shadow-lg text-sm font-medium backdrop-blur-sm transition-all ${
              t.variant === 'success'
                ? 'bg-emerald-900/90 text-emerald-200 border border-emerald-700'
                : t.variant === 'error'
                  ? 'bg-red-900/90 text-red-200 border border-red-700'
                  : 'bg-gray-800/90 text-gray-200 border border-gray-700'
            }`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </div>
  );
}
