import { StyleSheet, Text, View } from 'react-native';

import { Body, Button, Card, Heading, Screen } from '../../../components';
import { useSession } from '../../../state/session';
import { colors, spacing, typography } from '../../../theme';

/**
 * Auto-reject terminal state (FR-1.6). §6 makes this a terminal lifecycle node.
 *
 * The copy offers a real route to a human. FR-1.4 already guarantees a duplicate face never
 * reaches this screen automatically, but a rejection is still occasionally going to be wrong,
 * and a dead end with no appeal would be indefensible.
 */
export function RejectedScreen() {
  const signOut = useSession((s) => s.signOut);

  return (
    <Screen scroll>
      <Heading sub="We could not verify this account.">Verification unsuccessful</Heading>

      <Card style={styles.card}>
        <Text style={styles.cardTitle}>Common reasons</Text>
        <Reason text="The face in the video was not clearly visible — poor light, or too far away." />
        <Reason text="The profile photos did not appear to be the same person as the video." />
        <Reason text="The verification prompts were not followed in the order shown." />
      </Card>

      <View style={styles.appeal}>
        <Body>
          If you believe this is a mistake, contact us and a person will look at it. We would
          rather review a real account twice than turn one away.
        </Body>
        <Text style={styles.email}>support@sincere.app</Text>
      </View>

      <Button label="Sign out" variant="secondary" onPress={() => void signOut()} />
    </Screen>
  );
}

function Reason({ text }: { text: string }) {
  return (
    <View style={styles.reason}>
      <Text style={styles.bullet}>·</Text>
      <Text style={styles.reasonText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.xs, marginBottom: spacing.lg },
  cardTitle: { ...typography.label, color: colors.textFaint, marginBottom: spacing.xs },
  reason: { flexDirection: 'row', gap: spacing.sm },
  bullet: { ...typography.body, color: colors.textFaint },
  reasonText: { ...typography.caption, color: colors.textMuted, flex: 1 },
  appeal: { gap: spacing.sm, marginBottom: spacing.lg },
  email: { ...typography.bodyStrong, color: colors.primary },
});
