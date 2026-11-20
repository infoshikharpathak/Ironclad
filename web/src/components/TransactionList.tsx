import { useEffect, useState } from 'react';
import { getTransactions } from '../lib/api';
import type { Transaction } from '../types';
import TransactionRow from './TransactionRow';

export default function TransactionList({ accountId }: { accountId: string }) {
  const [txns, setTxns] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getTransactions(accountId)
      .then((data) => {
        if (!cancelled) setTxns(data.transactions);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [accountId]);

  if (loading)
    return <p className="text-sm text-gray-500 py-4">Loading transactions…</p>;

  if (txns.length === 0)
    return <p className="text-sm text-gray-500 py-4">No transactions yet.</p>;

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead>
          <tr className="text-xs text-gray-500 uppercase tracking-wider border-b border-gray-800">
            <th className="pb-2 pr-3 font-medium">Date</th>
            <th className="pb-2 pr-3 font-medium">Description</th>
            <th className="pb-2 pr-3 font-medium">From</th>
            <th className="pb-2 pr-3 font-medium">To</th>
            <th className="pb-2 pr-3 font-medium text-right">Amount</th>
            <th className="pb-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {txns.map((tx) => (
            <TransactionRow key={tx.id} tx={tx} contextAccountId={accountId} />
          ))}
        </tbody>
      </table>
    </div>
  );
}
