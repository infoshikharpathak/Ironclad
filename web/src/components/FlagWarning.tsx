// Shown above a pending transfer's details when Anvil blocked the assistant's
// reply about it. The transfer is still pending: confirm and decline work as usual.
export const FLAG_WARNING =
  "Ironclad blocked the assistant's reply about this transfer. Approve only if you asked for it.";

export default function FlagWarning({ compact = false }: { compact?: boolean }) {
  return (
    <div
      role="alert"
      className={`flex items-start gap-2 rounded-lg bg-red-900/40 border border-red-600/70 ${
        compact ? 'px-2.5 py-1.5' : 'px-3 py-2 mb-3'
      }`}
    >
      <span className="text-red-400 text-sm leading-tight">⚠</span>
      <span className="text-xs text-red-200 font-medium">{FLAG_WARNING}</span>
    </div>
  );
}
