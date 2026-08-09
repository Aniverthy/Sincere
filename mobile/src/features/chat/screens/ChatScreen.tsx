import type { RouteProp } from '@react-navigation/native';
import { useRoute } from '@react-navigation/native';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors, radius, spacing, typography } from '../../../theme';
import type { RootStackParamList } from '../../../navigation';
import { ChatSocket, chatApi, type Message } from '../api';

/**
 * Chat thread (FR-4.1).
 *
 * §4: WebSocket while the app is open, with `?after=` delta sync on reconnect. Sends go over
 * the socket when it is open and fall back to REST when it is not, so a flaky connection
 * degrades rather than blocks.
 */
export function ChatScreen() {
  const route = useRoute<RouteProp<RootStackParamList, 'Chat'>>();
  const { matchId } = route.params;

  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const socketRef = useRef<ChatSocket | null>(null);
  const lastAt = useRef<string | undefined>(undefined);

  const sync = useCallback(async () => {
    const page = await chatApi.history(matchId, lastAt.current);
    if (!page.messages.length) return;

    setMessages((existing) => {
      const seen = new Set(existing.map((m) => m.message_id));
      const merged = [...existing, ...page.messages.filter((m) => !seen.has(m.message_id))];
      return merged.sort((a, b) => a.sent_at.localeCompare(b.sent_at));
    });
    lastAt.current = page.next_after ?? lastAt.current;
  }, [matchId]);

  useEffect(() => {
    void sync();

    const socket = new ChatSocket(
      (frame) => {
        if (frame.type !== 'message' || frame.match_id !== matchId) return;
        const data = frame.data as unknown as {
          message_id: string;
          sender_id: string;
          body: string;
          sent_at: string;
        };
        setMessages((existing) =>
          existing.some((m) => m.message_id === data.message_id)
            ? existing
            : [
                ...existing,
                {
                  message_id: data.message_id,
                  match_id: matchId,
                  sender_id: data.sender_id,
                  body: data.body,
                  sent_at: data.sent_at,
                  delivered_at: null,
                  read_at: null,
                  mine: false,
                },
              ],
        );
        lastAt.current = data.sent_at;
      },
      // §4: on reconnect, delta-sync rather than assume nothing was missed.
      () => void sync(),
    );

    socketRef.current = socket;
    void socket.connect();
    return () => socket.close();
  }, [matchId, sync]);

  const send = useCallback(async () => {
    const body = draft.trim();
    if (!body || sending) return;

    setDraft('');
    setSendError(null);
    setSending(true);
    const clientId = `${Date.now()}`;

    // Optimistic bubble, reconciled by message_id when the server echoes it back.
    setMessages((existing) => [
      ...existing,
      {
        message_id: clientId,
        match_id: matchId,
        sender_id: 'me',
        body,
        sent_at: new Date().toISOString(),
        delivered_at: null,
        read_at: null,
        mine: true,
      },
    ]);

    try {
      const overSocket = socketRef.current?.send({
        type: 'message',
        match_id: matchId,
        data: { body, client_id: clientId },
      });
      if (!overSocket) {
        const saved = await chatApi.send(matchId, body, clientId);
        setMessages((existing) =>
          existing.map((m) => (m.message_id === clientId ? { ...saved, mine: true } : m)),
        );
      }
    } catch {
      // Put the text back in the box rather than losing it, and say why it is back.
      setMessages((existing) => existing.filter((m) => m.message_id !== clientId));
      setDraft(body);
      setSendError('That message did not send. Check your connection and try again.');
    } finally {
      setSending(false);
    }
  }, [draft, matchId, sending]);

  return (
    <SafeAreaView style={styles.screen} edges={['bottom']}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <FlatList
          data={messages}
          keyExtractor={(item) => item.message_id}
          contentContainerStyle={styles.list}
          renderItem={({ item }) => (
            <View style={[styles.bubble, item.mine ? styles.mine : styles.theirs]}>
              <Text style={styles.bubbleText}>{item.body}</Text>
            </View>
          )}
        />

        {sendError ? <Text style={styles.sendError}>{sendError}</Text> : null}

        <View style={styles.composer}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder="Say something"
            placeholderTextColor={colors.textFaint}
            style={styles.input}
            multiline
            maxLength={2000}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send"
            onPress={() => void send()}
            disabled={!draft.trim() || sending}
            style={[styles.send, (!draft.trim() || sending) && styles.sendDisabled]}
          >
            <Text style={styles.sendLabel}>Send</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  flex: { flex: 1 },
  list: { padding: spacing.md, gap: spacing.sm },
  bubble: {
    maxWidth: '78%',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.lg,
  },
  mine: { alignSelf: 'flex-end', backgroundColor: colors.primary },
  theirs: { alignSelf: 'flex-start', backgroundColor: colors.surfaceRaised },
  bubbleText: { ...typography.body, color: colors.text },
  composer: {
    flexDirection: 'row',
    gap: spacing.sm,
    padding: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    alignItems: 'flex-end',
  },
  input: {
    flex: 1,
    maxHeight: 120,
    minHeight: 44,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    ...typography.body,
  },
  send: {
    minHeight: 44,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendDisabled: { opacity: 0.4 },
  sendLabel: { ...typography.bodyStrong, color: colors.textInverse },
  sendError: {
    ...typography.caption,
    color: colors.danger,
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xs,
  },
});
