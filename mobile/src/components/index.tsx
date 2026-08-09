import { useEffect, useRef, type ReactNode } from 'react';
import {
  ActivityIndicator,
  Animated,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import * as Haptics from 'expo-haptics';

import { GlassSurface, type GlassTier, type GlassTint } from './GlassSurface';
import { Logo } from './Logo';
import { colors, radius, spacing, typography } from '../theme';

export { GlassSurface, Logo };

/** Screen chrome: safe area + Liquid Glass gradient background. */
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
      showsVerticalScrollIndicator={false}
    >
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.screenBody, style]}>{children}</View>
  );

  return (
    <View style={styles.screenWrapper}>
      <LinearGradient
        colors={[colors.bg.wine, colors.bg.roseDusk, colors.bg.wine]}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView style={styles.screen}>{content}</SafeAreaView>
    </View>
  );
}

export function Heading({ children, sub }: { children: ReactNode; sub?: string }) {
  return (
    <View style={styles.headingBlock}>
      <Text style={styles.headingText}>{children}</Text>
      {sub ? <Text style={styles.headingSub}>{sub}</Text> : null}
    </View>
  );
}

export function Body({
  children,
  muted = false,
  style,
}: {
  children: ReactNode;
  muted?: boolean;
  style?: StyleProp<any>;
}) {
  return <Text style={[styles.body, muted && styles.bodyMuted, style]}>{children}</Text>;
}

export function Button({
  label,
  onPress,
  variant = 'primary',
  loading = false,
  disabled = false,
  style,
}: {
  label: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'danger';
  loading?: boolean;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const inactive = disabled || loading;
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const handlePressIn = () => {
    if (inactive) return;
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    Animated.spring(scaleAnim, {
      toValue: 0.97,
      useNativeDriver: true,
      damping: 18,
      stiffness: 220,
    }).start();
  };

  const handlePressOut = () => {
    if (inactive) return;
    Animated.spring(scaleAnim, {
      toValue: 1,
      useNativeDriver: true,
      damping: 18,
      stiffness: 220,
    }).start();
  };

  const tier: GlassTier = variant === 'primary' ? 'floating' : 'ambient';
  const tint: GlassTint = variant === 'primary' ? 'rose' : variant === 'danger' ? 'danger' : 'neutral';

  return (
    <Animated.View style={[{ transform: [{ scale: scaleAnim }] }, style]}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ disabled: inactive, busy: loading }}
        onPress={onPress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={inactive}
        style={({ pressed }) => [
          styles.buttonWrapper,
          inactive && styles.buttonDisabled,
          pressed && styles.buttonPressed,
        ]}
      >
        <GlassSurface
          tier={tier}
          tint={tint}
          radius={radius.pill}
          style={styles.buttonGlass}
        >
          <View style={styles.buttonInner}>
            {loading ? (
              <LoadingDots />
            ) : (
              <Text
                style={[
                  styles.buttonLabel,
                  variant === 'primary' && styles.buttonLabelPrimary,
                  variant === 'secondary' && styles.buttonLabelSecondary,
                  variant === 'danger' && styles.buttonLabelDanger,
                ]}
              >
                {label}
              </Text>
            )}
          </View>
        </GlassSurface>
      </Pressable>
    </Animated.View>
  );
}

export function Card({
  children,
  style,
  tier = 'raised',
  tint = 'neutral',
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  tier?: GlassTier;
  tint?: GlassTint;
}) {
  return (
    <GlassSurface tier={tier} tint={tint} radius={radius.xl} style={style}>
      <View style={styles.cardInner}>{children}</View>
    </GlassSurface>
  );
}

/**
 * FR-6.2 (DECIDED): "Boosted profiles MUST be labeled 'Boosted' to viewers."
 * Mandatory product label requirement — rendered in Rose Pill, Tier 1 glass.
 */
export function BoostedBadge() {
  return (
    <View accessibilityLabel="This profile has boosted visibility">
      <Pill label="BOOSTED" tone="rose" />
    </View>
  );
}

export function Pill({
  label,
  tone = 'neutral',
  selected = false,
  onPress,
}: {
  label: string;
  tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'rose';
  selected?: boolean;
  onPress?: () => void;
}) {
  const tint: GlassTint =
    selected || tone === 'rose'
      ? 'rose'
      : tone === 'warning'
        ? 'warning'
        : tone === 'danger'
          ? 'danger'
          : 'neutral';

  const handlePress = () => {
    if (onPress) {
      void Haptics.selectionAsync();
      onPress();
    }
  };

  const pillContent = (
    <GlassSurface tier="ambient" tint={tint} radius={radius.pill} style={styles.pillGlass}>
      <View style={[styles.pillInner, selected && styles.pillSelectedInner]}>
        <Text style={[styles.pillText, selected && styles.pillSelectedText]}>{label}</Text>
      </View>
    </GlassSurface>
  );

  if (onPress) {
    return (
      <Pressable onPress={handlePress} accessibilityRole="button">
        {pillContent}
      </Pressable>
    );
  }

  return pillContent;
}

/** Small breathing dot typing/loading indicator (21st.dev Message Loading reference) */
function LoadingDots() {
  const anim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(anim, { toValue: 1, duration: 600, useNativeDriver: true }),
        Animated.timing(anim, { toValue: 0, duration: 600, useNativeDriver: true }),
      ])
    );
    loop.start();
    return () => loop.stop();
  }, [anim]);

  const scale = anim.interpolate({ inputRange: [0, 1], outputRange: [0.8, 1.2] });
  const opacity = anim.interpolate({ inputRange: [0, 1], outputRange: [0.5, 1] });

  return (
    <View style={styles.dotsRow}>
      <Animated.View style={[styles.dot, { transform: [{ scale }], opacity }]} />
      <Animated.View style={[styles.dot, { transform: [{ scale }], opacity, marginHorizontal: 6 }]} />
      <Animated.View style={[styles.dot, { transform: [{ scale }], opacity }]} />
    </View>
  );
}

