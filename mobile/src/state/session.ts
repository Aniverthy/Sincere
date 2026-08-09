import { create } from 'zustand';

import { setAuthFailureHandler } from '../api/client';
import {
  clearTokens,
  decodeAccessToken,
  getAccessToken,
  saveTokens,
  type Scope,
  type TokenPair,
} from '../api/tokens';

/**
 * Session store — the client's mirror of the §6 lifecycle state machine.
 *
 * `scope` is the single value the root navigator switches on. That is deliberate: §5 binds
 * token scopes to lifecycle state, so a waitlisted user's matching and chat screens are never
 * mounted at all. Navigation cannot drift from what the server will authorize, because both
 * read the same claim.
 */

export type SessionStatus = 'loading' | 'signed_out' | 'signed_in';

interface SessionState {
  status: SessionStatus;
  userId: string | null;
  scope: Scope | null;
  gender: 'male' | 'female' | null;
  region: string | null;

  /** Read stored tokens on cold start so a returning user skips signup. */
  restore: () => Promise<void>;
  signIn: (tokens: TokenPair) => Promise<void>;
  signOut: () => Promise<void>;
  /** Lifecycle transitions (verification passed, admitted off the waitlist) re-issue tokens
   *  with a new scope; §5 makes the token the source of truth, so we re-read it. */
  applyTokens: (tokens: TokenPair) => Promise<void>;
}

function claimsToState(token: string) {
  const claims = decodeAccessToken(token);
  if (!claims) return null;
  return {
    userId: claims.sub,
    scope: claims.scope,
    gender: claims.gender ?? null,
    region: claims.region ?? null,
  };
}

export const useSession = create<SessionState>((set) => ({
  status: 'loading',
  userId: null,
  scope: null,
  gender: null,
  region: null,

  restore: async () => {
    const token = await getAccessToken();
    if (!token) {
      set({ status: 'signed_out', userId: null, scope: null, gender: null, region: null });
      return;
    }

    const next = claimsToState(token);
    if (!next) {
      // Unreadable token — treat as signed out rather than guessing at a scope.
      await clearTokens();
      set({ status: 'signed_out', userId: null, scope: null, gender: null, region: null });
      return;
    }

    // An expired access token is fine here: the API client refreshes on the first call, and
    // the scope claim we need for navigation is still readable.
    set({ status: 'signed_in', ...next });
  },

  signIn: async (tokens) => {
    await saveTokens(tokens);
    const next = claimsToState(tokens.accessToken);
    set(next ? { status: 'signed_in', ...next } : { status: 'signed_out' });
  },

  applyTokens: async (tokens) => {
    await saveTokens(tokens);
    const next = claimsToState(tokens.accessToken);
    if (next) set({ status: 'signed_in', ...next });
  },

  signOut: async () => {
    await clearTokens();
    set({ status: 'signed_out', userId: null, scope: null, gender: null, region: null });
  },
}));

// A revoked refresh family (§5 reuse detection) ends the session from inside the API client.
setAuthFailureHandler(() => {
  void useSession.getState().signOut();
});
