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
import * as Haptics from 'expo-haptics';

import { GlassSurface } from '../../../components';
import type { RootStackParamList } from '../../../navigation';
import { colors, radius, spacing, typography } from '../../../theme';
import { ChatSocket, chatApi, type Message } from '../api';

/**
 * Chat thread (FR-4.1).
 * Preserves WebSocket handling, delta sync, and REST fallback logic.
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
      () => void sync(),
    );

    socketRef.current = socket;
    void socket.connect();
    return () => socket.close();
  }, [matchId, sync]);

  const send = useCallback(async () => {
    const body = draft.trim();
    if (!body || sending) return;

    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setDraft('');
    setSendError(null);
    setSending(true);
    const clientId = `${Date.now()}`;

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
      setMessages((existing) => existing.filter((m) => m.message_id !== clientId));
      setDraft(body);
      setSendError('That message did not send. Check your connection and try again.');
    } finally {
      setSending(false);
    }
  }, [draft, matchId, sending]);

  const canSend = draft.trim().length > 0 && !sending;

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
            <View style={[styles.bubbleWrapper, item.mine ? styles.mineWrapper : styles.theirsWrapper]}>
              <GlassSurface
                tier="raised"
                tint={item.mine ? 'rose' : 'neutral'}
                radius={radius.lg}
                style={styles.bubbleGlass}
              >
                <View style={styles.bubbleInner}>
                  <Text style={[styles.bubbleText, item.mine ? styles.mineText : styles.theirsText]}>
                    {item.body}
                  </Text>
                </View>
              </GlassSurface>
            </View>
          )}
        />

        {sendError ? <Text style={styles.sendError}>{sendError}</Text> : null}

        {/* Floating Glass Composer Bar */}
        <View style={styles.composerContainer}>
          <GlassSurface tier="raised" radius={radius.pill} style={styles.composerGlass}>
            <View style={styles.composerInner}>
              <TextInput
                value={draft}
                onChangeText={setDraft}
                placeholder="Say something sincere..."
                placeholderTextColor={colors.text.muted}
                style={styles.input}
                multiline
                maxLength={2000}
              />
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Send message"
                onPress={() => void send()}
                disabled={!canSend}
                style={styles.sendButton}
              >
                <GlassSurface
                  tier="floating"
                  tint={canSend ? 'rose' : 'neutral'}
                  radius={20}
                  style={[styles.sendGlass, !canSend && styles.sendDisabled]}
                >
                  <View style={styles.sendInner}>
                    <Text style={[styles.sendArrow, canSend && styles.sendArrowActive]}>↑</Text>
                  </View>
                </GlassSurface>
              </Pressable>
            </View>
          </GlassSurface>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg.wine },
  flex: { flex: 1 },
  list: { padding: spacing.md, gap: spacing.md, paddingBottom: 80 },

  bubbleWrapper: { maxWidth: '78%' },
  mineWrapper: { alignSelf: 'flex-end' },
  theirsWrapper: { alignSelf: 'flex-start' },
  bubbleGlass: { width: '100%' },
  bubbleInner: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  bubbleText: { ...typography.bodyL, lineHeight: 22 },
  mineText: { color: colors.text.onRose },
  theirsText: { color: colors.warmBeige },

  composerContainer: { padding: spacing.md },
  composerGlass: { width: '100%' },
  composerInner: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: 4,
    minHeight: 52,
  },
  input: {
    flex: 1,
    maxHeight: 100,
    minHeight: 40,
    ...typography.bodyL,
    color: colors.warmBeige,
    paddingVertical: spacing.xs,
  },
  sendButton: { marginLeft: spacing.sm },
  sendGlass: { width: 40, height: 40, borderRadius: 20 },
  sendDisabled: { opacity: 0.35 },
  sendInner: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  sendArrow: { fontSize: 20, fontFamily: 'Manrope_700Bold', color: colors.text.muted },
  sendArrowActive: { color: colors.text.onRose },

  sendError: {
    ...typography.caption,
    color: colors.dangerRed,
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.xs,
  },
});
