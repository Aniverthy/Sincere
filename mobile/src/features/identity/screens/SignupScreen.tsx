import { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '../../../api/client';
import { Button, GlassSurface, Logo, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { identityApi } from '../api';
import { useOnboarding } from '../state';

/**
 * Signup — phone entry (FR-1.1, §5 POST /auth/signup).
 * Preserves all business logic exactly.
 */
export function SignupScreen({ onSent }: { onSent: () => void }) {
  const setChallenge = useOnboarding((s) => s.setChallenge);
  const [phone, setPhone] = useState('+91');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    setBusy(true);
    try {
      const result = await identityApi.signup(phone.trim());
      setChallenge(phone.trim(), result.challenge_id, result.dev_otp ?? null);
      onSent();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? (err.problem.detail ?? err.problem.title)
          : 'Could not send your code. Check your connection.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen scroll>
      <View style={styles.header}>
        <Logo size={72} />
        <View style={styles.wordmarkRow}>
          <Text style={styles.wordmark}>Sinc</Text>
          <Text style={styles.wordmarkAccent}>è</Text>
          <Text style={styles.wordmark}>re</Text>
        </View>
        <Text style={styles.tagline}>Verified people. Deliberate matches.</Text>
      </View>

      <View style={styles.promises}>
        <PromiseRow
          title="Real people only"
          detail="Every profile passes a live face check before it can be seen. No bots, no stolen photos."
        />
        <PromiseRow
          title="We never track your location"
          detail="Read once when you open the app, then overwritten. No history exists to leak."
        />
        <PromiseRow
          title="Fifteen matches a day, free forever"
          detail="Not a trial. Base access is never revoked for active members."
        />
      </View>

      <Text style={styles.label}>YOUR PHONE NUMBER</Text>
      <GlassSurface tier="ambient" radius={radius.pill} style={styles.phoneInputContainer}>
        <View style={styles.phoneInputInner}>
          <Text style={styles.countryCode}>+91</Text>
          <View style={styles.divider} />
          <TextInput
            value={phone.replace(/^\+91\s?/, '')}
            onChangeText={(val) => setPhone(`+91 ${val}`)}
            placeholder="98765 43210"
            placeholderTextColor={colors.text.muted}
            keyboardType="phone-pad"
            autoComplete="tel"
            style={styles.textInput}
            editable={!busy}
          />
        </View>
      </GlassSurface>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <View style={styles.action}>
        <Button label="Send me a code" onPress={() => void submit()} loading={busy} />
      </View>
      <Text style={styles.footerNote}>
        We use your number to sign you in. It is never shown to anyone.
      </Text>
    </Screen>
  );
}

function PromiseRow({ title, detail }: { title: string; detail: string }) {
  return (
    <GlassSurface tier="ambient" radius={radius.lg} style={styles.promiseGlass}>
      <View style={styles.promiseContent}>
        <Text style={styles.promiseTitle}>{title}</Text>
        <Text style={styles.promiseDetail}>{detail}</Text>
      </View>
    </GlassSurface>
  );
}

const styles = StyleSheet.create({
  header: { alignItems: 'center', marginTop: spacing.lg, marginBottom: spacing.xl },
  wordmarkRow: { flexDirection: 'row', alignItems: 'baseline', marginTop: spacing.md },
  wordmark: { ...typography.displayL, color: colors.warmBeige },
  wordmarkAccent: { ...typography.displayL, color: colors.rose[500] },
  tagline: { ...typography.bodyM, color: colors.text.muted, marginTop: spacing.xs },

  promises: { gap: spacing.sm, marginBottom: spacing.xl },
  promiseGlass: { width: '100%' },
  promiseContent: { padding: spacing.md },
  promiseTitle: { ...typography.label, color: colors.warmBeige, marginBottom: 2 },
  promiseDetail: { ...typography.caption, color: colors.text.muted },

  label: { ...typography.label, color: colors.text.muted, marginBottom: spacing.xs },
  phoneInputContainer: { width: '100%' },
  phoneInputInner: {
    flexDirection: 'row',
    alignItems: 'center',
    height: 52,
    paddingHorizontal: spacing.md,
  },
  countryCode: { ...typography.label, color: colors.warmBeige },
  divider: { width: 1, height: 20, backgroundColor: colors.glass.ambient.border, marginHorizontal: spacing.md },
  textInput: {
    flex: 1,
    ...typography.bodyL,
    color: colors.text.primary,
    paddingVertical: 0,
  },

  error: { ...typography.caption, color: colors.dangerRed, marginTop: spacing.sm },
  action: { marginTop: spacing.lg, marginBottom: spacing.md },
  footerNote: { ...typography.caption, color: colors.text.muted, textAlign: 'center' },
});
