import { API_BASE, USER_ID } from './constants';
import type {
  Account,
  Transaction,
  TransferRequest,
  TransferInitiateResponse,
  TransferConfirmResponse,
  ApiError,
} from '../types';

class ApiException extends Error {
  constructor(
    public status: number,
    public body: ApiError,
  ) {
    super(body.message);
    this.name = 'ApiException';
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  const json = await res.json();
  if (!res.ok) throw new ApiException(res.status, json as ApiError);
  return json as T;
}

export async function getAccounts(): Promise<{ accounts: Account[] }> {
  return request(`${API_BASE}/accounts?user_id=${USER_ID}`);
}

export async function getTransactions(
  accountId: string,
  limit = 20,
  offset = 0,
): Promise<{ transactions: Transaction[]; limit: number; offset: number }> {
  return request(
    `${API_BASE}/accounts/${accountId}/transactions?user_id=${USER_ID}&limit=${limit}&offset=${offset}`,
  );
}

export async function initiateTransfer(
  data: TransferRequest,
): Promise<TransferInitiateResponse> {
  return request(`${API_BASE}/transfers/initiate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...data, user_id: USER_ID }),
  });
}

export async function confirmTransfer(
  transferId: string,
  otpCode: string,
): Promise<TransferConfirmResponse> {
  return request(`${API_BASE}/transfers/${transferId}/confirm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: USER_ID, otp_code: otpCode }),
  });
}

export async function resetAccounts(): Promise<{ status: string; accounts: Account[] }> {
  return request(`${API_BASE}/accounts/reset?user_id=${USER_ID}`, { method: 'POST' });
}

export { ApiException };
