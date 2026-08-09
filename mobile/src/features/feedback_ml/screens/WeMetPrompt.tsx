import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Modal, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Card, GlassSurface } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { feedbackApi, type WeMetAnswer } from '../api';

/**
 * We-Met prompt (FR-4.3, FR-4.4).
 * Preserves all query and response logic.
 */
export function WeMetPrompt() {
  const queryClient = useQueryClient();
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const { data } = useQuery({
    queryKey: ['wemet-pending'],
    queryFn: feedbackApi.pending,
    refetchInterval: 5 * 60_000,
  });

  const prompt = data?.prompts.find((p) => !dismissed.includes(p.prompt_id));
  if (!prompt) return null;

  const answer = async (response: WeMetAnswer) => {
    setBusy(true);
    try {
      await feedbackApi.respond(prompt.prompt_id, response);
      setDismissed((current) => [...current, prompt.prompt_id]);
      await queryClient.invalidateQueries({ queryKey: ['wemet-pending'] });
    } catch {
      setDismissed((current) => [...current, prompt.prompt_id]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal animationType="fade" transparent visible>
      <View style={styles.modalScrim}>
        <GlassSurface tier="floating" radius={radius.xl} sheen style={styles.sheetGlass}>
          <View style={styles.sheetInner}>
            <Text style={styles.eyebrow}>A QUICK QUESTION</Text>
            <Text style={styles.question}>
              {prompt.reask_number > 0 ? 'Checking back in — have you' : 'Have you'} and{' '}
              {prompt.other_name ?? 'your match'} met in person yet?
            </Text>

            <Card tier="ambient" style={styles.whyCard}>
              <Body muted style={styles.whyBody}>
                Nobody sees your answer. We use it to learn which matches actually work in real
                life — which is the only thing that makes the next fifteen better than the last.
              </Body>
            </Card>

            {/* All three options use Secondary clear glass style (deliberately neutral survey) */}
            <View style={styles.actions}>
              <Button
                label="Yes, we met"
                variant="secondary"
                onPress={() => void answer('met_yes')}
                disabled={busy}
              />
              <Button
                label="Not yet"
                variant="secondary"
                onPress={() => void answer('met_no_yet')}
                disabled={busy}
              />
              <Button
                label="We are not going to"
                variant="secondary"
                onPress={() => void answer('not_going_to')}
                disabled={busy}
              />
            </View>

            <Text style={styles.footnote}>
              {prompt.reask_number > 0
                ? 'We last asked a couple of weeks ago. If you say “not yet” we will stop asking eventually.'
                : 'If you say “not yet”, we will check back once in a week or two.'}
            </Text>
          </View>
        </GlassSurface>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  modalScrim: {
    flex: 1,
    backgroundColor: 'rgba(93, 49, 64, 0.85)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  sheetGlass: { width: '100%', maxWidth: 360 },
  sheetInner: { padding: spacing.xl, gap: spacing.md },
  eyebrow: { ...typography.label, color: colors.rose[300] },
  question: { ...typography.displayM, color: colors.warmBeige, lineHeight: 28 },
  whyCard: { padding: spacing.md },
  whyBody: { ...typography.bodyM, lineHeight: 20 },
  actions: { gap: spacing.sm, marginTop: spacing.xs },
  footnote: { ...typography.caption, color: colors.text.muted, textAlign: 'center', marginTop: spacing.xs },
});
