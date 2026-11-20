import type { ReactNode } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { useBank } from '../context/BankContext';

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

  return (
    <div className="min-h-screen flex flex-col">
      {/* Nav */}
      <nav className="border-b border-gray-800 bg-gray-950/80 backdrop-blur-sm sticky top-0 z-30">
        <div className="max-w-5xl mx-auto px-4 sm:px-6 h-14 flex items-center gap-6">
          <Link to="/" className="text-lg font-bold tracking-tight text-white">
            <span className="text-emerald-400">⬡</span> Irodclad
          </Link>
          <div className="flex items-center gap-1 ml-4">
            <NavLink to="/">Dashboard</NavLink>
            <NavLink to="/transfer">Transfer</NavLink>
          </div>
          <span className="ml-auto text-xs text-gray-500 font-mono">demo_user</span>
        </div>
      </nav>

      {/* Content */}
      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 py-8">
        {children}
      </main>

      {/* Toasts */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
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
