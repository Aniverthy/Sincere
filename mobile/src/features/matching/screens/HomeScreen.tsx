import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../../api/client';
import { Body, Card, ErrorState, GlassSurface, Loading, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { matchingApi, type DailyCandidate } from '../api';
import { SwipeDeck } from '../components/SwipeDeck';

/**
 * Home — the daily 15 (FR-3.1; 30 / 40+ on Pro per FR-6.1).
 * Preserves all matchingApi calls and dwell timer logic.
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
        // Dwell recorded or reconciled on next focus
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

  if (index >= candidates.length || candidates.length === 0) {
    return (
      <Screen>
        <View style={styles.emptyContainer}>
          <Card tier="raised" style={styles.emptyCard}>
            <Text style={styles.emptyTitle}>That is everyone for today</Text>
            <Body muted style={styles.emptyBody}>
              {data?.message ??
                'Fifteen people, once a day. Come back tomorrow — or widen your radius in Me.'}
            </Body>
          </Card>
        </View>
      </Screen>
    );
  }

  return (
    <Screen>
      {/* Floating Counter Header Pill */}
      <View style={styles.counterHeader}>
        <GlassSurface tier="ambient" radius={radius.pill} style={styles.counterGlass}>
          <View style={styles.counterInner}>
            <Text style={styles.counterText}>
              {index + 1} of {candidates.length}
            </Text>
          </View>
        </GlassSurface>
      </View>

      <SwipeDeck candidates={candidates} currentIndex={index} onSwipe={onSwipe} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  counterHeader: { alignItems: 'center', marginBottom: spacing.sm, zIndex: 10 },
  counterGlass: { paddingHorizontal: spacing.md, paddingVertical: 4 },
  counterInner: { alignItems: 'center', justifyContent: 'center' },
  counterText: { ...typography.label, color: colors.warmBeige },

  emptyContainer: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  emptyCard: { width: '100%', maxWidth: 340, alignItems: 'center', textAlign: 'center' },
  emptyTitle: { ...typography.displayM, color: colors.warmBeige, textAlign: 'center' },
  emptyBody: { textAlign: 'center', marginTop: spacing.sm },
});
