import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../../api/client';
import { Body, BoostedBadge, Button, Card, ErrorState, Loading, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { matchingApi, type DailyCandidate } from '../api';

/**
 * Home — the daily 15 (FR-3.1; 30 / 40+ on Pro per FR-6.1).
 *
 * §19 makes the fetch a pure lookup: the batch was precomputed nightly, so this is fast by
 * construction rather than by optimization.
 *
 * The dwell timer is the piece carrying product logic (§4): the client marks when a profile
 * became visible and sends the elapsed time with the swipe. FR-5.2 evaluates it, and §18
 * cross-checks it server-side because the client is untrusted.
 */
export function HomeScreen() {
  const queryClient = useQueryClient();
  const [index, setIndex] = useState(0);
  const shownAt = useRef<number>(Date.now());

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['daily'],
    queryFn: matchingApi.daily,
  });

  const advance = useCallback(() => {
    setIndex((i) => i + 1);
    shownAt.current = Date.now();
  }, []);

  const onSwipe = useCallback(
    async (candidate: DailyCandidate, direction: 'left' | 'right') => {
      const dwellMs = Date.now() - shownAt.current;
      advance();
      try {
        const result = await matchingApi.swipe(candidate.user_id, direction, dwellMs);
        if (result.matched) {
          await queryClient.invalidateQueries({ queryKey: ['matches'] });
        }
      } catch {
        // The swipe is recorded server-side or it is not; either way the card has moved on.
        // Re-fetching on the next screen focus reconciles any divergence.
      }
    },
    [advance, queryClient],
  );

  if (isLoading) return <Loading label="Finding your fifteen" />;

  if (error) {
    const detail = error instanceof ApiError ? error.problem.detail : undefined;
    return (
      <Screen>
        <ErrorState title="Could not load today's matches" detail={detail} onRetry={refetch} />
      </Screen>
    );
  }

  const candidates = data?.candidates ?? [];
  const candidate = candidates[index];

  if (!candidate) {
    return (
      <Screen>
        <View style={styles.empty}>
          <Text style={styles.emptyTitle}>That is everyone for today</Text>
          <Body muted>
            {data?.message ??
              'Fifteen people, once a day. Come back tomorrow — or widen your radius in Me.'}
          </Body>
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      <View style={styles.counter}>
        <Text style={styles.counterText}>
          {index + 1} of {candidates.length}
        </Text>
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        <Card style={styles.card}>
          {candidate.photos[0]?.url ? (
            <Image source={{ uri: candidate.photos[0].url }} style={styles.photo} />
          ) : (
            <View style={[styles.photo, styles.photoPlaceholder]} />
          )}

          <View style={styles.identity}>
            <Text style={styles.name}>
              {candidate.name ?? 'Someone'}
              {candidate.age ? <Text style={styles.age}>, {candidate.age}</Text> : null}
            </Text>
            {/* FR-6.2 (DECIDED): boosted profiles must be labelled to viewers. */}
            {candidate.boosted ? <BoostedBadge /> : null}
          </View>

          {candidate.bio ? <Text style={styles.bio}>{candidate.bio}</Text> : null}

          {candidate.prompts.map((prompt) => (
            <View key={prompt.q} style={styles.prompt}>
              <Text style={styles.promptQuestion}>{prompt.q}</Text>
              <Text style={styles.promptAnswer}>{prompt.a}</Text>
            </View>
          ))}

          {candidate.tags.length ? (
            <View style={styles.tags}>
              {candidate.tags.map((tag) => (
                <View key={tag} style={styles.tag}>
                  <Text style={styles.tagText}>{tag}</Text>
                </View>
              ))}
            </View>
          ) : null}
        </Card>
      </ScrollView>

      <View style={styles.actions}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Pass"
          onPress={() => onSwipe(candidate, 'left')}
          style={[styles.action, styles.pass]}
        >
          <Text style={styles.actionLabel}>Pass</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Like"
          onPress={() => onSwipe(candidate, 'right')}
          style={[styles.action, styles.like]}
        >
          <Text style={[styles.actionLabel, styles.likeLabel]}>Like</Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  counter: { alignItems: 'center', marginBottom: spacing.sm },
  counterText: { ...typography.label, color: colors.textFaint },
  card: { padding: 0, overflow: 'hidden' },
  photo: { width: '100%', height: 380, backgroundColor: colors.surfaceRaised },
  photoPlaceholder: { backgroundColor: colors.surfaceRaised },
  identity: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.md,
  },
  name: { ...typography.title, color: colors.text },
  age: { ...typography.title, color: colors.textMuted, fontWeight: '400' },
  bio: {
    ...typography.body,
    color: colors.text,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
  },
  prompt: { paddingHorizontal: spacing.md, paddingTop: spacing.md },
  promptQuestion: { ...typography.caption, color: colors.textFaint },
  promptAnswer: { ...typography.body, color: colors.text, marginTop: 2 },
  tags: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.xs,
    padding: spacing.md,
  },
  tag: {
    backgroundColor: colors.surfaceRaised,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  tagText: { ...typography.caption, color: colors.textMuted },
  actions: { flexDirection: 'row', gap: spacing.md, paddingTop: spacing.md },
  action: {
    flex: 1,
    minHeight: 54,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pass: { backgroundColor: colors.surfaceRaised, borderWidth: 1, borderColor: colors.border },
  like: { backgroundColor: colors.primary },
  actionLabel: { ...typography.bodyStrong, color: colors.text },
  likeLabel: { color: colors.textInverse },
  empty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.sm },
  emptyTitle: { ...typography.heading, color: colors.text, textAlign: 'center' },
});
