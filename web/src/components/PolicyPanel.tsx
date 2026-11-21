import { useState } from 'react';
import type { TraceConfig } from '../lib/api';

export default function PolicyPanel({ config }: { config: TraceConfig }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 text-left"
      >
        <div className="flex items-center gap-2">
          <span className="text-emerald-400 text-sm">⛊</span>
          <span className="text-sm font-medium text-gray-300">Active Policy</span>
          <span className="text-xs font-mono text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
            {config.policy_name}
          </span>
          <span className={`text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-full font-semibold ${
            config.strictness === 'strict'
              ? 'bg-red-900/40 text-red-300 border border-red-800/50'
              : 'bg-amber-900/40 text-amber-300 border border-amber-800/50'
          }`}>
            {config.strictness}
          </span>
        </div>
        <span className={`text-gray-600 text-xs transition-transform ${open ? 'rotate-90' : ''}`}>▸</span>
      </button>

      {open && (
        <div className="px-4 pb-4 space-y-4 border-t border-gray-800 pt-3">
          <p className="text-xs text-gray-400">{config.policy_description}</p>

          {/* Tools */}
          <div>
            <h4 className="text-[10px] uppercase tracking-wider text-gray-500 font-semibold mb-2">
              Allowed Tools ({config.tools.length})
            </h4>
            <div className="grid gap-1.5">
              {config.tools.map((t) => (
                <div
                  key={t.name}
                  className="flex items-center justify-between bg-gray-800 rounded-md px-3 py-1.5"
                >
                  <span className="text-xs font-mono text-gray-300">{t.name}</span>
                  <div className="flex items-center gap-2">
                    {t.injection_scanning && (
                      <span className="text-[9px] text-amber-400 bg-amber-900/30 px-1.5 py-0.5 rounded">
                        scan
                      </span>
                    )}
                    <span className={`text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded ${
                      t.trust === 'trusted'
                        ? 'text-emerald-400 bg-emerald-900/30'
                        : 'text-red-400 bg-red-900/30'
                    }`}>
                      {t.trust}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Settings */}
          <div>
            <h4 className="text-[10px] uppercase tracking-wider text-gray-500 font-semibold mb-2">
              Global Settings
            </h4>
            <div className="grid grid-cols-3 gap-2 text-xs">
              <div className="bg-gray-800 rounded-md px-3 py-2">
                <p className="text-gray-500 text-[10px] mb-0.5">Injection Scan</p>
                <p className={config.settings.injection_scanning ? 'text-emerald-400' : 'text-gray-500'}>
                  {config.settings.injection_scanning ? 'Enabled' : 'Disabled'}
                </p>
              </div>
              <div className="bg-gray-800 rounded-md px-3 py-2">
                <p className="text-gray-500 text-[10px] mb-0.5">Default Trust</p>
                <p className="text-gray-300">{config.settings.default_trust}</p>
              </div>
              <div className="bg-gray-800 rounded-md px-3 py-2">
                <p className="text-gray-500 text-[10px] mb-0.5">Session TTL</p>
                <p className="text-gray-300">{config.settings.session_ttl}s</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
