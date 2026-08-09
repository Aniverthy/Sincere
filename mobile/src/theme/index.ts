/**
 * Design tokens.
 *
 * Sincère's positioning is "verified, deliberate, fair" — the palette is deep and calm rather
 * than the saturated pinks the category defaults to. One source of truth so screens never
 * hard-code a colour.
 */

export const colors = {
  // Base
  background: '#12101A',
  surface: '#1C1826',
  surfaceRaised: '#262034',
  border: '#332C44',

  // Text
  text: '#F5F2FA',
  textMuted: '#A79FBA',
  textFaint: '#6F6684',
  textInverse: '#12101A',

  // Brand
  primary: '#C9A227',
  primaryPressed: '#A8871E',
  primaryMutedBg: '#2A2418',

  // Semantic
  success: '#4BAE7F',
  warning: '#E0A458',
  danger: '#D9534F',
  info: '#5B8FD9',

  /** FR-6.2: boosted profiles MUST be visibly labeled. Its own token so it cannot be
   *  quietly restyled into invisibility. */
  boosted: '#E0A458',
  boostedBg: '#2E2418',

  /** Verification states mirror the §6 lifecycle. */
  verified: '#4BAE7F',
  pending: '#E0A458',
  rejected: '#D9534F',
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
  pill: 999,
} as const;

export const typography = {
  display: { fontSize: 32, fontWeight: '700' as const, letterSpacing: -0.5 },
  title: { fontSize: 24, fontWeight: '700' as const, letterSpacing: -0.3 },
  heading: { fontSize: 19, fontWeight: '600' as const },
  body: { fontSize: 16, fontWeight: '400' as const, lineHeight: 23 },
  bodyStrong: { fontSize: 16, fontWeight: '600' as const },
  caption: { fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
  label: { fontSize: 12, fontWeight: '600' as const, letterSpacing: 0.6 },
} as const;

export const theme = { colors, spacing, radius, typography } as const;

export type Theme = typeof theme;
