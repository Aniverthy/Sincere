import { api } from '../../api/client';
import type { TokenPair } from '../../api/tokens';

/** Identity endpoints (§7 Identity & Verification, Profile & Location). */

export type UserStatus =
  | 'onboarding'
  | 'pending_review'
  | 'rejected'
  | 'waitlisted'
  | 'active'
  | 'banned'
  | 'grace_period';

export interface SignupResult {
  challenge_id: string;
  expires_in: number;
  /** Only populated when SMS_PROVIDER=console in dev. Never in production. */
  dev_otp?: string | null;
}

export interface TokenResult {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  scope: string;
  status: UserStatus;
}

export interface Profile {
  user_id: string;
  status: UserStatus;
  gender: 'male' | 'female';
  name: string | null;
  dob: string | null;
  bio: string | null;
  prompts: { q: string; a: string }[];
  tags: string[];
  photos: { url: string; object_key: string }[];
  radius_km: number;
  h3_region: string | null;
}

export interface LivenessSession {
  session_id: string;
  /** §5: randomized per session, so a replayed recording of someone else's fails. */
  prompt_sequence: string[];
  upload_url: string;
  object_key: string;
  expires_at: string;
}

export interface VerificationStatus {
  status: UserStatus;
  band: 'auto_approve' | 'review' | 'auto_reject' | null;
  submitted_at: string | null;
  decided_at: string | null;
  message: string;
}

export const identityApi = {
  signup: (phone: string) =>
    api.post<SignupResult>('/auth/signup', { phone }, { skipAuth: true }),

  verifyOtp: (challengeId: string, otp: string, deviceFingerprint?: string) =>
    api.post<TokenResult>(
      '/auth/verify-otp',
      { challenge_id: challengeId, otp, device_fingerprint: deviceFingerprint },
      { skipAuth: true },
    ),

  me: () => api.get<Profile>('/me'),

  updateProfile: (changes: Partial<Omit<Profile, 'user_id' | 'status' | 'gender'>>) =>
    api.patch<Profile>('/me', changes),

  /** Gender is write-once: it decides which pool the ratio admits you against (FR-2.4). */
  setGender: (gender: 'male' | 'female') =>
    api.post<Profile>(`/me/gender?gender=${gender}`),

  setRadius: (radiusKm: number) => api.patch<Profile>('/me/radius', { radius_km: radiusKm }),

  /** FR-3.3: sent on every app open. §18: overwrites, keeps no history. */
  setLocation: (latitude: number, longitude: number) =>
    api.post<{ h3_region: string }>('/me/location', { latitude, longitude }),

  photoUploadUrl: (contentType: 'image/jpeg' | 'image/png') =>
    api.post<{
      upload_url: string;
      object_key: string;
      /** Where the photo is readable once uploaded. Absolute, resolved against this
       *  request's host — so a phone gets the dev machine's LAN address, not localhost. */
      public_url: string | null;
    }>('/me/photos/upload-url', { content_type: contentType }),

  startLiveness: () => api.post<LivenessSession>('/verification/liveness/session'),

  submitLiveness: (sessionId: string, objectKey: string) =>
    api.post<VerificationStatus>('/verification/liveness', {
      session_id: sessionId,
      object_key: objectKey,
    }),

  verificationStatus: () => api.get<VerificationStatus>('/verification/status'),

  deleteAccount: () =>
    api.delete<{ restorable_until: string; message: string }>('/me'),
};

export type { TokenPair };
