import type { SequenceRule } from '../lib/api';

interface Props {
  sequences: SequenceRule[];
  satisfiedTools: string[];
}

export default function SequenceTracker({ sequences, satisfiedTools }: Props) {
  if (sequences.length === 0) return null;

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3">
      <h3 className="text-xs uppercase tracking-wider text-gray-500 font-semibold">Sequence Requirements</h3>

      {sequences.map((seq, i) => {
        const allMet = seq.requires.every((r) => satisfiedTools.includes(r));
        return (
          <div key={i} className="flex items-center gap-2 flex-wrap">
            {seq.requires.map((req, j) => {
              const met = satisfiedTools.includes(req);
              return (
                <span key={j} className="flex items-center gap-1.5">
                  {j > 0 && <span className="text-gray-600 text-xs">→</span>}
                  <span
                    className={`text-xs font-mono px-2 py-1 rounded-md border ${
                      met
                        ? 'bg-emerald-900/30 border-emerald-700/50 text-emerald-300'
                        : 'bg-gray-800 border-gray-700 text-gray-500'
                    }`}
                  >
                    {met ? '✓' : '○'} {req}
                  </span>
                </span>
              );
            })}

            <span className="text-gray-600 text-xs">→</span>

            <span
              className={`text-xs font-mono px-2 py-1 rounded-md border ${
                allMet
                  ? 'bg-blue-900/30 border-blue-700/50 text-blue-300'
                  : 'bg-gray-800 border-gray-700 text-gray-500'
              }`}
            >
              {allMet ? '●' : '○'} {seq.before}
            </span>

            <span className={`text-[10px] ml-1 ${allMet ? 'text-emerald-400' : 'text-gray-600'}`}>
              {allMet ? 'Ready' : 'Locked'}
            </span>
          </div>
        );
      })}
    </div>
  );
}
