import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import { useQuery } from '@tanstack/react-query';
import { FlatList, Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { Body, ErrorState, Heading, Loading, Screen } from '../../../components';
import type { RootStackParamList } from '../../../navigation';
import { colors, radius, spacing, typography } from '../../../theme';
import { matchingApi } from '../api';

/** Matches list (§7 ``GET /matches``). Taps through to the chat thread. */
export function MatchesScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['matches'],
    queryFn: matchingApi.matches,
  });

  if (isLoading) return <Loading />;
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
        <Body muted>No matches yet. Today's fifteen are waiting on the Today tab.</Body>
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
        renderItem={({ item }) => (
          <Pressable
            accessibilityRole="button"
            onPress={() =>
              navigation.navigate('Chat', {
                matchId: item.match_id,
                displayName: item.name ?? 'Match',
              })
            }
            style={({ pressed }) => [styles.row, pressed && styles.pressed]}
          >
            {item.photo_url ? (
              <Image source={{ uri: item.photo_url }} style={styles.avatar} />
            ) : (
              <View style={[styles.avatar, styles.avatarPlaceholder]} />
            )}
            <View style={styles.rowText}>
              <Text style={styles.name}>{item.name ?? 'Match'}</Text>
              <Text style={styles.meta}>
                {item.message_count > 0
                  ? `${item.message_count} message${item.message_count === 1 ? '' : 's'}`
                  : 'Say hello'}
              </Text>
            </View>
          </Pressable>
        )}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  list: { gap: spacing.sm, paddingTop: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
  },
  pressed: { opacity: 0.8 },
  avatar: { width: 52, height: 52, borderRadius: radius.pill },
  avatarPlaceholder: { backgroundColor: colors.surfaceRaised },
  rowText: { flex: 1 },
  name: { ...typography.bodyStrong, color: colors.text },
  meta: { ...typography.caption, color: colors.textMuted, marginTop: 2 },
});
