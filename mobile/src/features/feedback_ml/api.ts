import { api } from '../../api/client';

/** We-Met endpoints (§7 We Met). */

export type WeMetAnswer = 'met_yes' | 'met_no_yet' | 'not_going_to';

export interface Prompt {
  prompt_id: string;
  match_id: string;
  other_user_id: string;
  other_name: string | null;
  triggered_at: string;
  question: string;
  /** 0 on the first ask; increments on each 1-2 week re-ask (FR-4.3). */
  reask_number: number;
}

export const feedbackApi = {
  pending: () => api.get<{ prompts: Prompt[] }>('/wemet/pending'),

  respond: (promptId: string, response: WeMetAnswer, note?: string) =>
    api.post<{ recorded: boolean; next_reask_at: string | null; message: string }>(
      `/wemet/${promptId}/response`,
      { response, note },
    ),
};
