import type { ReactNode } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { colors, radius, spacing, typography } from '../theme';

/** Screen chrome: safe area + background, so no screen repeats it. */
export function Screen({
  children,
  scroll = false,
  style,
}: {
  children: ReactNode;
  scroll?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const content = scroll ? (
    <ScrollView
      contentContainerStyle={[styles.scrollContent, style]}
      keyboardShouldPersistTaps="handled"
    >
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.screenBody, style]}>{children}</View>
  );

  return <SafeAreaView style={styles.screen}>{content}</SafeAreaView>;
}

export function Heading({ children, sub }: { children: ReactNode; sub?: string }) {
  return (
    <View style={styles.headingBlock}>
      <Text style={styles.headingText}>{children}</Text>
      {sub ? <Text style={styles.headingSub}>{sub}</Text> : null}
    </View>
  );
}

export function Body({ children, muted = false }: { children: ReactNode; muted?: boolean }) {
  return <Text style={[styles.body, muted && styles.bodyMuted]}>{children}</Text>;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  loading = false,
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  loading?: boolean;
  disabled?: boolean;
}) {
  const inactive = disabled || loading;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: inactive, busy: loading }}
      onPress={onPress}
      disabled={inactive}
      style={({ pressed }) => [
        styles.button,
        variant === 'primary' && styles.buttonPrimary,
        variant === 'secondary' && styles.buttonSecondary,
        variant === 'danger' && styles.buttonDanger,
        pressed && styles.buttonPressed,
        inactive && styles.buttonDisabled,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={variant === 'primary' ? colors.textInverse : colors.text} />
      ) : (
        <Text
          style={[
            styles.buttonLabel,
            variant === 'primary' ? styles.buttonLabelDark : styles.buttonLabelLight,
          ]}
        >
          {label}
        </Text>
      )}
    </Pressable>
  );
}

export function Card({
  children,
  style,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return <View style={[styles.card, style]}>{children}</View>;
}

/**
 * FR-6.2 (DECIDED): "Boosted profiles **must be labeled 'Boosted'** to viewers."
 *
 * This component is the single implementation of that obligation. Rendering a profile whose
 * payload carries `boosted: true` without it is a product-rule violation, not a style choice —
 * which is why the label text is not a prop.
 */
export function BoostedBadge() {
  return (
    <View style={styles.boostedBadge} accessibilityLabel="This profile has boosted visibility">
      <Text style={styles.boostedText}>BOOSTED</Text>
    </View>
  );
}

export function Pill({
  label,
  tone = 'neutral',
}: {
  label: string;
  tone?: 'neutral' | 'success' | 'warning' | 'danger';
}) {
  const toneStyle =
    tone === 'success'
      ? styles.pillSuccess
      : tone === 'warning'
        ? styles.pillWarning
        : tone === 'danger'
          ? styles.pillDanger
          : styles.pillNeutral;

  return (
    <View style={[styles.pill, toneStyle]}>
      <Text style={styles.pillText}>{label}</Text>
    </View>
  );
}

export function Loading({ label }: { label?: string }) {
  return (
    <View style={styles.centered}>
      <ActivityIndicator color={colors.primary} size="large" />
      {label ? <Text style={styles.loadingLabel}>{label}</Text> : null}
    </View>
  );
}

export function ErrorState({
  title,
  detail,
  onRetry,
}: {
  title: string;
  detail?: string;
  onRetry?: () => void;
}) {
  return (
    <View style={styles.centered}>
      <Text style={styles.errorTitle}>{title}</Text>
      {detail ? <Text style={styles.errorDetail}>{detail}</Text> : null}
      {onRetry ? (
        <View style={styles.errorAction}>
          <Button label="Try again" onPress={onRetry} variant="secondary" />
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  screenBody: { flex: 1, padding: spacing.lg },
  scrollContent: { padding: spacing.lg, paddingBottom: spacing.xxl },

  headingBlock: { marginBottom: spacing.lg },
  headingText: { ...typography.title, color: colors.text },
  headingSub: { ...typography.body, color: colors.textMuted, marginTop: spacing.sm },

  body: { ...typography.body, color: colors.text },
  bodyMuted: { color: colors.textMuted },

  button: {
    minHeight: 52,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  buttonPrimary: { backgroundColor: colors.primary },
  buttonSecondary: {
    backgroundColor: colors.surfaceRaised,
    borderWidth: 1,
    borderColor: colors.border,
  },
  buttonDanger: { backgroundColor: colors.danger },
  buttonPressed: { opacity: 0.85 },
  buttonDisabled: { opacity: 0.45 },
  buttonLabel: { ...typography.bodyStrong },
  buttonLabelDark: { color: colors.textInverse },
  buttonLabelLight: { color: colors.text },

  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
  },

  boostedBadge: {
    alignSelf: 'flex-start',
    backgroundColor: colors.boostedBg,
    borderColor: colors.boosted,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
  },
  boostedText: { ...typography.label, color: colors.boosted },

  pill: {
    alignSelf: 'flex-start',
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
  },
  pillNeutral: { backgroundColor: colors.surfaceRaised },
  pillSuccess: { backgroundColor: '#1B3A2C' },
  pillWarning: { backgroundColor: '#3A2E1B' },
  pillDanger: { backgroundColor: '#3A1E1E' },
  pillText: { ...typography.caption, color: colors.text },

  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.lg },
  loadingLabel: { ...typography.body, color: colors.textMuted, marginTop: spacing.md },

  errorTitle: { ...typography.heading, color: colors.text, textAlign: 'center' },
  errorDetail: {
    ...typography.body,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  errorAction: { marginTop: spacing.lg },
});
