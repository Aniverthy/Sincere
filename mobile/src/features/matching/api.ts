import { api } from '../../api/client';

/** Matching endpoints (§7 Matching & Swipes). */

export interface DailyCandidate {
  user_id: string;
  name: string | null;
  age: number | null;
  bio: string | null;
  prompts: { q: string; a: string }[];
  tags: string[];
  photos: { url: string }[];
  distance_km: number | null;
  /** FR-6.2: when true the UI MUST render the "Boosted" label. */
  boosted: boolean;
}

export interface DailyBatch {
  batch_date: string;
  candidates: DailyCandidate[];
  total: number;
  remaining: number;
  message?: string | null;
}

export interface SwipeResult {
  matched: boolean;
  match_id: string | null;
  remaining_today: number;
  warning?: { occasion_no: number; of: number; message: string } | null;
}

export interface MatchSummary {
  match_id: string;
  user_id: string;
  name: string | null;
  photo_url: string | null;
  formed_at: string;
  last_message_at: string | null;
  message_count: number;
}

export const matchingApi = {
  daily: () => api.get<DailyBatch>('/matches/daily'),

  /**
   * §4: the client timestamps profile-visible -> swipe and sends `dwell_ms`.
   * §18 treats it as untrusted and cross-checks it server-side, so there is no point
   * inflating it — but there is every point measuring it honestly.
   */
  swipe: (targetId: string, direction: 'left' | 'right', dwellMs: number) =>
    api.post<SwipeResult>('/swipes', {
      target_id: targetId,
      direction,
      dwell_ms: Math.max(0, Math.round(dwellMs)),
    }),

  matches: () => api.get<{ matches: MatchSummary[]; total: number }>('/matches'),

  unmatch: (matchId: string) =>
    api.delete<{ match_id: string; messages_purge_after: string; message: string }>(
      `/matches/${matchId}`,
    ),
};
