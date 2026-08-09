import { useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '../../../api/client';
import { Body, Button, GlassSurface, Heading, OtpInput, Screen } from '../../../components';
import { useSession } from '../../../state/session';
import { colors, radius, spacing, typography } from '../../../theme';
import { identityApi } from '../api';
import { useOnboarding } from '../state';

/**
 * OTP verification (§5 POST /auth/verify-otp → onboarding-scope tokens).
 * Preserves all business logic exactly.
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

      <View style={styles.inputWrapper}>
        <OtpInput value={otp} onChange={setOtp} length={6} />
        <TextInput
          value={otp}
          onChangeText={(v) => setOtp(v.replace(/[^0-9]/g, '').slice(0, 6))}
          keyboardType="number-pad"
          maxLength={6}
          autoFocus
          style={styles.hiddenInput}
          editable={!busy}
        />
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      {devOtp ? (
        <GlassSurface tier="ambient" tint="warning" radius={radius.lg} style={styles.devHint}>
          <View style={styles.devHintInner}>
            <Text style={styles.devLabel}>DEV MODE</Text>
            <Text style={styles.devCode}>{devOtp}</Text>
            <Text style={styles.devNote}>
              Shown because SMS_PROVIDER=console. Never returned in production.
            </Text>
          </View>
        </GlassSurface>
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
  inputWrapper: { position: 'relative' },
  hiddenInput: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0,
    fontSize: 1,
  },
  error: { ...typography.caption, color: colors.dangerRed, marginTop: spacing.sm },

  devHint: { marginTop: spacing.lg },
  devHintInner: { padding: spacing.md, alignItems: 'center' },
  devLabel: { ...typography.label, color: colors.warningAmber },
  devCode: {
    fontFamily: 'Fraunces_600SemiBold',
    fontSize: 28,
    color: colors.warningAmber,
    letterSpacing: 8,
    marginVertical: spacing.xs,
  },
  devNote: { ...typography.caption, color: colors.text.muted, textAlign: 'center' },

  actions: { gap: spacing.sm, marginTop: spacing.lg, marginBottom: spacing.md },
});
