import { config } from '../config';
import {
  clearTokens,
  decodeAccessToken,
  getAccessToken,
  getRefreshToken,
  isExpiring,
  saveTokens,
} from './tokens';

/**
 * HTTP client.
 *
 * Three responsibilities the rest of the app should never re-implement:
 *
 * 1. **Silent refresh.** §5 gives access tokens a 15-minute life. The client refreshes
 *    pre-emptively when a token is close to expiry and reactively on a 401, then replays the
 *    original request once. Concurrent callers share one in-flight refresh — otherwise five
 *    parallel requests would each rotate the refresh token, and §5's reuse detection would
 *    correctly read that as an attack and revoke the family.
 *
 * 2. **RFC-7807 parsing.** §7:391 specifies problem+json for every error, so errors arrive as
 *    a typed {@link ApiError} carrying `title`, `detail` and `type` rather than a bare status.
 *
 * 3. **Idempotency keys.** §7:391 requires them on payment and bid endpoints. Passing
 *    `idempotencyKey` sets the header; a retry of a failed checkout then cannot double-charge.
 */

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  errors?: { field: string; message: string }[];
  retry_after?: number;
}

export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem;

  constructor(problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = 'ApiError';
    this.status = problem.status;
    this.problem = problem;
  }

  /** §5: the caller is authenticated but their lifecycle state forbids this action. */
  get isScopeDenied(): boolean {
    return this.status === 403 && this.problem.type === '/errors/insufficient-scope';
  }

  /** FR-6.3: entry-tier visibility is gated behind a Pro subscription. */
  get isProRequired(): boolean {
    return this.problem.type === '/errors/pro-required';
  }

  get isRateLimited(): boolean {
    return this.status === 429;
  }
}

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined>;
  /** §7:391 — required on payment and bid endpoints. */
  idempotencyKey?: string;
  /** Signup and OTP routes are the only unauthenticated ones (§7). */
  skipAuth?: boolean;
  signal?: AbortSignal;
}

/** Set by the session store so a hard auth failure can drop the user to signup. */
let onAuthFailure: (() => void) | null = null;
export function setAuthFailureHandler(handler: () => void): void {
  onAuthFailure = handler;
}

let refreshInFlight: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  // Coalesce: one rotation at a time, or §5 reuse detection revokes the family.
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    try {
      const refreshToken = await getRefreshToken();
      if (!refreshToken) return null;

      const response = await fetch(`${config.apiBaseUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        // A rejected refresh means the family was revoked or expired — the session is over.
        await clearTokens();
        onAuthFailure?.();
        return null;
      }

      const data = (await response.json()) as {
        access_token: string;
        refresh_token: string;
      };
      await saveTokens({
        accessToken: data.access_token,
        refreshToken: data.refresh_token,
      });
      return data.access_token;
    } catch {
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

async function authHeader(skipAuth: boolean): Promise<Record<string, string>> {
  if (skipAuth) return {};

  let token = await getAccessToken();
  if (!token) return {};

  // Pre-emptive refresh: cheaper than letting the request fail and replaying it.
  const claims = decodeAccessToken(token);
  if (claims && isExpiring(claims)) {
    token = (await refreshAccessToken()) ?? token;
  }
  return { Authorization: `Bearer ${token}` };
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = `${config.apiBaseUrl}${path}`;
  if (!query) return url;

  const params = Object.entries(query)
    .filter(([, value]) => value !== undefined)
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);

  return params.length ? `${url}?${params.join('&')}` : url;
}

async function toProblem(response: Response): Promise<Problem> {
  try {
    const body = await response.json();
    if (body && typeof body === 'object' && 'title' in body) {
      return body as Problem;
    }
    return { type: 'about:blank', title: 'Request failed', status: response.status };
  } catch {
    return {
      type: 'about:blank',
      title: response.status >= 500 ? 'Server error' : 'Request failed',
      status: response.status,
    };
  }
}

async function send<T>(path: string, options: RequestOptions, retrying = false): Promise<T> {
  const { method = 'GET', body, query, idempotencyKey, skipAuth = false, signal } = options;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.requestTimeoutMs);
  signal?.addEventListener('abort', () => controller.abort());

  try {
    const response = await fetch(buildUrl(path, query), {
      method,
      signal: controller.signal,
      headers: {
        Accept: 'application/json',
        ...(body ? { 'Content-Type': 'application/json' } : {}),
        ...(idempotencyKey ? { 'Idempotency-Key': idempotencyKey } : {}),
        ...(await authHeader(skipAuth)),
      },
      body: body ? JSON.stringify(body) : undefined,
    });

    // Reactive refresh, exactly once — a second 401 means the session is genuinely dead.
    if (response.status === 401 && !skipAuth && !retrying) {
      const refreshed = await refreshAccessToken();
      if (refreshed) return send<T>(path, options, true);
    }

    if (!response.ok) {
      throw new ApiError(await toProblem(response));
    }

    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof Error && error.name === 'AbortError') {
      throw new ApiError({
        type: '/errors/timeout',
        title: 'Request timed out',
        status: 408,
        detail: 'The server took too long to respond. Check your connection and try again.',
      });
    }
    throw new ApiError({
      type: '/errors/network',
      title: 'No connection',
      status: 0,
      detail: 'Could not reach Sincère. Check your internet connection.',
    });
  } finally {
    clearTimeout(timeout);
  }
}

export const api = {
  get: <T>(path: string, options: Omit<RequestOptions, 'method' | 'body'> = {}) =>
    send<T>(path, { ...options, method: 'GET' }),

  post: <T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method'> = {}) =>
    send<T>(path, { ...options, method: 'POST', body }),

  patch: <T>(path: string, body?: unknown, options: Omit<RequestOptions, 'method'> = {}) =>
    send<T>(path, { ...options, method: 'PATCH', body }),

  delete: <T>(path: string, options: Omit<RequestOptions, 'method'> = {}) =>
    send<T>(path, { ...options, method: 'DELETE' }),
};
