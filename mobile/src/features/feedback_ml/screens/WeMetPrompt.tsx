import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Modal, StyleSheet, Text, View } from 'react-native';

import { Body, Button, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { feedbackApi, type WeMetAnswer } from '../api';

/**
 * We-Met prompt (FR-4.3, FR-4.4).
 *
 * Fires at 20-30 messages within a 3-day window. `met_no_yet` schedules a re-ask in 1-2
 * weeks; the other two answers are terminal for that match — continuing to ask someone who
 * said "not going to" would be harassment by scheduler.
 *
 * The copy explains *why* we are asking. §13's purpose for this loop is to re-anchor the
 * models to real-world compatibility rather than in-app swipe appeal, and people answer an
 * honest question more honestly than an unexplained one.
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
    <Modal animationType="slide" transparent={false} visible>
      <Screen>
        <View style={styles.body}>
          <Text style={styles.eyebrow}>A QUICK QUESTION</Text>
          <Text style={styles.question}>
            {prompt.reask_number > 0 ? 'Checking back in — have you' : 'Have you'} and{' '}
            {prompt.other_name ?? 'your match'} met in person yet?
          </Text>

          <View style={styles.why}>
            <Body muted>
              Nobody sees your answer. We use it to learn which matches actually work in real
              life — which is the only thing that makes the next fifteen better than the last.
            </Body>
          </View>

          <View style={styles.actions}>
            <Button label="Yes, we met" onPress={() => void answer('met_yes')} loading={busy} />
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
      </Screen>
    </Modal>
  );
}

const styles = StyleSheet.create({
  body: { flex: 1, justifyContent: 'center', gap: spacing.md },
  eyebrow: { ...typography.label, color: colors.primary },
  question: { ...typography.title, color: colors.text },
  why: {
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
  },
  actions: { gap: spacing.sm, marginTop: spacing.md },
  footnote: { ...typography.caption, color: colors.textFaint, textAlign: 'center' },
});
