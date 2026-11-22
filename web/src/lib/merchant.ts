// Labels for merchant payment requests (see bank-service routes/payments.py).

interface MaybeMerchant {
  initiated_by: string;
  merchant_display_name?: string | null;
  channel?: 'checkout' | 'agent' | null;
}

/** Started by an AI agent: the user's own assistant, or a merchant's. */
export function isAgentStarted(t: MaybeMerchant): boolean {
  return t.initiated_by === 'agent' || t.initiated_by === 'merchant_agent' || t.channel === 'agent';
}

/** "FoodDash checkout" / "Started by FoodDash's AI agent", or null for a plain transfer. */
export function merchantChannelLine(t: MaybeMerchant): string | null {
  if (!t.merchant_display_name) return null;
  return t.channel === 'agent'
    ? `Started by ${t.merchant_display_name}'s AI agent`
    : `${t.merchant_display_name} checkout`;
}
