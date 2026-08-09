import { api } from '../../api/client';

/** Anti-abuse endpoints (FR-5.3 warning ledger). */

export interface Warning {
  occasion_no: number;
  of: number;
  message: string;
  issued_at: string | null;
}

export const antiabuseApi = {
  pending: () => api.get<{ warning: Warning | null }>('/warnings/pending'),

  /** Acknowledgement is required: FR-5.3's escalation is only fair if each step was seen. */
  acknowledge: () => api.post<{ status: string }>('/warnings/acknowledge'),
};
