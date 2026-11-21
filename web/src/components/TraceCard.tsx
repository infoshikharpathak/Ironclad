import { useState } from 'react';
import type { TraceEvent } from '../lib/api';

function truncate(obj: Record<string, unknown>, maxLen = 120): string {
  const s = JSON.stringify(obj);
  return s.length > maxLen ? s.slice(0, maxLen) + '…' : s;
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts);
    const hms = d.toLocaleTimeString('en-US', { hour12: false });
    const ms = String(d.getMilliseconds()).padStart(3, '0');
    return `${hms}.${ms}`;
  } catch {
    return ts;
  }
}

const ruleLabels: Record<string, string> = {
  sequence: 'SEQUENCE',
  access_control: 'ACCESS',
  injection_scan: 'INJECTION',
  schema_validation: 'SCHEMA',
  upstream: 'UPSTREAM',
  none: '',
};

export default function TraceCard({ trace }: { trace: TraceEvent }) {
  const [expanded, setExpanded] = useState(false);
  const isBlocked = trace.decision === 'blocked';
  const isInjection = trace.violation?.includes('injection') ?? false;

  const borderColor = isInjection
    ? 'border-l-amber-500'
    : isBlocked
      ? 'border-l-red-500'
      : 'border-l-emerald-500';

  const icon = isInjection ? '⚠' : isBlocked ? '✗' : '✓';
  const iconColor = isInjection
    ? 'text-amber-400'
    : isBlocked
      ? 'text-red-400'
      : 'text-emerald-400';

  const decisionBg = isInjection
    ? 'bg-amber-900/30 text-amber-300'
    : isBlocked
      ? 'bg-red-900/30 text-red-300'
      : 'bg-emerald-900/30 text-emerald-300';

  return (
    <div
      className={`bg-gray-900 border border-gray-800 border-l-4 ${borderColor} rounded-lg cursor-pointer hover:border-gray-700 transition-colors`}
      onClick={() => setExpanded(!expanded)}
    >
      {/* Header row */}
      <div className="flex items-center gap-3 px-4 py-3">
        <span className={`text-lg ${iconColor}`}>{icon}</span>

        <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-md ${decisionBg}`}>
          {isBlocked ? 'Blocked' : 'Allowed'}
        </span>

        <span className="text-sm font-mono font-medium text-white">{trace.tool}</span>

        {trace.policy_rule !== 'none' && (
          <span className="text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">
            {ruleLabels[trace.policy_rule] ?? trace.policy_rule}
          </span>
        )}

        <span className="ml-auto text-[11px] text-gray-500 font-mono">
          {formatTime(trace.timestamp)}
        </span>

        {trace.execution_ms != null && (
          <span className="text-[11px] text-gray-600 font-mono">{trace.execution_ms}ms</span>
        )}

        <span className={`text-gray-600 text-xs transition-transform ${expanded ? 'rotate-90' : ''}`}>▸</span>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="px-4 pb-4 pt-0 space-y-2 border-t border-gray-800">
          <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-xs mt-3">
            <span className="text-gray-500">Agent</span>
            <span className="text-gray-300 font-mono">{trace.agent_id}</span>

            <span className="text-gray-500">Params</span>
            <pre className="text-gray-400 font-mono whitespace-pre-wrap break-all">
              {JSON.stringify(trace.parameters, null, 2)}
            </pre>

            {isBlocked && (
              <>
                <span className="text-gray-500">Reason</span>
                <span className={isInjection ? 'text-amber-300' : 'text-red-300'}>{trace.reason}</span>
              </>
            )}

            {trace.violation && (
              <>
                <span className="text-gray-500">Violation</span>
                <span className="text-gray-400 font-mono">{trace.violation}</span>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
