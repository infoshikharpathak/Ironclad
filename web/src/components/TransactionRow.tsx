import type { Transaction } from '../types';
import { formatCurrency } from './AccountCard';

const statusColors: Record<string, string> = {
  confirmed: 'bg-emerald-900/60 text-emerald-300',
  pending_otp: 'bg-amber-900/60 text-amber-300',
  cancelled: 'bg-red-900/60 text-red-300',
  failed: 'bg-red-900/60 text-red-300',
};

export default function TransactionRow({
  tx,
  contextAccountId,
}: {
  tx: Transaction;
  contextAccountId?: string;
}) {
  const isDebit = contextAccountId
    ? tx.from_account === contextAccountId
    : true; // default: show as debit
  const dateStr = new Date(tx.created_at).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <tr className="border-b border-gray-800/60 hover:bg-gray-900/40 transition-colors">
      <td className="py-3 pr-3 text-xs text-gray-500 whitespace-nowrap">{dateStr}</td>
      <td className="py-3 pr-3 text-sm text-gray-300 max-w-[180px] truncate">
        {tx.description || '—'}
      </td>
      <td className="py-3 pr-3 text-xs text-gray-500 font-mono whitespace-nowrap">
        {tx.from_account.replace('acc_demo_user_', '')}
      </td>
      <td className="py-3 pr-3 text-xs text-gray-500 font-mono whitespace-nowrap">
        {tx.to_account.replace('acc_demo_user_', '')}
      </td>
      <td
        className={`py-3 pr-3 text-sm font-mono font-medium text-right whitespace-nowrap ${
          isDebit ? 'text-red-400' : 'text-emerald-400'
        }`}
      >
        {isDebit ? '−' : '+'} {formatCurrency(tx.amount)}
      </td>
      <td className="py-3">
        <span
          className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${statusColors[tx.status] ?? 'bg-gray-800 text-gray-400'}`}
        >
          {tx.status.replace('_', ' ')}
        </span>
      </td>
    </tr>
  );
}
