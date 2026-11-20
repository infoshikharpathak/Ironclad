import type { Account } from '../types';

function formatCurrency(amount: number) {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(amount);
}

export default function AccountCard({ account }: { account: Account }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 flex flex-col gap-2 hover:border-gray-700 transition-colors">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-gray-300">{account.name}</span>
        <span
          className={`text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${
            account.account_type === 'checking'
              ? 'bg-blue-900/60 text-blue-300'
              : 'bg-purple-900/60 text-purple-300'
          }`}
        >
          {account.account_type}
        </span>
      </div>
      <span className="text-2xl font-bold font-mono text-white tracking-tight">
        {formatCurrency(account.balance)}
      </span>
      <span className="text-xs text-gray-500 font-mono">{account.id}</span>
    </div>
  );
}

export { formatCurrency };
