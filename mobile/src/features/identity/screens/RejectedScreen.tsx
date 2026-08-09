import { StyleSheet, Text, View } from 'react-native';

import { Body, Button, Card, Heading, Screen } from '../../../components';
import { useSession } from '../../../state/session';
import { colors, spacing, typography } from '../../../theme';

/**
 * Auto-reject terminal state (FR-1.6).
 * Styled with neutral slate / warmBeige glass only (no Rose accents).
 */
export function RejectedScreen() {
  const signOut = useSession((s) => s.signOut);

  return (
    <Screen scroll>
      <Heading sub="We could not verify this account.">Verification unsuccessful</Heading>

      <Card tier="raised" tint="neutral" style={styles.card}>
        <Text style={styles.cardTitle}>COMMON REASONS</Text>
        <Reason text="The face in the video was not clearly visible — poor light, or too far away." />
        <Reason text="The profile photos did not appear to be the same person as the video." />
        <Reason text="The verification prompts were not followed in the order shown." />
      </Card>

      <View style={styles.appeal}>
        <Body muted>
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
    <View style={styles.reasonRow}>
      <Text style={styles.bullet}>•</Text>
      <Text style={styles.reasonText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.sm, marginBottom: spacing.lg },
  cardTitle: { ...typography.label, color: colors.passSlate, marginBottom: spacing.xs },
  reasonRow: { flexDirection: 'row', gap: spacing.sm },
  bullet: { ...typography.bodyL, color: colors.passSlate },
  reasonText: { ...typography.bodyM, color: colors.text.muted, flex: 1 },
  appeal: { gap: spacing.sm, marginBottom: spacing.xl },
  email: { ...typography.bodyL, color: colors.rose[300], textDecorationLine: 'underline', marginTop: spacing.xs },
});
