import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useQuery } from '@tanstack/react-query';
import { FlatList, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { Body, Card, ErrorState, GlassSurface, Heading, Loading, Screen } from '../../../components';
import type { RootStackParamList } from '../../../navigation';
import { colors, radius, spacing, typography } from '../../../theme';
import { matchingApi } from '../api';

/** Matches list (§7 GET /matches). Preserves navigation and query logic. */
export function MatchesScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['matches'],
    queryFn: matchingApi.matches,
  });

  if (isLoading) return <Loading label="Loading matches" />;
  if (error) {
    return (
      <Screen>
        <ErrorState title="Could not load your matches" onRetry={refetch} />
      </Screen>
    );
  }

  const matches = data?.matches ?? [];

  if (!matches.length) {
    return (
      <Screen>
        <Heading sub="When someone you liked likes you back, they appear here.">Matches</Heading>
        <Card tier="raised" style={styles.emptyCard}>
          <Body muted style={styles.emptyText}>
            No matches yet. Today's fifteen are waiting on the Today tab.
          </Body>
        </Card>
      </Screen>
    );
  }

  return (
    <Screen>
      <Heading>Matches</Heading>
      <FlatList
        data={matches}
        keyExtractor={(item) => item.match_id}
        contentContainerStyle={styles.list}
        showsVerticalScrollIndicator={false}
        renderItem={({ item }) => {
          const hasUnread = item.message_count > 0;
          return (
            <Pressable
              accessibilityRole="button"
              onPress={() =>
                navigation.navigate('Chat', {
                  matchId: item.match_id,
                  displayName: item.name ?? 'Match',
                })
              }
              style={({ pressed }) => [styles.rowWrapper, pressed && styles.pressed]}
            >
              <GlassSurface tier="ambient" radius={radius.lg} style={styles.rowGlass}>
                <View style={styles.rowInner}>
                  <View style={[styles.avatarRing, hasUnread && styles.avatarRingActive]}>
                    {item.photo_url ? (
                      <Image source={{ uri: item.photo_url }} style={styles.avatar} />
                    ) : (
                      <View style={[styles.avatar, styles.avatarPlaceholder]}>
                        <Text style={styles.avatarInitial}>{item.name?.[0] ?? 'M'}</Text>
                      </View>
                    )}
                  </View>

                  <View style={styles.rowText}>
                    <Text style={styles.name}>{item.name ?? 'Match'}</Text>
                    <Text style={styles.meta}>
                      {hasUnread
                        ? `${item.message_count} message${item.message_count === 1 ? '' : 's'}`
                        : 'Say hello'}
                    </Text>
                  </View>
                </View>
              </GlassSurface>
            </Pressable>
          );
        }}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.sm, paddingTop: spacing.xs, paddingBottom: 100 },
  rowWrapper: { width: '100%' },
  rowGlass: { width: '100%' },
  rowInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    padding: spacing.md,
  },
  pressed: { opacity: 0.85 },
  avatarRing: {
    padding: 2,
    borderRadius: radius.pill,
    backgroundColor: 'transparent',
  },
  avatarRingActive: {
    backgroundColor: colors.rose[500],
  },
  avatar: { width: 52, height: 52, borderRadius: 26 },
  avatarPlaceholder: {
    backgroundColor: 'rgba(255,255,255,0.08)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarInitial: { fontFamily: 'Fraunces_600SemiBold', fontSize: 20, color: colors.warmBeige },

  rowText: { flex: 1 },
  name: { ...typography.bodyL, fontFamily: 'Manrope_600SemiBold', color: colors.warmBeige },
  meta: { ...typography.bodyM, color: colors.text.muted, marginTop: 2 },

  emptyCard: { marginTop: spacing.md, padding: spacing.lg, alignItems: 'center' },
  emptyText: { textAlign: 'center' },
});
