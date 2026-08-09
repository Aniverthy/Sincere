import { useQuery } from '@tanstack/react-query';
import * as Location from 'expo-location';
import { useCallback, useEffect, useState } from 'react';
import { Alert, StyleSheet, Text, View } from 'react-native';

import { api } from '../../../api/client';
import { Body, Button, Card, Heading, Pill, Screen } from '../../../components';
import { useSession } from '../../../state/session';
import { colors, spacing, typography } from '../../../theme';
import { monetizationApi } from '../api';

/**
 * Me — radius slider (1-100 km), Pro plans, settings, delete account (§4 screen map).
 *
 * §4 requires the radius copy make clear it affects **matches only, never queue position** —
 * users otherwise assume a wider radius jumps the waitlist.
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
      // Roll the control back rather than showing a value the server did not accept.
      setRadius(previous);
      setNotice('Could not change your radius. Check your connection.');
    }
  }, [radius]);

  /**
   * §4: location is fetched once per app foreground and posted. **No background permission
   * is requested** — that is a product decision (DECIDED) and a privacy selling point, and
   * `app.json` blocks ACCESS_BACKGROUND_LOCATION at the manifest level to make it structural.
   */
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

      <Card style={styles.section}>
        <Text style={styles.sectionTitle}>Your radius</Text>
        <Text style={styles.radiusValue}>{radius ?? '—'} km</Text>
        <View style={styles.radiusButtons}>
          {[5, 10, 25, 50, 100].map((km) => (
            <Button
              key={km}
              label={`${km}`}
              variant={radius === km ? 'primary' : 'secondary'}
              onPress={() => void changeRadius(km)}
            />
          ))}
        </View>
        <Body muted>
          Your radius decides which people you are shown. It has no effect on your place in
          any queue.
        </Body>
      </Card>

      <Card style={styles.section}>
        <Text style={styles.sectionTitle}>Your plan</Text>
        <Pill
          label={subscription?.tier ? subscription.tier.replace('_', ' ') : 'Free'}
          tone={subscription?.tier ? 'success' : 'neutral'}
        />
        <Text style={styles.planMeta}>
          {subscription?.daily_matches ?? plans?.free_tier_daily_matches ?? 15} matches a day
        </Text>
        {plans ? <Body muted>{plans.free_tier_note}</Body> : null}

        {plans?.plans.map((plan) => (
          <View key={plan.tier} style={styles.plan}>
            <View style={styles.planHead}>
              <Text style={styles.planName}>{plan.name}</Text>
              <Text style={styles.planPrice}>₹{(plan.price_paise / 100).toFixed(0)}/mo</Text>
            </View>
            {plan.features
              .filter((feature) => feature.included)
              .map((feature) => (
                <Text key={feature.label} style={styles.feature}>
                  · {feature.label}
                </Text>
              ))}
          </View>
        ))}
      </Card>

      <Card style={styles.section}>
        <Text style={styles.sectionTitle}>Privacy</Text>
        <Body muted>
          We read your location only while the app is open, and overwrite it each time. No
          history exists to leak.
        </Body>
        <Button label="Update my location" variant="secondary" onPress={() => void refreshLocation()} />
      </Card>

      {notice ? <Text style={styles.notice}>{notice}</Text> : null}

      <View style={styles.footer}>
        <Button label="Sign out" variant="secondary" onPress={() => void signOut()} />
        <Button label="Delete account" variant="danger" onPress={confirmDelete} />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { marginBottom: spacing.md, gap: spacing.sm },
  sectionTitle: { ...typography.label, color: colors.textFaint },
  radiusValue: { ...typography.title, color: colors.primary },
  radiusButtons: { flexDirection: 'row', gap: spacing.xs },
  planMeta: { ...typography.bodyStrong, color: colors.text },
  plan: {
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingTop: spacing.sm,
    marginTop: spacing.sm,
  },
  planHead: { flexDirection: 'row', justifyContent: 'space-between' },
  planName: { ...typography.bodyStrong, color: colors.text },
  planPrice: { ...typography.bodyStrong, color: colors.primary },
  feature: { ...typography.caption, color: colors.textMuted, marginTop: 2 },
  notice: { ...typography.caption, color: colors.textMuted, marginBottom: spacing.sm },
  footer: { gap: spacing.sm, marginTop: spacing.lg },
});
