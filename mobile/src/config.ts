import Constants from 'expo-constants';

/**
 * Runtime configuration.
 *
 * The API base URL is derived rather than hard-coded. On a physical phone running Expo Go,
 * `localhost` resolves to the phone itself, so a literal `http://localhost:8000` cannot reach
 * the dev machine. Expo exposes the dev server's LAN address as `hostUri`; we reuse its host
 * and swap in the API port. That makes `npx expo start` + scan-the-QR work with no manual edit.
 */

function resolveApiBaseUrl(): string {
  const configured = Constants.expoConfig?.extra?.apiBaseUrl as string | undefined;

  // An explicit non-localhost value (staging, production) always wins.
  if (configured && !configured.includes('localhost')) {
    return configured;
  }

  // hostUri looks like "192.168.1.7:8081" while the dev server is running.
  const hostUri = Constants.expoConfig?.hostUri;
  if (hostUri) {
    const host = hostUri.split(':')[0];
    return `http://${host}:${API_PORT}/v1`;
  }

  return configured ?? `http://localhost:${API_PORT}/v1`;
}

const API_PORT = 8000;

export const config = {
  apiBaseUrl: resolveApiBaseUrl(),

  /** WebSocket endpoint for chat (§7: `WS /ws/chat`). Same host, ws:// scheme. */
  get wsUrl(): string {
    return this.apiBaseUrl.replace(/^http/, 'ws').replace(/\/v1$/, '/v1/ws/chat');
  },

  /** §4: location is captured once per app foreground — never in the background. */
  locationRefreshMinIntervalMs: 60_000,

  /** §2: p95 < 300ms for interactive reads. A 15s ceiling is a dead-network signal. */
  requestTimeoutMs: 15_000,

  /** §4 no-push UX: badge counts refresh on app open, so the client re-polls on foreground. */
  refetchOnForeground: true,
} as const;

export const isDev = __DEV__;
