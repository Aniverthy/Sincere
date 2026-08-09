import * as SecureStore from 'expo-secure-store';

/**
 * Token storage.
 *
 * Tokens live in the OS keystore (Keychain / Android Keystore) rather than AsyncStorage,
 * because AsyncStorage is plain unencrypted files readable by anything with device access.
 *
 * §5 defines what we store: a short-lived access JWT (~15 min) and a rotating refresh token
 * (~30 days). The scope claim mirrors the §6 lifecycle state and drives navigation.
 */

const ACCESS_KEY = 'sincere.access_token';
const REFRESH_KEY = 'sincere.refresh_token';

export type Scope = 'onboarding' | 'pending_review' | 'waitlisted' | 'active' | 'admin';

export interface TokenPair {
  accessToken: string;
  refreshToken: string;
}

export interface AccessClaims {
  sub: string;
  scope: Scope;
  gender?: 'male' | 'female';
  region?: string;
  exp: number;
}

export async function saveTokens({ accessToken, refreshToken }: TokenPair): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_KEY, accessToken),
    SecureStore.setItemAsync(REFRESH_KEY, refreshToken),
  ]);
}

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(ACCESS_KEY);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(REFRESH_KEY);
}

export async function clearTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_KEY),
    SecureStore.deleteItemAsync(REFRESH_KEY),
  ]);
}

/**
 * Decode the access token payload without verifying it.
 *
 * The client reads `scope` to decide which screens to mount. This is a UX affordance only —
 * the signature is verified server-side on every request, and §5's scope rules are enforced
 * there. A tampered token here changes what the user sees, never what they can do.
 */
export function decodeAccessToken(token: string): AccessClaims | null {
  try {
    const [, payload] = token.split('.');
    if (!payload) return null;
    const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(normalized.length + ((4 - (normalized.length % 4)) % 4), '=');
    return JSON.parse(globalThis.atob(padded)) as AccessClaims;
  } catch {
    return null;
  }
}

/** True when the token expires within `skewSeconds`. Drives pre-emptive refresh. */
export function isExpiring(claims: AccessClaims, skewSeconds = 60): boolean {
  return claims.exp * 1000 - Date.now() < skewSeconds * 1000;
}
