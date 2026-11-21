import { useState, useEffect, useCallback } from 'react';
import {
  getTraces,
  getTraceStats,
  getTraceConfig,
  exportTracesUrl,
  type TraceEvent,
  type TraceStats as Stats,
  type TraceConfig,
} from '../lib/api';
import TraceStatsRow from './TraceStats';
import TraceCard from './TraceCard';
import SequenceTracker from './SequenceTracker';
import PolicyPanel from './PolicyPanel';

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function TracesSidebar({ open, onClose }: Props) {
  const [traces, setTraces] = useState<TraceEvent[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [config, setConfig] = useState<TraceConfig | null>(null);
  const [sessionId, setSessionId] = useState('');
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [traceRes, statsRes, configRes] = await Promise.all([
        getTraces(),
        getTraceStats(),
        getTraceConfig(),
      ]);
      setTraces(traceRes.traces);
      setSessionId(traceRes.session_id);
      setStats(statsRes);
      setConfig(configRes);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    refresh();
    const interval = setInterval(refresh, 2000);
    return () => clearInterval(interval);
  }, [open, refresh]);

  return (
    <>
      {/* Sidebar panel */}
      <div
        className={`fixed top-0 right-0 h-full z-40 bg-gray-950 border-l border-gray-800 shadow-2xl transition-transform duration-300 ease-in-out w-full sm:w-[480px] ${
          open ? 'translate-x-0' : 'translate-x-full'
        }`}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 h-14 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <span className="text-emerald-400">⛊</span>
            <span className="text-sm font-semibold text-white">Anvil Traces</span>
            <span className="text-[10px] font-mono text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">
              {sessionId}
            </span>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          </div>
          <a
            href={exportTracesUrl()}
            className="text-[10px] text-gray-500 hover:text-gray-300 border border-gray-700 rounded px-2 py-1 transition-colors"
          >
            Export
          </a>
        </div>

        {/* Content */}
        <div className="h-[calc(100%-3.5rem)] overflow-y-auto p-4 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <span className="text-gray-500 text-sm">Loading…</span>
            </div>
          ) : (
            <>
              {stats && <TraceStatsRow stats={stats} />}

              {config && <PolicyPanel config={config} />}

              {config && (
                <SequenceTracker
                  sequences={config.sequences}
                  satisfiedTools={config.sequence_state}
                />
              )}

              <div>
                <h3 className="text-[10px] uppercase tracking-wider text-gray-500 font-semibold mb-2">
                  Timeline ({traces.length})
                </h3>
                {traces.length === 0 ? (
                  <div className="bg-gray-900 border border-gray-800 rounded-lg p-6 text-center">
                    <p className="text-gray-500 text-xs">No events yet. Chat with the agent to generate traces.</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {[...traces].reverse().map((t) => (
                      <TraceCard key={t.id} trace={t} />
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
