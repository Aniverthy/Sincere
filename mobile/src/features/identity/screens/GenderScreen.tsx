import { useState } from 'react';
import { StyleSheet, Text } from 'react-native';

import { ApiError } from '../../../api/client';
import { Body, Button, Card, Heading, Screen } from '../../../components';
import { colors, spacing, typography } from '../../../theme';
import { identityApi } from '../api';
import { useOnboarding } from '../state';

/**
 * Gender selection.
 *
 * Two values, because Sincère's admission ratio (FR-2.4) is defined over two opposite pools —
 * a mechanical constraint of the documented admission model, not a claim about identity. The
 * copy says why, because a bare binary choice with no explanation reads as carelessness.
 *
 * Write-once (the service enforces it): changing it later would retroactively corrupt every
 * hex's ratio counters.
 */
export function GenderScreen() {
  const setStep = useOnboarding((s) => s.setStep);
  const [busy, setBusy] = useState<'male' | 'female' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const choose = async (gender: 'male' | 'female') => {
    setError(null);
    setBusy(gender);
    try {
      await identityApi.setGender(gender);
      setStep('profile');
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setStep('profile'); // already set — a retry after a dropped response
        return;
      }
      setError(err instanceof ApiError ? (err.problem.detail ?? err.problem.title) : 'Try again.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <Screen scroll>
      <Heading sub="Sincère balances how many men and women are active in each area, so this decides which side of that balance you join.">
        I am a…
      </Heading>

      <Card style={styles.card}>
        <Button
          label="Woman"
          onPress={() => void choose('female')}
          loading={busy === 'female'}
          disabled={busy !== null}
        />
        <Button
          label="Man"
          onPress={() => void choose('male')}
          loading={busy === 'male'}
          disabled={busy !== null}
        />
      </Card>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Body muted>
        This cannot be changed later — it determines how you were admitted. Contact support if
        you need it corrected.
      </Body>
    </Screen>
  );
}

const styles = StyleSheet.create({
  card: { gap: spacing.sm, marginBottom: spacing.md },
  error: { ...typography.caption, color: colors.danger, marginBottom: spacing.sm },
});
