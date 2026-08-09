import { useQuery } from '@tanstack/react-query';
import { StyleSheet, Text, View } from 'react-native';

import { Body, Card, ErrorState, Heading, Loading, Pill, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { admissionApi } from '../api';

/**
 * Waitlist (FR-2.7-2.10, §4 screen map).
 * Preserves all React Query data fetching and business rules.
 */
export function WaitlistScreen() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['queue-status'],
    queryFn: admissionApi.status,
    refetchInterval: 60_000,
  });

  const { data: auction } = useQuery({
    queryKey: ['auction-today'],
    queryFn: admissionApi.auctionToday,
    retry: false,
  });

  if (isLoading) return <Loading label="Finding your place" />;

  if (error) {
    return (
      <Screen>
        <ErrorState
          title="Could not load your place in line"
          detail="Your position is safe — this is only a display problem."
          onRetry={refetch}
        />
      </Screen>
    );
  }

  const frozen = data?.admission_state === 'frozen';

  return (
    <Screen scroll>
      <Heading sub="Sincère admits men only as fast as the community stays balanced. It is what keeps matches real rather than endless.">
        You are on the list
      </Heading>

      <Card tier="raised" style={styles.positionCard}>
        <Text style={styles.positionLabel}>YOUR POSITION</Text>
        <Text style={styles.positionValue}>{data?.position ?? '—'}</Text>
        <Pill
          label={frozen ? 'Admissions paused' : 'Places open daily'}
          tone={frozen ? 'warning' : 'success'}
        />
        {data?.estimated_days ? (
          <Text style={styles.estimate}>
            Roughly {data.estimated_days} day{data.estimated_days === 1 ? '' : 's'} at the current rate
          </Text>
        ) : null}
      </Card>

      {frozen ? (
        <Card tier="raised" tint="warning" style={styles.noticeCard}>
          <Body>
            {data?.message ??
              'Admissions in your area are paused while the community rebalances.'}
          </Body>
        </Card>
      ) : null}

      {/* 3 Admission channel cards at equal visual weight */}
      <View style={styles.tiersContainer}>
        <TierCard
          title="Free queue"
          share="60% of daily places"
          detail="Ordered by how genuinely you engage — a complete, real profile moves faster than an early but empty one."
        />
        <TierCard
          title="Paid entry"
          share="25% of daily places"
          detail="A fixed price. Never surge-priced, however long the queue gets."
        />
        <TierCard
          title="Daily auction"
          share="15% of daily places"
          detail={
            auction
              ? `Bidding is open ${formatWindow(auction.window_start, auction.window_end)}. ${auction.slots} place${auction.slots === 1 ? '' : 's'} today.`
              : 'One open bidding window each day. Top bids at close take that day’s places.'
          }
        />
      </View>

      <Card tier="raised" style={styles.fairnessCard}>
        <Body>
          Paying or winning the auction changes <Text style={styles.emphasis}>when</Text> you
          get in — never who you are shown to, or how you are ranked. Everyone is scored the
          same way.
        </Body>
      </Card>

      <View style={styles.disclaimerContainer}>
        <Text style={styles.disclaimerText}>
          If the balance dips, we pause new admissions. We never remove anyone who is already
          in — including you, once you are.
        </Text>
      </View>
    </Screen>
  );
}

function formatWindow(start: string, end: string): string {
  const format = (iso: string) =>
    new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return `${format(start)}–${format(end)}`;
}

function TierCard({ title, share, detail }: { title: string; share: string; detail: string }) {
  return (
    <Card tier="raised" style={styles.tierCard}>
      <View style={styles.tierHead}>
        <Text style={styles.tierTitle}>{title}</Text>
        <Text style={styles.tierShare}>{share}</Text>
      </View>
      <Text style={styles.tierDetail}>{detail}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  positionCard: { alignItems: 'center', paddingVertical: spacing.xl, marginBottom: spacing.lg },
  positionLabel: { ...typography.label, color: colors.text.muted },
  positionValue: {
    fontFamily: 'Fraunces_600SemiBold',
    fontSize: 52,
    lineHeight: 56,
    color: colors.rose[300],
    marginVertical: spacing.sm,
  },
  estimate: { ...typography.caption, color: colors.text.muted, marginTop: spacing.sm },

  noticeCard: { marginBottom: spacing.lg },
  tiersContainer: { gap: spacing.md, marginBottom: spacing.lg },
  tierCard: { width: '100%' },
  tierHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  tierTitle: { ...typography.displayM, color: colors.warmBeige },
  tierShare: { ...typography.label, color: colors.rose[300] },
  tierDetail: { ...typography.bodyM, color: colors.text.muted, lineHeight: 20 },

  fairnessCard: { marginBottom: spacing.lg },
  emphasis: { color: colors.rose[300], fontFamily: 'Manrope_700Bold' },

  disclaimerContainer: { paddingHorizontal: spacing.sm, marginBottom: spacing.xl },
  disclaimerText: { ...typography.caption, color: colors.text.muted, lineHeight: 18 },
});
