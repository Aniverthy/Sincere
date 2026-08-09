import { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '../../../api/client';
import { Body, Button, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { identityApi } from '../api';
import { useOnboarding } from '../state';

/**
 * Signup — phone entry (FR-1.1, §5 ``POST /auth/signup``).
 *
 * The privacy promises are on this screen deliberately: they are the reason someone chooses
 * Sincère over the alternatives, and burying them in a settings page would waste them.
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
      <View style={styles.brand}>
        <Text style={styles.wordmark}>Sincère</Text>
        <Text style={styles.tagline}>Verified people. Deliberate matches.</Text>
      </View>

      <View style={styles.promises}>
        <Promise
          title="Real people only"
          detail="Every profile passes a live face check before it can be seen. No bots, no stolen photos."
        />
        <Promise
          title="We never track your location"
          detail="Read once when you open the app, then overwritten. No history exists to leak."
        />
        <Promise
          title="Fifteen matches a day, free forever"
          detail="Not a trial. Base access is never revoked for active members."
        />
      </View>

      <Text style={styles.label}>YOUR PHONE NUMBER</Text>
      <TextInput
        value={phone}
        onChangeText={setPhone}
        placeholder="+91 98765 43210"
        placeholderTextColor={colors.textFaint}
        keyboardType="phone-pad"
        autoComplete="tel"
        style={styles.input}
        editable={!busy}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}

      <View style={styles.action}>
        <Button label="Send me a code" onPress={() => void submit()} loading={busy} />
      </View>
      <Body muted>We use your number to sign you in. It is never shown to anyone.</Body>
    </Screen>
  );
}

function Promise({ title, detail }: { title: string; detail: string }) {
  return (
    <View style={styles.promise}>
      <Text style={styles.promiseTitle}>{title}</Text>
      <Text style={styles.promiseDetail}>{detail}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  brand: { alignItems: 'center', marginTop: spacing.xl, marginBottom: spacing.xl },
  wordmark: { ...typography.display, color: colors.primary },
  tagline: { ...typography.body, color: colors.textMuted, marginTop: spacing.sm },
  promises: { marginBottom: spacing.xl },
  promise: { marginBottom: spacing.md },
  promiseTitle: { ...typography.bodyStrong, color: colors.text, marginBottom: 2 },
  promiseDetail: { ...typography.caption, color: colors.textMuted },
  label: { ...typography.label, color: colors.textFaint, marginBottom: spacing.xs },
  input: {
    minHeight: 52,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    paddingHorizontal: spacing.md,
    ...typography.body,
  },
  error: { ...typography.caption, color: colors.danger, marginTop: spacing.sm },
  action: { marginTop: spacing.lg, marginBottom: spacing.md },
});
