// When running via Vite dev server, the proxy handles /api → bank-service.
// When running in Docker (nginx), the same /api prefix is proxied to bank-service.
// Fall back to direct URL only when explicitly overridden.
export const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

// WS base resolves from the page origin; during Vite dev, the proxy handles /ws.
function wsBase(): string {
  if (import.meta.env.VITE_WS_BASE) return import.meta.env.VITE_WS_BASE;
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${window.location.host}/ws`;
}
export const WS_BASE = wsBase();

export const USER_ID = 'demo_user';
