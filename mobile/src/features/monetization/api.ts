import { api } from '../../api/client';

/** Monetization endpoints (§7 Monetization). */

export interface Plan {
  tier: 'basic_pro' | 'pro_plus';
  name: string;
  price_paise: number;
  period: string;
  daily_matches: number;
  features: { label: string; included: boolean }[];
}

export interface Plans {
  plans: Plan[];
  free_tier_daily_matches: number;
  /** FR-6.4: base access is free forever for active users — never revoked. */
  free_tier_note: string;
}

export interface Subscription {
  tier: 'basic_pro' | 'pro_plus' | null;
  status: string;
  renews_at: string | null;
  daily_matches: number;
  boosted: boolean;
}

export const monetizationApi = {
  plans: () => api.get<Plans>('/pro/plans'),
  subscription: () => api.get<Subscription>('/pro/subscription'),

  subscribe: (tier: Plan['tier'], billingState: string) =>
    api.post<{ checkout_url: string; amount_paise: number }>('/pro/subscribe', {
      tier,
      billing_state: billingState,
      idempotency_key: `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
    }),

  cancel: () => api.delete<Subscription>('/pro/subscription'),

  /** FR-6.3: 403 unless the caller is a Pro-subscribed woman. */
  entryTier: (userId: string) =>
    api.get<{ entry_tier: string | null; note: string }>(`/profiles/${userId}/entry-tier`),
};
