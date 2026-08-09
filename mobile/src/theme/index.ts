/**
 * Liquid Glass Design System Tokens for Sincère.
 *
 * Implements Apple's Liquid Glass material guidelines (iOS 26+ visual language),
 * incorporating Fraunces serif & Manrope sans-serif typography, wine-to-beige gradients,
 * translucent glass tiers, and Rose accent glint tokens.
 */

export const colors = {
  // Base backdrop gradient tokens
  bg: {
    wine: '#5D3140',
    roseDusk: '#8B4A5F',
    warm: '#F6D8BD',
  },

  // Translucent glass material fills
  glass: {
    ambient: {
      fill: 'rgba(255, 255, 255, 0.06)',
      border: 'rgba(255, 255, 255, 0.22)',
      blur: 40,
    },
    raised: {
      fill: 'rgba(255, 255, 255, 0.10)',
      border: 'rgba(255, 255, 255, 0.22)',
      blur: 60,
      shadow: '0px 8px 24px rgba(0, 0, 0, 0.35)',
    },
    floating: {
      fill: 'rgba(255, 255, 255, 0.14)',
      border: 'rgba(255, 255, 255, 0.25)',
      blur: 80,
      shadow: '0px 16px 40px rgba(0, 0, 0, 0.45)',
    },
    sheen: 'rgba(255, 255, 255, 0.08)',
  },

  // Rose accent tokens
  rose: {
    300: '#F39399',
    500: '#CF4173',
    700: '#A23D5F',
  },

  // Warm neutral accent
  warmBeige: '#F6D8BD',

  // Semantics
  passSlate: '#A89CB8',
  warningAmber: '#FFC15E',
  dangerRed: '#D85A6A',
  successGreen: '#4BAE7F',

  // Text tokens
  text: {
    primary: '#F6D8BD',
    muted: 'rgba(246, 216, 189, 0.65)',
    onRose: '#FEFAF6',
    inverse: '#5D3140',
  },

  // Legacy mappings for backward-compatibility with existing feature code
  background: '#5D3140',
  surface: 'rgba(255, 255, 255, 0.10)',
  surfaceRaised: 'rgba(255, 255, 255, 0.14)',
  border: 'rgba(255, 255, 255, 0.22)',

  primary: '#CF4173',
  primaryPressed: '#A23D5F',
  primaryMutedBg: 'rgba(207, 65, 115, 0.20)',

  success: '#4BAE7F',
  warning: '#FFC15E',
  danger: '#D85A6A',
  info: '#5B8FD9',

  boosted: '#CF4173',
  boostedBg: 'rgba(207, 65, 115, 0.15)',

  verified: '#4BAE7F',
  pending: '#FFC15E',
  rejected: '#D85A6A',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 20,
  xl: 24,
  pill: 9999,
} as const;

export const typography = {
  displayXL: {
    fontFamily: 'Fraunces_600SemiBold',
    fontSize: 40,
    lineHeight: 44,
    color: colors.text.primary,
  },
  displayL: {
    fontFamily: 'Fraunces_500Medium',
    fontSize: 28,
    lineHeight: 34,
    color: colors.text.primary,
  },
  displayM: {
    fontFamily: 'Fraunces_500Medium',
    fontSize: 22,
    lineHeight: 28,
    color: colors.text.primary,
  },
  bodyL: {
    fontFamily: 'Manrope_400Regular',
    fontSize: 17,
    lineHeight: 24,
    color: colors.text.primary,
  },
  bodyM: {
    fontFamily: 'Manrope_400Regular',
    fontSize: 15,
    lineHeight: 21,
    color: colors.text.primary,
  },
  label: {
    fontFamily: 'Manrope_600SemiBold',
    fontSize: 13,
    lineHeight: 16,
    letterSpacing: 0.4,
    color: colors.text.primary,
  },
  caption: {
    fontFamily: 'Manrope_500Medium',
    fontSize: 12,
    lineHeight: 16,
    color: colors.text.muted,
  },

  // Legacy mappings for fallback
  display: { fontFamily: 'Fraunces_600SemiBold', fontSize: 32, lineHeight: 38 },
  title: { fontFamily: 'Fraunces_500Medium', fontSize: 24, lineHeight: 30 },
  heading: { fontFamily: 'Fraunces_500Medium', fontSize: 19, lineHeight: 25 },
  body: { fontFamily: 'Manrope_400Regular', fontSize: 16, lineHeight: 23 },
  bodyStrong: { fontFamily: 'Manrope_600SemiBold', fontSize: 16, lineHeight: 23 },
} as const;

export const motion = {
  buttonPress: { damping: 18, stiffness: 220, mass: 0.9 },
  cardEntrance: { damping: 20, stiffness: 160 },
  swipeRelease: { damping: 14, stiffness: 120 },
  tagToggle: { damping: 16, stiffness: 200 },
} as const;

export const theme = { colors, spacing, radius, typography, motion } as const;

export type Theme = typeof theme;
