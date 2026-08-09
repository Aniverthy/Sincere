import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '../../../api/client';
import { Body, Card, Heading, Loading, Screen } from '../../../components';
import { useSession } from '../../../state/session';
import { colors, spacing, typography } from '../../../theme';
import { identityApi, type VerificationStatus } from '../api';

/**
 * Verification in progress / pending human review (FR-1.6, FR-1.7, §19).
 *
 * §19 runs embedding generation asynchronously behind a "verifying…" client state, and §4's
 * screen map gives the ambiguous bot-risk band its own screen. Both land here.
 *
 * **How the user leaves this screen.** Not by navigation. Verification changes the account's
 * lifecycle state server-side; the client picks that up by refreshing its tokens, because §5
 * binds the token scope to lifecycle state. A new scope re-renders the root navigator into a
 * different tree — waitlist, or the daily 15. So this screen polls, then refreshes.
 */
export function VerifyingScreen() {
  const applyTokens = useSession((s) => s.applyTokens);
  const [status, setStatus] = useState<VerificationStatus | null>(null);

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const next = await identityApi.verificationStatus();
        if (cancelled) return;
        setStatus(next);

        // Any status past onboarding/pending means a decision landed — pull a token that
        // carries the new scope so the navigator can move on.
        if (next.status !== 'onboarding' && next.status !== 'pending_review') {
          const { getRefreshToken } = await import('../../../api/tokens');
          const refreshToken = await getRefreshToken();
          if (!refreshToken) return;

          const rotated = await api.post<{ access_token: string; refresh_token: string }>(
            '/auth/refresh',
            { refresh_token: refreshToken },
            { skipAuth: true },
          );
          await applyTokens({
            accessToken: rotated.access_token,
            refreshToken: rotated.refresh_token,
          });
        }
      } catch {
        // Transient failure — the next tick retries.
      }
    };

    void poll();
    const timer = setInterval(() => void poll(), 5_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [applyTokens]);

  const underReview = status?.status === 'pending_review';

  return (
    <Screen>
      <Heading
        sub={
          underReview
            ? 'A person is reviewing your verification. This usually takes a few hours, and we will not ask you to do anything else.'
            : 'This takes a moment. We are checking your capture against every account we have.'
        }
      >
        {underReview ? 'We are checking it is really you' : 'Verifying'}
      </Heading>

      <Loading />

      <Card style={styles.card}>
        <Text style={styles.cardTitle}>What is happening</Text>
        <Step text="Your video is turned into a mathematical signature." />
        <Step text="The video is deleted. Only the signature is kept." />
        <Step text="The signature is compared against existing accounts, to catch duplicates." />
        <Step text="Anything borderline goes to a person, never an automatic rejection." />
      </Card>

      {status?.message ? (
        <View style={styles.status}>
          <Body muted>{status.message}</Body>
        </View>
      ) : null}
    </Screen>
  );
}

function Step({ text }: { text: string }) {
  return (
    <View style={styles.step}>
      <Text style={styles.bullet}>·</Text>
      <Text style={styles.stepText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { marginTop: spacing.lg, gap: spacing.xs },
  cardTitle: { ...typography.label, color: colors.textFaint, marginBottom: spacing.xs },
  step: { flexDirection: 'row', gap: spacing.sm },
  bullet: { ...typography.body, color: colors.primary },
  stepText: { ...typography.caption, color: colors.textMuted, flex: 1 },
  status: { marginTop: spacing.md },
});
