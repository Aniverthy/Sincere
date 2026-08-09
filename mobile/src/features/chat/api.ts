import { api } from '../../api/client';
import { config } from '../../config';
import { getAccessToken } from '../../api/tokens';

/** Chat endpoints and the WebSocket client (§7 Chat, §4 client responsibilities). */

export interface Message {
  message_id: string;
  match_id: string;
  sender_id: string;
  body: string;
  sent_at: string;
  delivered_at: string | null;
  read_at: string | null;
  mine: boolean;
}

export interface MessagePage {
  match_id: string;
  messages: Message[];
  has_more: boolean;
  next_after: string | null;
}

export const chatApi = {
  /** §4: history, or the reconnect delta when `after` is supplied. */
  history: (matchId: string, after?: string) =>
    api.get<MessagePage>(`/matches/${matchId}/messages`, { query: { after } }),

  send: (matchId: string, body: string, clientId?: string) =>
    api.post<Message>(`/matches/${matchId}/messages`, { body, client_id: clientId }),

  report: (matchId: string, reason: string) =>
    api.post<{ retention_hold: boolean; message: string }>(`/matches/${matchId}/report`, {
      reason,
    }),
};

type Frame = { type: string; match_id?: string; data?: Record<string, unknown> };

/**
 * WebSocket client for `/ws/chat`.
 *
 * §5: the access JWT is presented at connect and the connection is dropped on expiry, so the
 * client "silently reconnects after refresh". React Native's WebSocket cannot set headers,
 * which is why the token rides in the query string — the server accepts both.
 *
 * On reconnect the caller delta-syncs with `?after=` (§4) rather than trusting that nothing
 * was missed while the socket was down.
 */
export class ChatSocket {
  private socket: WebSocket | null = null;
  private closedByUs = false;
  private attempt = 0;

  constructor(
    private readonly onFrame: (frame: Frame) => void,
    private readonly onReconnect: () => void,
  ) {}

  async connect(): Promise<void> {
    const token = await getAccessToken();
    if (!token) return;

    this.closedByUs = false;
    this.socket = new WebSocket(`${config.wsUrl}?token=${encodeURIComponent(token)}`);

    this.socket.onmessage = (event) => {
      try {
        this.onFrame(JSON.parse(String(event.data)) as Frame);
      } catch {
        // A malformed frame is not worth tearing the socket down for.
      }
    };

    this.socket.onopen = () => {
      if (this.attempt > 0) this.onReconnect();
      this.attempt = 0;
    };

    this.socket.onclose = () => {
      if (this.closedByUs) return;
      // Exponential backoff, capped. An expired token closes the socket, and the API client
      // will have refreshed it by the time we retry.
      this.attempt += 1;
      const delay = Math.min(1000 * 2 ** this.attempt, 15_000);
      setTimeout(() => void this.connect(), delay);
    };
  }

  send(frame: Frame): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(frame));
    return true;
  }

  close(): void {
    this.closedByUs = true;
    this.socket?.close();
    this.socket = null;
  }
}
