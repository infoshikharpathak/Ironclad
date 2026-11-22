import { useState, useEffect, useCallback } from 'react';
import { getPendingTransfers, confirmTransfer, cancelTransfer, type PendingTransfer } from '../lib/api';
import { useBank } from '../context/BankContext';
import { formatCurrency } from './AccountCard';
import type { ApiError } from '../types';
import { isAgentStarted, merchantChannelLine } from '../lib/merchant';
import FlagWarning from './FlagWarning';

export default function PendingTransfers() {
  const { refreshAccounts, addToast, flaggedTransfers } = useBank();
  const [transfers, setTransfers] = useState<PendingTransfer[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [otpInputs, setOtpInputs] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});

  const fetchPending = useCallback(async () => {
    try {
      const data = await getPendingTransfers();
      setTransfers(data.transfers);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPending();
  }, [fetchPending]);

  const handleConfirm = async (t: PendingTransfer) => {
    const otp = otpInputs[t.transfer_id]?.trim();
    if (!otp || otp.length < 6) return;

    setConfirming(t.transfer_id);
    setErrors((prev) => ({ ...prev, [t.transfer_id]: '' }));

    try {
      await confirmTransfer(t.transfer_id, otp);
      addToast('Transfer confirmed', 'success');
      await refreshAccounts();
      setTransfers((prev) => prev.filter((p) => p.transfer_id !== t.transfer_id));
    } catch (err: any) {
      const body: ApiError | undefined = err.body;
      const msg = body?.message ?? 'Confirmation failed';
      setErrors((prev) => ({ ...prev, [t.transfer_id]: msg }));

      if (body?.error === 'OTP_MAX_ATTEMPTS' || body?.error === 'OTP_EXPIRED') {
        setTimeout(() => {
          setTransfers((prev) => prev.filter((p) => p.transfer_id !== t.transfer_id));
        }, 2000);
      }
    } finally {
      setConfirming(null);
    }
  };

  const handleDecline = async (t: PendingTransfer) => {
    try {
      await cancelTransfer(t.transfer_id);
      addToast('Transfer declined', 'info');
      setTransfers((prev) => prev.filter((p) => p.transfer_id !== t.transfer_id));
    } catch {
      // already cancelled
      setTransfers((prev) => prev.filter((p) => p.transfer_id !== t.transfer_id));
    }
  };

  if (loading) return null;
  if (transfers.length === 0) return null;

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-medium text-amber-400 flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
        Pending Transfers ({transfers.length})
      </h2>

      {transfers.map((t) => {
        const isAgent = isAgentStarted(t);
        const channelLine = merchantChannelLine(t);
        const isFlagged = !!t.flagged_by_output_scan || flaggedTransfers.has(t.transfer_id);
        return (
          <div
            key={t.transfer_id}
            className="bg-gray-900 border border-gray-700 rounded-xl p-4 space-y-3"
          >
            {/* Header */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-lg font-mono font-semibold text-white">
                  {formatCurrency(t.amount)}
                </span>
                {isAgent && (
                  <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-amber-900/50 text-amber-300 border border-amber-700/50">
                    agent
                  </span>
                )}
              </div>
              <span className="text-[10px] text-gray-500 font-mono">{t.transfer_id}</span>
            </div>

            {isFlagged && <FlagWarning compact />}

            {/* From → To */}
            <div className="flex items-center gap-3 text-sm">
              <div>
                <span className="text-gray-500 text-xs">From </span>
                <span className="text-gray-300">{t.from_name}</span>
              </div>
              <span className="text-gray-600">→</span>
              <div>
                <span className="text-gray-500 text-xs">To </span>
                <span className="text-gray-300">{t.to_name}</span>
                {t.merchant_display_name && <span className="text-gray-500 text-xs"> (merchant)</span>}
              </div>
            </div>

            {channelLine && (
              <p className="text-xs text-gray-400">
                {channelLine}{t.order_ref && <> · order <span className="font-mono">{t.order_ref}</span></>}
              </p>
            )}

            {t.description && (
              <p className="text-xs text-gray-500">{t.description}</p>
            )}

            {/* OTP + Confirm */}
            <div className="bg-gray-800 border border-gray-700 rounded-lg p-3">
              <p className="text-xs text-gray-500 uppercase tracking-wider mb-1.5">OTP Code</p>
              <p className="text-2xl font-mono font-bold tracking-[0.3em] text-emerald-400 mb-3">
                {t.otp_code}
              </p>

              <div className="flex gap-2">
                <input
                  type="text"
                  inputMode="numeric"
                  maxLength={6}
                  value={otpInputs[t.transfer_id] ?? ''}
                  onChange={(e) =>
                    setOtpInputs((prev) => ({
                      ...prev,
                      [t.transfer_id]: e.target.value.replace(/\D/g, ''),
                    }))
                  }
                  onKeyDown={(e) => e.key === 'Enter' && handleConfirm(t)}
                  placeholder="Enter OTP"
                  className="flex-1 bg-gray-900 border border-gray-600 rounded-lg px-3 py-2 text-center text-sm font-mono tracking-wider text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500 transition-colors"
                />
                <button
                  onClick={() => handleDecline(t)}
                  className="px-3 py-2 rounded-lg border border-gray-600 text-gray-400 text-sm font-medium hover:text-gray-200 hover:border-gray-500 transition-colors"
                >
                  Decline
                </button>
                <button
                  onClick={() => handleConfirm(t)}
                  disabled={
                    confirming === t.transfer_id ||
                    (otpInputs[t.transfer_id]?.length ?? 0) < 6
                  }
                  className="px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                >
                  {confirming === t.transfer_id ? 'Confirming…' : 'Confirm'}
                </button>
              </div>

              {errors[t.transfer_id] && (
                <p className="text-xs text-red-400 mt-2">{errors[t.transfer_id]}</p>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
