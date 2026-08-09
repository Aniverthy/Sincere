import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Modal, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { antiabuseApi } from '../api';

/**
 * Anti-abuse warning interstitial (FR-5.3, §4).
 *
 * §4 requires these render **distinctly from a ban notice**, so the final occasion changes
 * colour, heading and copy rather than just incrementing a counter.
 *
 * The tone is deliberate. Most people tripping the FR-5.2 dwell rule are swiping carelessly,
 * not maliciously, and the goal is to change the habit — so the copy explains the behaviour
 * and its effect on other people rather than accusing anyone of anything.
 */
export function WarningInterstitial() {
  const queryClient = useQueryClient();
  const [dismissed, setDismissed] = useState(false);
  const [busy, setBusy] = useState(false);

  const { data } = useQuery({
    queryKey: ['warnings-pending'],
    queryFn: antiabuseApi.pending,
    refetchInterval: 60_000,
  });

  const warning = data?.warning;
  if (!warning || dismissed) return null;

  const isFinal = warning.occasion_no >= warning.of;

  const acknowledge = async () => {
    setBusy(true);
    try {
      await antiabuseApi.acknowledge();
      setDismissed(true);
      await queryClient.invalidateQueries({ queryKey: ['warnings-pending'] });
    } catch {
      setDismissed(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal animationType="fade" visible>
      <Screen>
        <View style={styles.body}>
          <View style={[styles.badge, isFinal ? styles.badgeBan : styles.badgeWarn]}>
            <Text style={[styles.badgeText, isFinal ? styles.badgeTextBan : styles.badgeTextWarn]}>
              {isFinal ? 'ACCOUNT SUSPENDED' : `WARNING ${warning.occasion_no} OF ${warning.of}`}
            </Text>
          </View>

          <Text style={styles.heading}>
            {isFinal ? 'Your account has been suspended' : 'Please slow down'}
          </Text>

          <Body>{warning.message}</Body>

          {!isFinal ? (
            <View style={styles.explain}>
              <Text style={styles.explainTitle}>Why this matters</Text>
              <Body muted>
                Sincère gives everyone fifteen people a day precisely so each one gets read.
                Liking profiles without looking at them makes matches meaningless — for the
                people you liked, and for you.
              </Body>
            </View>
          ) : (
            <View style={styles.explain}>
              <Text style={styles.explainTitle}>What now</Text>
              <Body muted>
                If you believe this is a mistake, contact support@sincere.app and a person will
                review it.
              </Body>
            </View>
          )}

          <View style={styles.action}>
            <Button
              label={isFinal ? 'I understand' : 'Got it'}
              onPress={() => void acknowledge()}
              loading={busy}
              variant={isFinal ? 'danger' : 'primary'}
            />
          </View>
        </View>
      </Screen>
    </Modal>
  );
}

const styles = StyleSheet.create({
  body: { flex: 1, justifyContent: 'center', gap: spacing.md },
  badge: {
    alignSelf: 'flex-start',
    borderRadius: radius.pill,
    borderWidth: 1,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  badgeWarn: { backgroundColor: '#3A2E1B', borderColor: colors.warning },
  badgeBan: { backgroundColor: '#3A1E1E', borderColor: colors.danger },
  badgeText: { ...typography.label },
  badgeTextWarn: { color: colors.warning },
  badgeTextBan: { color: colors.danger },
  heading: { ...typography.title, color: colors.text },
  explain: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    gap: spacing.xs,
  },
  explainTitle: { ...typography.label, color: colors.textFaint },
  action: { marginTop: spacing.md },
});
