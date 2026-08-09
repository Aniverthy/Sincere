import { useQuery } from '@tanstack/react-query';
import * as Location from 'expo-location';
import { useCallback, useEffect, useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';

import { api } from '../../../api/client';
import { Body, Button, Card, GlassSurface, Heading, Pill, Screen } from '../../../components';
import { useSession } from '../../../state/session';
import { colors, radius as defaultRadius, spacing, typography } from '../../../theme';
import { monetizationApi } from '../api';

/**
 * Me — radius slider (1-100 km), Pro plans, settings, delete account (§4 screen map).
 * Preserves all business logic, queries, and location update functionality.
 */
export function MeScreen() {
  const signOut = useSession((state) => state.signOut);
  const [radius, setRadius] = useState<number | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const { data: plans } = useQuery({ queryKey: ['plans'], queryFn: monetizationApi.plans });
  const { data: subscription } = useQuery({
    queryKey: ['subscription'],
    queryFn: monetizationApi.subscription,
  });

  useEffect(() => {
    void api
      .get<{ radius_km: number }>('/me')
      .then((profile) => setRadius(profile.radius_km))
      .catch(() => undefined);
  }, []);

  const changeRadius = useCallback(async (next: number) => {
    const previous = radius;
    setRadius(next);
    setNotice(null);
    try {
      await api.patch('/me/radius', { radius_km: next });
    } catch {
      setRadius(previous);
      setNotice('Could not change your radius. Check your connection.');
    }
  }, [radius]);

  const refreshLocation = useCallback(async () => {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert(
        'Location needed',
        'Sincère uses your location only while the app is open, to find people near you. We keep no history.',
      );
      return;
    }
    try {
      const position = await Location.getCurrentPositionAsync({});
      await api.post('/me/location', {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
      });
      setNotice('Location updated.');
    } catch {
      setNotice('Could not update your location.');
    }
  }, []);

  const confirmDelete = useCallback(() => {
    Alert.alert(
      'Delete your account?',
      'Your profile is hidden immediately. You can restore it within 30 days; after that everything is permanently deleted.',
      [
        { text: 'Keep my account', style: 'cancel' },
        {
          text: 'Delete',
          style: 'destructive',
          onPress: async () => {
            await api.delete('/me');
            await signOut();
          },
        },
      ],
    );
  }, [signOut]);

  return (
    <Screen scroll>
      <Heading>Me</Heading>

      {/* Radius Selector Card */}
      <Card tier="raised" style={styles.sectionCard}>
        <Text style={styles.sectionTitle}>YOUR RADIUS</Text>
        <Text style={styles.radiusDisplay}>{radius ?? '—'} km</Text>
        <View style={styles.radiusPillsRow}>
          {[5, 10, 25, 50, 100].map((km) => (
            <Pill
              key={km}
              label={`${km} km`}
              selected={radius === km}
              onPress={() => void changeRadius(km)}
            />
          ))}
        </View>
        <Body muted style={styles.sectionNote}>
          Your radius decides which people you are shown. It has no effect on your place in
          any queue.
        </Body>
      </Card>

      {/* Subscription Plan Card with warmBeige shimmer sheen for paid tiers */}
      <Card tier="raised" style={styles.sectionCard}>
        <View style={styles.planHeader}>
          <Text style={styles.sectionTitle}>YOUR PLAN</Text>
          <Pill
            label={subscription?.tier ? subscription.tier.replace('_', ' ') : 'Free'}
            tone={subscription?.tier ? 'success' : 'neutral'}
          />
        </View>

        <Text style={styles.planMeta}>
          {subscription?.daily_matches ?? plans?.free_tier_daily_matches ?? 15} matches a day
        </Text>
        {plans ? <Body muted style={styles.sectionNote}>{plans.free_tier_note}</Body> : null}

        {plans?.plans.map((plan) => (
          <GlassSurface
            key={plan.tier}
            tier="raised"
            tint="rose"
            radius={defaultRadius.lg}
            sheen
            style={styles.paidPlanGlass}
          >
            <View style={styles.paidPlanInner}>
              <View style={styles.planHead}>
                <Text style={styles.planName}>{plan.name}</Text>
                <Text style={styles.planPrice}>₹{(plan.price_paise / 100).toFixed(0)}/mo</Text>
              </View>
              {plan.features
                .filter((feature) => feature.included)
                .map((feature) => (
                  <Text key={feature.label} style={styles.featureText}>
                    ✓ {feature.label}
                  </Text>
                ))}
            </View>
          </GlassSurface>
        ))}
      </Card>

      {/* Privacy Location Card */}
      <Card tier="ambient" style={styles.sectionCard}>
        <Text style={styles.sectionTitle}>PRIVACY & LOCATION</Text>
        <Body muted style={styles.sectionNote}>
          We read your location only while the app is open, and overwrite it each time. No
          history exists to leak.
        </Body>
        <View style={styles.locationAction}>
          <Button label="Update my location" variant="secondary" onPress={() => void refreshLocation()} />
        </View>
      </Card>

      {notice ? <Text style={styles.noticeText}>{notice}</Text> : null}

      <View style={styles.accountActionsFooter}>
        <Button label="Sign out" variant="secondary" onPress={() => void signOut()} />
        <View style={styles.deleteSpacer}>
          <Button label="Delete account" variant="danger" onPress={confirmDelete} />
        </View>
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  sectionCard: { marginBottom: spacing.lg, gap: spacing.sm },
  sectionTitle: { ...typography.label, color: colors.text.muted },
  radiusDisplay: { fontFamily: 'Fraunces_600SemiBold', fontSize: 36, color: colors.rose[300] },
  radiusPillsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginVertical: spacing.xs },
  sectionNote: { ...typography.bodyM, color: colors.text.muted, lineHeight: 20 },

  planHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  planMeta: { ...typography.displayM, color: colors.warmBeige, marginTop: spacing.xs },
  paidPlanGlass: { marginTop: spacing.md },
  paidPlanInner: { padding: spacing.md },
  planHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.xs },
  planName: { ...typography.displayM, color: colors.warmBeige },
  planPrice: { ...typography.label, color: colors.rose[300], fontSize: 16 },
  featureText: { ...typography.caption, color: colors.text.primary, marginTop: 4 },

  locationAction: { marginTop: spacing.sm },
  noticeText: { ...typography.caption, color: colors.rose[300], marginBottom: spacing.sm, textAlign: 'center' },

  accountActionsFooter: { marginTop: spacing.xl, marginBottom: spacing.xxl },
  deleteSpacer: { marginTop: spacing.lg },
});