export function Loading({ label }: { label?: string }) {
  return (
    <View style={styles.centered}>
      <GlassSurface tier="floating" tint="rose" radius={radius.pill} style={styles.loadingCapsule}>
        <View style={styles.loadingContent}>
          <LoadingDots />
          {label ? <Text style={styles.loadingLabel}>{label}</Text> : null}
        </View>
      </GlassSurface>
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
      <Card tier="raised" tint="danger" style={styles.errorCard}>
        <Text style={styles.errorTitle}>{title}</Text>
        {detail ? <Text style={styles.errorDetail}>{detail}</Text> : null}
        {onRetry ? (
          <View style={styles.errorAction}>
            <Button label="Try again" onPress={onRetry} variant="secondary" />
          </View>
        ) : null}
      </Card>
    </View>
  );
}

/** Clear Tier 1 Glass Input field */
export function GlassInput({
  label,
  error,
  leftElement,
  style,
  ...props
}: TextInputProps & {
  label?: string;
  error?: string;
  leftElement?: ReactNode;
  style?: StyleProp<ViewStyle>;
}) {
  return (
    <View style={[styles.inputContainer, style]}>
      {label ? <Text style={styles.inputLabel}>{label}</Text> : null}
      <GlassSurface tier="ambient" radius={radius.pill}>
        <View style={styles.inputInner}>
          {leftElement}
          <TextInput
            placeholderTextColor={colors.text.muted}
            style={styles.textInput}
            {...props}
          />
        </View>
      </GlassSurface>
      {error ? <Text style={styles.inputError}>{error}</Text> : null}
    </View>
  );
}

/** Six-cell glass capsule OTP input */
export function OtpInput({
  value,
  onChange,
  length = 6,
}: {
  value: string;
  onChange: (val: string) => void;
  length?: number;
}) {
  const digits = value.split('');

  return (
    <View style={styles.otpRow}>
      {Array.from({ length }).map((_, i) => {
        const digit = digits[i] || '';
        const isFilled = digit !== '';
        return (
          <GlassSurface
            key={i}
            tier="ambient"
            tint={isFilled ? 'rose' : 'neutral'}
            radius={radius.pill}
            style={styles.otpCell}
          >
            <View style={styles.otpCellInner}>
              <Text style={styles.otpText}>{digit}</Text>
            </View>
          </GlassSurface>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  screenWrapper: { flex: 1, backgroundColor: colors.bg.wine },
  screen: { flex: 1 },
  screenBody: { flex: 1, padding: spacing.lg },
  scrollContent: { padding: spacing.lg, paddingBottom: spacing.xxl },

  headingBlock: { marginBottom: spacing.lg },
  headingText: { ...typography.displayL, color: colors.text.primary },
  headingSub: { ...typography.bodyM, color: colors.text.muted, marginTop: spacing.sm },

  body: { ...typography.bodyL, color: colors.text.primary },
  bodyMuted: { color: colors.text.muted },

  buttonWrapper: { minHeight: 52, borderRadius: radius.pill },
  buttonGlass: { minHeight: 52 },
  buttonInner: {
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.lg,
  },
  buttonPressed: { opacity: 0.88 },
  buttonDisabled: { opacity: 0.35 },
  buttonLabel: { ...typography.label },
  buttonLabelPrimary: { color: colors.text.onRose },
  buttonLabelSecondary: { color: colors.warmBeige },
  buttonLabelDanger: { color: colors.rose[300] },

  cardInner: { padding: spacing.lg },

  pillGlass: { alignSelf: 'flex-start' },
  pillInner: { paddingHorizontal: spacing.md, paddingVertical: 6 },
  pillSelectedInner: { backgroundColor: 'rgba(207, 65, 115, 0.30)' },
  pillText: { ...typography.caption, color: colors.text.primary },
  pillSelectedText: { color: colors.text.onRose, fontFamily: 'Manrope_700Bold' },

  centered: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.lg },
  loadingCapsule: { paddingHorizontal: spacing.xl, paddingVertical: spacing.md },
  loadingContent: { alignItems: 'center', justifyContent: 'center' },
  loadingLabel: { ...typography.bodyM, color: colors.text.primary, marginTop: spacing.sm },

  dotsRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.rose[300] },

  errorCard: { width: '100%', maxWidth: 340, alignItems: 'center' },
  errorTitle: { ...typography.displayM, color: colors.text.primary, textAlign: 'center' },
  errorDetail: {
    ...typography.bodyM,
    color: colors.text.muted,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  errorAction: { marginTop: spacing.lg, width: '100%' },

  inputContainer: { marginBottom: spacing.md },
  inputLabel: { ...typography.label, color: colors.text.primary, marginBottom: spacing.xs },
  inputInner: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    height: 52,
  },
  textInput: {
    flex: 1,
    ...typography.bodyL,
    color: colors.text.primary,
    paddingVertical: spacing.xs,
  },
  inputError: { ...typography.caption, color: colors.dangerRed, marginTop: spacing.xs },

  otpRow: { flexDirection: 'row', justifyContent: 'space-between', marginVertical: spacing.lg },
  otpCell: { width: 46, height: 56 },
  otpCellInner: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  otpText: { ...typography.displayM, color: colors.text.primary },
});
