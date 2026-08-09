import { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '../../../api/client';
import { Body, Button, Heading, Screen } from '../../../components';
import { useSession } from '../../../state/session';
import { colors, radius, spacing, typography } from '../../../theme';
import { identityApi } from '../api';
import { useOnboarding } from '../state';

/**
 * OTP verification (§5 ``POST /auth/verify-otp`` → onboarding-scope tokens).
 *
 * On success the session store takes over: the token's `scope` claim drives which screens
 * exist, so there is no explicit navigation call here.
 */
export function OtpScreen() {
  const { phone, challengeId, devOtp, reset, setStep } = useOnboarding();
  const signIn = useSession((s) => s.signIn);

  const [otp, setOtp] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!challengeId) return;
    setError(null);
    setBusy(true);
    try {
      const tokens = await identityApi.verifyOtp(challengeId, otp.trim());
      setStep('gender');
      await signIn({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
    } catch (err) {
      setError(
        err instanceof ApiError
          ? (err.problem.detail ?? err.problem.title)
          : 'Could not verify that code.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen scroll>
      <Heading sub={`We sent a six-digit code to ${phone ?? 'your phone'}.`}>
        Enter your code
      </Heading>

      <TextInput
        value={otp}
        onChangeText={setOtp}
        placeholder="000000"
        placeholderTextColor={colors.textFaint}
        keyboardType="number-pad"
        maxLength={6}
        autoFocus
        style={styles.input}
        editable={!busy}
      />
      {error ? <Text style={styles.error}>{error}</Text> : null}

      {devOtp ? (
        <View style={styles.devHint}>
          <Text style={styles.devLabel}>DEV MODE</Text>
          <Text style={styles.devCode}>{devOtp}</Text>
          <Text style={styles.devNote}>
            Shown because SMS_PROVIDER=console. Never returned in production.
          </Text>
        </View>
      ) : null}

      <View style={styles.actions}>
        <Button
          label="Verify"
          onPress={() => void submit()}
          loading={busy}
          disabled={otp.trim().length < 4}
        />
        <Button label="Use a different number" variant="secondary" onPress={reset} />
      </View>

      <Body muted>Codes expire after five minutes.</Body>
    </Screen>
  );
}

const styles = StyleSheet.create({
  input: {
    minHeight: 64,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    textAlign: 'center',
    letterSpacing: 12,
    fontSize: 28,
    fontWeight: '700',
  },
  error: { ...typography.caption, color: colors.danger, marginTop: spacing.sm },
  devHint: {
    marginTop: spacing.lg,
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: colors.primaryMutedBg,
    borderWidth: 1,
    borderColor: colors.primary,
    alignItems: 'center',
  },
  devLabel: { ...typography.label, color: colors.primary },
  devCode: {
    ...typography.title,
    color: colors.primary,
    letterSpacing: 8,
    marginVertical: spacing.xs,
  },
  devNote: { ...typography.caption, color: colors.textMuted, textAlign: 'center' },
  actions: { gap: spacing.sm, marginTop: spacing.lg, marginBottom: spacing.md },
});
