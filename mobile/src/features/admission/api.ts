import { api } from '../../api/client';

/** Admission endpoints (§7 Queue, Waitlist, Auction). */

export interface QueueStatus {
  region: string;
  admission_state: 'open' | 'frozen';
  tier: 'free' | 'paid' | 'auction' | null;
  position: number | null;
  waitlist_size: number;
  slots_available: number;
  active_men: number;
  active_women: number;
  estimated_days: number | null;
  /** FR-2.11 — surfaced so the UI can state it rather than let users assume otherwise. */
  paid_entry_affects_ranking: boolean;
  message: string;
}

export interface AuctionToday {
  region: string;
  status: 'scheduled' | 'open' | 'settling' | 'settled';
  window_start: string;
  window_end: string;
  slots: number;
  min_bid_paise: number;
  standing_requirement_paise: number;
  /** §7: anonymized — rank and amount only, never a user id. */
  top_bids: { rank: number; amount_paise: number; is_you: boolean }[];
  your_bid_paise: number | null;
  your_rank: number | null;
}

const idempotencyKey = () =>
  `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

export const admissionApi = {
  status: () => api.get<QueueStatus>('/queue/status'),

  /** §7:391 requires an idempotency key — a retried checkout must not charge twice. */
  paidCheckout: () =>
    api.post<{ payment_id: string; amount_paise: number; checkout_url: string }>(
      '/queue/paid/checkout',
      { idempotency_key: idempotencyKey() },
    ),

  auctionToday: () => api.get<AuctionToday>('/auction/today'),

  bid: (amountPaise: number) =>
    api.post<AuctionToday>('/auction/bid', {
      amount_paise: amountPaise,
      idempotency_key: idempotencyKey(),
    }),

  auctionResult: () =>
    api.get<{ you_won: boolean; message: string; refund_status: string | null }>(
      '/auction/result',
    ),
};
