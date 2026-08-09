import { useQuery } from '@tanstack/react-query';
import { StyleSheet, Text, View } from 'react-native';

import { Body, Card, ErrorState, Heading, Loading, Pill, Screen } from '../../../components';
import { colors, spacing, typography } from '../../../theme';
import { admissionApi } from '../api';

/**
 * Waitlist (FR-2.7-2.10, §4 screen map).
 *
 * Two DECIDED rules the copy states explicitly, because users will otherwise assume the
 * opposite:
 *   - FR-2.11: paying or winning the auction buys **entry timing only** — no score advantage.
 *   - FR-2.10: the free queue is ordered by engagement quality, not first-come-first-served.
 *
 * And when the region is frozen (FR-2.4), the copy says plainly that **nobody is removed** —
 * FR-2.6's never-evict rule is reassuring only if the person waiting knows about it.
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

      <Card style={styles.positionCard}>
        <Text style={styles.positionLabel}>YOUR POSITION</Text>
        <Text style={styles.positionValue}>{data?.position ?? '—'}</Text>
        <Pill
          label={frozen ? 'Admissions paused' : 'Places open daily'}
          tone={frozen ? 'warning' : 'success'}
        />
        {data?.estimated_days ? (
          <Text style={styles.estimate}>
            Roughly {data.estimated_days} day{data.estimated_days === 1 ? '' : 's'} at the
            current rate
          </Text>
        ) : null}
      </Card>

      {frozen ? (
        <Card style={styles.notice}>
          <Body>
            {data?.message ??
              'Admissions in your area are paused while the community rebalances.'}
          </Body>
        </Card>
      ) : null}

      <View style={styles.tiers}>
        <Tier
          title="Free queue"
          share="60% of daily places"
          detail="Ordered by how genuinely you engage — a complete, real profile moves faster than an early but empty one."
        />
        <Tier
          title="Paid entry"
          share="25% of daily places"
          detail="A fixed price. Never surge-priced, however long the queue gets."
        />
        <Tier
          title="Daily auction"
          share="15% of daily places"
          detail={
            auction
              ? `Bidding is open ${formatWindow(auction.window_start, auction.window_end)}. ${auction.slots} place${auction.slots === 1 ? '' : 's'} today.`
              : 'One open bidding window each day. Top bids at close take that day’s places.'
          }
        />
      </View>

      <Card>
        <Body>
          Paying or winning the auction changes <Text style={styles.emphasis}>when</Text> you
          get in — never who you are shown to, or how you are ranked. Everyone is scored the
          same way.
        </Body>
      </Card>

      <Card style={styles.notice}>
        <Body muted>
          If the balance dips, we pause new admissions. We never remove anyone who is already
          in — including you, once you are.
        </Body>
      </Card>
    </Screen>
  );
}

function formatWindow(start: string, end: string): string {
  const format = (iso: string) =>
    new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
  return `${format(start)}–${format(end)}`;
}

function Tier({ title, share, detail }: { title: string; share: string; detail: string }) {
  return (
    <Card style={styles.tier}>
      <View style={styles.tierHead}>
        <Text style={styles.tierTitle}>{title}</Text>
        <Text style={styles.tierShare}>{share}</Text>
      </View>
      <Text style={styles.tierDetail}>{detail}</Text>
    </Card>
  );
}

const styles = StyleSheet.create({
  positionCard: { alignItems: 'center', paddingVertical: spacing.xl, marginBottom: spacing.md },
  positionLabel: { ...typography.label, color: colors.textFaint },
  positionValue: { ...typography.display, color: colors.primary, marginVertical: spacing.sm },
  estimate: { ...typography.caption, color: colors.textMuted, marginTop: spacing.sm },
  notice: { marginBottom: spacing.md },
  tiers: { marginBottom: spacing.md },
  tier: { marginBottom: spacing.sm },
  tierHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  tierTitle: { ...typography.bodyStrong, color: colors.text },
  tierShare: { ...typography.caption, color: colors.primary },
  tierDetail: { ...typography.caption, color: colors.textMuted },
  emphasis: { color: colors.primary, fontWeight: '700' },
});
