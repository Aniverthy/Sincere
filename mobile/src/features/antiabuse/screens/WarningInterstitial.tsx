import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Modal, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Card, GlassSurface, Pill } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { antiabuseApi } from '../api';

/**
 * Anti-abuse warning interstitial (FR-5.3, §4).
 * Preserves all warning status and acknowledge logic.
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
    <Modal animationType="fade" transparent visible>
      <View style={styles.modalScrim}>
        <GlassSurface
          tier="floating"
          tint={isFinal ? 'danger' : 'warning'}
          radius={radius.xl}
          sheen
          style={styles.sheetGlass}
        >
          <View style={styles.sheetInner}>
            <View style={styles.badgeRow}>
              <Pill
                label={isFinal ? 'ACCOUNT SUSPENDED' : `WARNING ${warning.occasion_no} OF ${warning.of}`}
                tone={isFinal ? 'danger' : 'warning'}
              />
            </View>

            <Text style={styles.heading}>
              {isFinal ? 'Your account has been suspended' : 'Please slow down'}
            </Text>

            <Body style={styles.messageText}>{warning.message}</Body>

            {!isFinal ? (
              <Card tier="ambient" style={styles.explainCard}>
                <Text style={styles.explainTitle}>WHY THIS MATTERS</Text>
                <Body muted style={styles.explainText}>
                  Sincère gives everyone fifteen people a day precisely so each one gets read.
                  Liking profiles without looking at them makes matches meaningless — for the
                  people you liked, and for you.
                </Body>
              </Card>
            ) : (
              <Card tier="ambient" tint="danger" style={styles.explainCard}>
                <Text style={styles.explainTitle}>WHAT NOW</Text>
                <Body muted style={styles.explainText}>
                  If you believe this is a mistake, contact support@sincere.app and a person will
                  review it.
                </Body>
              </Card>
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
        </GlassSurface>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalScrim: {
    flex: 1,
    backgroundColor: 'rgba(93, 49, 64, 0.90)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  sheetGlass: { width: '100%', maxWidth: 360 },
  sheetInner: { padding: spacing.xl, gap: spacing.md },
  badgeRow: { flexDirection: 'row' },
  heading: { ...typography.displayM, color: colors.warmBeige, lineHeight: 28 },
  messageText: { ...typography.bodyL, color: colors.warmBeige, lineHeight: 22 },
  explainCard: { padding: spacing.md, gap: spacing.xs },
  explainTitle: { ...typography.label, color: colors.text.muted },
  explainText: { ...typography.bodyM, lineHeight: 20 },
  action: { marginTop: spacing.sm },
});
