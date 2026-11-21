import { API_BASE, USER_ID } from './constants';
import type {
  Account,
  Transaction,
  TransferRequest,
  TransferInitiateResponse,
  TransferConfirmResponse,
  PublicAccount,
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

export async function cancelTransfer(
  transferId: string,
): Promise<{ transfer_id: string; status: string; message: string }> {
  return request(`${API_BASE}/transfers/${transferId}/cancel`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: USER_ID }),
  });
}

export async function deposit(
  accountId: string,
  amount: number,
): Promise<Account> {
  return request(`${API_BASE}/accounts/${accountId}/deposit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: USER_ID, amount }),
  });
}

export async function getDirectory(): Promise<{ accounts: PublicAccount[] }> {
  return request(`${API_BASE}/directory`);
}

export async function lookupAccount(accountNumber: string): Promise<PublicAccount> {
  return request(`${API_BASE}/directory/lookup/${encodeURIComponent(accountNumber)}`);
}

export async function resetAccounts(): Promise<{ status: string; accounts: Account[] }> {
  return request(`${API_BASE}/accounts/reset?user_id=${USER_ID}`, { method: 'POST' });
}

// ── Pending Transfers ────────────────────────────────────────────────

export interface PendingTransfer {
  transfer_id: string;
  amount: number;
  from_account: string;
  to_account: string;
  from_name: string;
  to_name: string;
  description: string;
  initiated_by: string;
  otp_code: string;
  expires_at: string | null;
  created_at: string;
}

export async function getPendingTransfers(): Promise<{ transfers: PendingTransfer[] }> {
  return request(`${API_BASE}/transfers/pending?user_id=${USER_ID}`);
}

// ── Trace API ────────────────────────────────────────────────────────

export interface TraceEvent {
  id: string;
  timestamp: string;
  agent_id: string;
  tool: string;
  parameters: Record<string, unknown>;
  decision: 'allowed' | 'blocked';
  result: string;
  reason: string;
  violation: string | null;
  policy_rule: string;
  execution_ms: number | null;
}

export interface TraceStats {
  total: number;
  allowed: number;
  blocked: number;
  avg_ms: number;
  tools_used: string[];
}

export interface SequenceRule {
  before: string;
  requires: string[];
  match_fields: string[];
}

export interface ToolInfo {
  name: string;
  trust: string;
  injection_scanning: boolean;
  description: string;
}

export interface TraceConfig {
  policy_name: string;
  policy_description: string;
  agent_id: string;
  strictness: string;
  tools: ToolInfo[];
  sequences: SequenceRule[];
  sequence_state: string[];
  settings: {
    injection_scanning: boolean;
    default_trust: string;
    session_ttl: number;
  };
}

// Traces are per agent session; the viewer shows this tab's session.
const sessionQuery = () => `?session_id=${encodeURIComponent(agentSessionId())}`;

export async function getTraces(): Promise<{ traces: TraceEvent[]; session_id: string }> {
  return request(`/agent/traces${sessionQuery()}`);
}

export async function getTraceStats(): Promise<TraceStats> {
  return request(`/agent/traces/stats${sessionQuery()}`);
}

export async function getTraceConfig(): Promise<TraceConfig> {
  return request(`/agent/traces/config${sessionQuery()}`);
}

export function exportTracesUrl(): string {
  return `/agent/traces/export${sessionQuery()}`;
}

// ── Agent API ────────────────────────────────────────────────────────

export interface ToolCallInfo {
  tool: string;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
  blocked: boolean;
}

export interface ChatResponse {
  reply: string;
  tool_calls: ToolCallInfo[];
}

// One agent session per browser tab: the agent remembers the conversation
// and Anvil's sequence rules span messages within it.
export function agentSessionId(): string {
  let id = sessionStorage.getItem('agentSessionId');
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem('agentSessionId', id);
  }
  return id;
}

export async function agentChat(message: string): Promise<ChatResponse> {
  return request('/agent/agent/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, session_id: agentSessionId() }),
  });
}

export async function agentReset(): Promise<{ status: string }> {
  return request('/agent/agent/reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: agentSessionId() }),
  });
}

export { ApiException };
