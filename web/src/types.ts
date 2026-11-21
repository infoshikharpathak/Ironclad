export interface Account {
  id: string;
  name: string;
  account_type: 'checking' | 'savings';
  balance: number;
  currency: string;
}

export interface Transaction {
  id: string;
  from_account: string;
  to_account: string;
  amount: number;
  status: 'pending_otp' | 'confirmed' | 'cancelled' | 'failed';
  description: string;
  initiated_by: string;
  otp_attempts: number;
  otp_expires_at: string | null;
  created_at: string;
  confirmed_at: string | null;
}

export interface TransferRequest {
  from_account: string;
  to_account: string;
  amount: number;
  description: string;
  idempotency_key?: string;
  initiated_by?: string;
}

export interface TransferInitiateResponse {
  transfer_id: string;
  status: string;
  message: string;
  amount: number;
  from_account: string;
  to_account: string;
  // No otp_code: the code reaches the user only via the dashboard.
  expires_at: string | null;
  idempotent_replay?: boolean;
}

export interface TransferConfirmResponse {
  transfer_id: string;
  status: string;
  message: string;
  transaction: Transaction;
  new_balances: Record<string, number>;
}

export interface OTPEvent {
  transfer_id: string;
  amount: number;
  from_account: string;
  to_account: string;
  from_name: string;
  to_name: string;
  description: string;
  initiated_by: string;
  otp_code: string;
}

export interface WSEvent {
  type: 'otp_required' | 'transfer_confirmed' | 'transfer_cancelled' | 'balance_updated';
  data: any;
}

export interface PublicAccount {
  account_number: string;
  owner_name: string;
  account_type: 'checking' | 'savings';
  currency: string;
}

export interface ApiError {
  error: string;
  message: string;
  details: Record<string, any>;
}
