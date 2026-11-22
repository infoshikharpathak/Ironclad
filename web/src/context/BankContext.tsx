import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from 'react';
import { getAccounts } from '../lib/api';
import { WS_BASE, USER_ID } from '../lib/constants';
import type { Account, OTPEvent, WSEvent } from '../types';

interface Toast {
  id: number;
  message: string;
  variant: 'success' | 'error' | 'info';
}

interface BankContextType {
  accounts: Account[];
  refreshAccounts: () => Promise<void>;
  loading: boolean;
  // OTP modal
  otpEvent: OTPEvent | null;
  clearOtp: () => void;
  // Transfers flagged after their OTP push (the assistant's reply was blocked)
  flaggedTransfers: Set<string>;
  // Toasts
  toasts: Toast[];
  addToast: (message: string, variant?: Toast['variant']) => void;
  removeToast: (id: number) => void;
}

const BankContext = createContext<BankContextType | null>(null);

let toastCounter = 0;

export function BankProvider({ children }: { children: ReactNode }) {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [otpEvent, setOtpEvent] = useState<OTPEvent | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [flaggedTransfers, setFlaggedTransfers] = useState<Set<string>>(new Set());

  const addToast = useCallback((message: string, variant: Toast['variant'] = 'info') => {
    const id = ++toastCounter;
    setToasts((prev) => [...prev, { id, message, variant }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 5000);
  }, []);

  const removeToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const refreshAccounts = useCallback(async () => {
    try {
      const data = await getAccounts();
      setAccounts(data.accounts);
    } catch {
      /* silently retry later */
    } finally {
      setLoading(false);
    }
  }, []);

  const clearOtp = useCallback(() => setOtpEvent(null), []);

  // Initial load
  useEffect(() => {
    refreshAccounts();
  }, [refreshAccounts]);

  // WebSocket
  useEffect(() => {
    let ws: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout>;

    function connect() {
      ws = new WebSocket(`${WS_BASE}/${USER_ID}`);

      ws.onmessage = (ev) => {
        try {
          const event: WSEvent = JSON.parse(ev.data);
          switch (event.type) {
            case 'otp_required':
              setOtpEvent(event.data as OTPEvent);
              break;
            case 'transfer_confirmed':
              addToast('Transfer confirmed ✓', 'success');
              refreshAccounts();
              break;
            case 'transfer_cancelled':
              addToast(`Transfer cancelled: ${event.data.reason}`, 'error');
              // Close the OTP modal if it's for this transfer (expired, or
              // withdrawn by the merchant that requested it).
              setOtpEvent((current) =>
                current && current.transfer_id === event.data.transfer_id ? null : current,
              );
              break;
            case 'transfer_flagged': {
              const id: string = event.data.transfer_id;
              setFlaggedTransfers((prev) => new Set(prev).add(id));
              setOtpEvent((current) =>
                current && current.transfer_id === id
                  ? { ...current, flagged_by_output_scan: true, flag_reason: event.data.flag_reason }
                  : current,
              );
              break;
            }
            case 'balance_updated':
              refreshAccounts();
              break;
          }
        } catch {
          /* ignore malformed events */
        }
      };

      ws.onclose = () => {
        reconnectTimer = setTimeout(connect, 3000);
      };
    }

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [addToast, refreshAccounts]);

  return (
    <BankContext.Provider
      value={{
        accounts,
        refreshAccounts,
        loading,
        otpEvent,
        clearOtp,
        flaggedTransfers,
        toasts,
        addToast,
        removeToast,
      }}
    >
      {children}
    </BankContext.Provider>
  );
}

export function useBank() {
  const ctx = useContext(BankContext);
  if (!ctx) throw new Error('useBank must be used inside <BankProvider>');
  return ctx;
}
