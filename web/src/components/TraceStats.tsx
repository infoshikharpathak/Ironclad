import type { TraceStats as Stats } from '../lib/api';

export default function TraceStats({ stats }: { stats: Stats }) {
  const cards = [
    { label: 'Total Calls', value: stats.total, color: 'text-white' },
    { label: 'Allowed', value: stats.allowed, color: 'text-emerald-400' },
    { label: 'Blocked', value: stats.blocked, color: stats.blocked > 0 ? 'text-red-400' : 'text-gray-400' },
    { label: 'Avg Latency', value: `${stats.avg_ms}ms`, color: 'text-blue-400' },
  ];

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
      {cards.map((c) => (
        <div
          key={c.label}
          className="bg-gray-900 border border-gray-800 rounded-xl px-4 py-3"
        >
          <p className="text-[10px] uppercase tracking-wider text-gray-500 mb-1">{c.label}</p>
          <p className={`text-2xl font-mono font-bold ${c.color}`}>{c.value}</p>
        </div>
      ))}
    </div>
  );
}
