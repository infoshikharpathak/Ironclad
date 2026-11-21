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
import TraceStatsRow from '../components/TraceStats';
import TraceCard from '../components/TraceCard';
import SequenceTracker from '../components/SequenceTracker';
import PolicyPanel from '../components/PolicyPanel';

export default function Traces() {
  const [traces, setTraces] = useState<TraceEvent[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [config, setConfig] = useState<TraceConfig | null>(null);
  const [sessionId, setSessionId] = useState<string>('');
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
    refresh();
    const interval = setInterval(refresh, 2000);
    return () => clearInterval(interval);
  }, [refresh]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <span className="text-gray-500 text-sm">Loading traces…</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="text-emerald-400 text-lg">⛊</span>
            <h1 className="text-xl font-semibold text-white">Anvil Governance Trace</h1>
          </div>
          <span className="text-xs font-mono text-gray-500 bg-gray-800 border border-gray-700 px-2 py-0.5 rounded">
            {sessionId}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-[10px] text-gray-500 uppercase tracking-wider">Live</span>
          </span>
        </div>
        <a
          href={exportTracesUrl()}
          className="px-3 py-1.5 rounded-lg border border-gray-700 text-gray-400 text-xs font-medium hover:text-gray-200 hover:border-gray-600 transition-colors"
        >
          Export JSON
        </a>
      </div>

      {/* Stats */}
      {stats && <TraceStatsRow stats={stats} />}

      {/* Policy panel */}
      {config && <PolicyPanel config={config} />}

      {/* Sequence tracker */}
      {config && (
        <SequenceTracker
          sequences={config.sequences}
          satisfiedTools={config.sequence_state}
        />
      )}

      {/* Timeline */}
      <div>
        <h2 className="text-xs uppercase tracking-wider text-gray-500 font-semibold mb-3">
          Event Timeline ({traces.length})
        </h2>

        {traces.length === 0 ? (
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-8 text-center">
            <p className="text-gray-500 text-sm">No trace events yet.</p>
            <p className="text-gray-600 text-xs mt-1">
              Chat with the AI Agent to generate governance events.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {[...traces].reverse().map((t) => (
              <TraceCard key={t.id} trace={t} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
