import { useState } from 'react';
import { confirmTransfer, cancelTransfer } from '../lib/api';
import { useBank } from '../context/BankContext';
import { formatCurrency } from './AccountCard';
import type { ApiError } from '../types';
import { isAgentStarted, merchantChannelLine } from '../lib/merchant';

export default function OTPModal() {
  const { otpEvent, clearOtp, refreshAccounts, addToast } = useBank();
  const [input, setInput] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!otpEvent) return null;

  const isAgentInitiated = isAgentStarted(otpEvent);
  const merchantName = otpEvent.merchant_display_name;
  const channelLine = merchantChannelLine(otpEvent);
  const isExternal = !merchantName && !otpEvent.to_account.startsWith('acc_demo_user_');

  const handleConfirm = async () => {
    if (!input.trim()) return;
    setSubmitting(true);
    setError(null);
    try {
      await confirmTransfer(otpEvent.transfer_id, input.trim());
      addToast('Transfer confirmed ✓', 'success');
      await refreshAccounts();
      clearOtp();
      setInput('');
    } catch (err: any) {
      const body: ApiError | undefined = err.body;
      setError(body?.message ?? 'Confirmation failed');
      if (body?.error === 'OTP_MAX_ATTEMPTS' || body?.error === 'OTP_EXPIRED') {
        setTimeout(() => {
          clearOtp();
          setInput('');
          setError(null);
        }, 2500);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-gray-900 border border-gray-700 rounded-2xl shadow-2xl w-full max-w-md mx-4 p-6">
        <h2 className="text-lg font-semibold text-white mb-1">
          {merchantName ? `Pay ${formatCurrency(otpEvent.amount)} to ${merchantName} (merchant)` : 'Confirm Transfer'}
        </h2>
        {channelLine && <p className="text-xs text-gray-400 mb-3">{channelLine}</p>}

        {/* Agent badge */}
        {isAgentInitiated && (
          <div className="flex items-center gap-2 mb-3 px-3 py-2 rounded-lg bg-amber-900/30 border border-amber-700/50">
            <span className="text-amber-400 text-sm">🤖</span>
            <span className="text-xs text-amber-300 font-medium">
              {merchantName
                ? `This payment was requested by ${merchantName}'s AI agent. Review the details carefully.`
                : 'This transfer was initiated by an AI agent. Review the details carefully.'}
            </span>
          </div>
        )}

        {/* Transfer details card */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 mb-4 space-y-3">
          {/* Amount */}
          <div className="text-center">
            <p className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">Amount</p>
            <p className="text-2xl font-mono font-bold text-white">
              {formatCurrency(otpEvent.amount)}
            </p>
          </div>

          <div className="border-t border-gray-700" />

          {/* From → To */}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2">
            <div className="text-center">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">From</p>
              <p className="text-sm font-medium text-white">{otpEvent.from_name}</p>
              <p className="text-[10px] text-gray-500 font-mono mt-0.5">
                {otpEvent.from_account.replace('acc_demo_user_', '')}
              </p>
            </div>
            <span className="text-gray-600 text-lg">→</span>
            <div className="text-center">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">To</p>
              <p className="text-sm font-medium text-white">
                {otpEvent.to_name}{merchantName && <span className="text-gray-500"> (merchant)</span>}
              </p>
              <p className="text-[10px] text-gray-500 font-mono mt-0.5">
                {otpEvent.to_account}
              </p>
              {isExternal && (
                <span className="inline-block mt-1 text-[9px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-blue-900/50 text-blue-300">
                  external
                </span>
              )}
            </div>
          </div>

          {/* Description */}
          {otpEvent.description && (
            <>
              <div className="border-t border-gray-700" />
              <div>
                <p className="text-xs text-gray-500 uppercase tracking-wider mb-0.5">Description</p>
                <p className="text-sm text-gray-300">{otpEvent.description}</p>
              </div>
            </>
          )}

          {/* Merchant order */}
          {otpEvent.order_ref && (
            <>
              <div className="border-t border-gray-700" />
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-500">Order ref</span>
                <span className="text-xs text-gray-300 font-mono">{otpEvent.order_ref}</span>
              </div>
            </>
          )}

          {/* Transfer ID */}
          <div className="border-t border-gray-700" />
          <div className="flex items-center justify-between">
            <span className="text-xs text-gray-500">Transfer ID</span>
            <span className="text-xs text-gray-400 font-mono">{otpEvent.transfer_id}</span>
          </div>
        </div>

        {/* OTP display */}
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-3 text-center mb-4">
          <p className="text-xs text-gray-500 uppercase tracking-wider mb-1">Your OTP Code</p>
          <p className="text-3xl font-mono font-bold tracking-[0.3em] text-emerald-400">
            {otpEvent.otp_code}
          </p>
        </div>

        {/* Input */}
        <label className="block text-xs text-gray-500 mb-1">Enter OTP to confirm</label>
        <input
          type="text"
          inputMode="numeric"
          maxLength={6}
          value={input}
          onChange={(e) => setInput(e.target.value.replace(/\D/g, ''))}
          onKeyDown={(e) => e.key === 'Enter' && handleConfirm()}
          autoFocus
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-center text-xl font-mono tracking-[0.3em] text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500 transition-colors"
          placeholder="000000"
        />

        {error && <p className="text-sm text-red-400 mt-2">{error}</p>}

        <div className="flex gap-3 mt-5">
          <button
            onClick={async () => {
              try {
                await cancelTransfer(otpEvent.transfer_id);
                addToast('Transfer declined', 'info');
              } catch { /* already cancelled or confirmed */ }
              clearOtp();
              setInput('');
              setError(null);
            }}
            className="flex-1 px-4 py-2.5 rounded-lg border border-gray-700 text-gray-300 text-sm font-medium hover:bg-gray-800 transition-colors"
          >
            Decline
          </button>
          <button
            onClick={handleConfirm}
            disabled={submitting || input.length < 6}
            className="flex-1 px-4 py-2.5 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? 'Confirming…' : 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  );
}
