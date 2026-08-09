import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import * as Haptics from 'expo-haptics';

import { ApiError } from '../../../api/client';
import { GlassSurface, Heading, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { identityApi } from '../api';
import { useOnboarding } from '../state';

/**
 * Gender selection.
 * Preserves all business logic exactly.
 */
export function GenderScreen() {
  const setStep = useOnboarding((s) => s.setStep);
  const [busy, setBusy] = useState<'male' | 'female' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const choose = async (gender: 'male' | 'female') => {
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setError(null);
    setBusy(gender);
    try {
      await identityApi.setGender(gender);
      setStep('profile');
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setStep('profile');
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

      <View style={styles.tilesContainer}>
        <TileOption
          label="Woman"
          sub="Joining female membership balance"
          busy={busy === 'female'}
          disabled={busy !== null}
          onPress={() => void choose('female')}
        />
        <TileOption
          label="Man"
          sub="Joining male membership balance"
          busy={busy === 'male'}
          disabled={busy !== null}
          onPress={() => void choose('male')}
        />
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <Text style={styles.disclaimer}>
        🔒 This cannot be changed later — it determines how you were admitted. Contact support if you need it corrected.
      </Text>
    </Screen>
  );
}

function TileOption({
  label,
  sub,
  busy,
  disabled,
  onPress,
}: {
  label: string;
  sub: string;
  busy: boolean;
  disabled: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      style={({ pressed }) => [styles.tileWrapper, pressed && styles.tilePressed]}
    >
      <GlassSurface
        tier="raised"
        tint={busy ? 'rose' : 'neutral'}
        radius={radius.xl}
        style={styles.tileGlass}
      >
        <View style={styles.tileInner}>
          <Text style={styles.tileLabel}>{label}</Text>
          <Text style={styles.tileSub}>{sub}</Text>
        </View>
      </GlassSurface>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  tilesContainer: { gap: spacing.md, marginVertical: spacing.lg },
  tileWrapper: { width: '100%' },
  tilePressed: { opacity: 0.88, transform: [{ scale: 0.98 }] },
  tileGlass: { minHeight: 90 },
  tileInner: { padding: spacing.lg, justifyContent: 'center' },
  tileLabel: { ...typography.displayM, color: colors.warmBeige },
  tileSub: { ...typography.caption, color: colors.text.muted, marginTop: spacing.xs },

  error: { ...typography.caption, color: colors.dangerRed, marginBottom: spacing.sm },
  disclaimer: { ...typography.caption, color: colors.text.muted, marginTop: spacing.md, lineHeight: 18 },
});
