import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '../../../api/client';
import { Card, GlassSurface, Heading, Loading, Screen } from '../../../components';
import { useSession } from '../../../state/session';
import { colors, radius, spacing, typography } from '../../../theme';
import { identityApi, type VerificationStatus } from '../api';

/**
 * Verification in progress / pending human review (FR-1.6, FR-1.7, §19).
 * Preserves polling and token rotation logic exactly.
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
        // Transient failure
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
    <Screen scroll>
      <Heading
        sub={
          underReview
            ? 'A person is reviewing your verification. This usually takes a few hours, and we will not ask you to do anything else.'
            : 'This takes a moment. We are checking your capture against every account we have.'
        }
      >
        {underReview ? 'We are checking it is really you' : 'Verifying'}
      </Heading>

      <View style={styles.loadingHero}>
        <Loading label={underReview ? 'In review' : 'Processing verification'} />
      </View>

      <Card tier="raised" style={styles.processCard}>
        <Text style={styles.cardTitle}>WHAT IS HAPPENING</Text>
        <Step num="1" text="Your video is turned into a mathematical signature." />
        <Step num="2" text="The video is deleted. Only the signature is kept." />
        <Step num="3" text="The signature is compared against existing accounts to catch duplicates." />
        <Step num="4" text="Anything borderline goes to a person, never an automatic rejection." />
      </Card>

      {status?.message ? (
        <GlassSurface tier="ambient" radius={radius.lg} style={styles.statusGlass}>
          <View style={styles.statusInner}>
            <Text style={styles.statusText}>{status.message}</Text>
          </View>
        </GlassSurface>
      ) : null}
    </Screen>
  );
}

function Step({ num, text }: { num: string; text: string }) {
  return (
    <View style={styles.stepRow}>
      <GlassSurface tier="ambient" tint="rose" radius={radius.pill} style={styles.stepBadge}>
        <Text style={styles.stepNum}>{num}</Text>
      </GlassSurface>
      <Text style={styles.stepText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  loadingHero: { marginVertical: spacing.lg },
  processCard: { gap: spacing.md, marginTop: spacing.md },
  cardTitle: { ...typography.label, color: colors.text.muted },

  stepRow: { flexDirection: 'row', alignItems: 'flex-start', gap: spacing.md },
  stepBadge: { width: 24, height: 24, alignItems: 'center', justifyContent: 'center' },
  stepNum: { ...typography.caption, color: colors.text.onRose, fontFamily: 'Manrope_700Bold' },
  stepText: { ...typography.bodyM, color: colors.text.primary, flex: 1, lineHeight: 22 },

  statusGlass: { marginTop: spacing.lg },
  statusInner: { padding: spacing.md },
  statusText: { ...typography.bodyM, color: colors.warmBeige, textAlign: 'center' },
});
