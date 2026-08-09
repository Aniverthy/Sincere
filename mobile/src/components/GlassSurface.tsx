import { useEffect, useState, type ReactNode } from 'react';
import {
  AccessibilityInfo,
  StyleSheet,
  View,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { BlurView } from 'expo-blur';
import { LinearGradient } from 'expo-linear-gradient';

import { colors, radius as defaultRadius } from '../theme';

export type GlassTier = 'ambient' | 'raised' | 'floating';
export type GlassTint = 'neutral' | 'rose' | 'warning' | 'danger';

export interface GlassSurfaceProps {
  tier?: GlassTier;
  tint?: GlassTint;
  radius?: number;
  sheen?: boolean;
  style?: StyleProp<ViewStyle>;
  children?: ReactNode;
}

const tierConfig = {
  ambient: {
    intensity: 40,
    fill: 'rgba(255, 255, 255, 0.06)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.22)',
    shadow: {},
    solidBg: '#2D1F28',
  },
  raised: {
    intensity: 60,
    fill: 'rgba(255, 255, 255, 0.10)',
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.22)',
    shadow: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 8 },
      shadowOpacity: 0.35,
      shadowRadius: 24,
      elevation: 6,
    },
    solidBg: '#362331',
  },
  floating: {
    intensity: 80,
    fill: 'rgba(255, 255, 255, 0.14)',
    borderWidth: 1.5,
    borderColor: 'rgba(255, 255, 255, 0.25)',
    shadow: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 16 },
      shadowOpacity: 0.45,
      shadowRadius: 40,
      elevation: 12,
    },
    solidBg: '#42283A',
  },
} as const;

const tintFills: Record<GlassTint, string> = {
  neutral: 'transparent',
  rose: 'rgba(207, 65, 115, 0.22)',
  warning: 'rgba(255, 193, 94, 0.18)',
  danger: 'rgba(216, 90, 106, 0.22)',
};

const tintSolidBgs: Record<GlassTint, string> = {
  neutral: '#362331',
  rose: '#5C243B',
  warning: '#563E1F',
  danger: '#522027',
};

export function GlassSurface({
  tier = 'ambient',
  tint = 'neutral',
  radius = defaultRadius.lg,
  sheen = true,
  style,
  children,
}: GlassSurfaceProps) {
  const [reduceTransparency, setReduceTransparency] = useState(false);

  useEffect(() => {
    let isMounted = true;
    void AccessibilityInfo.isReduceTransparencyEnabled().then((enabled) => {
      if (isMounted) setReduceTransparency(enabled);
    });
    const sub = AccessibilityInfo.addEventListener('reduceTransparencyChanged', (enabled) => {
      setReduceTransparency(enabled);
    });
    return () => {
      isMounted = false;
      sub.remove();
    };
  }, []);

  const config = tierConfig[tier];
  const borderRadius = radius;

  if (reduceTransparency) {
    const solidBg = tint !== 'neutral' ? tintSolidBgs[tint] : config.solidBg;
    return (
      <View
        style={[
          styles.container,
          config.shadow,
          {
            borderRadius,
            backgroundColor: solidBg,
            borderWidth: config.borderWidth,
            borderColor: config.borderColor,
          },
          style,
        ]}
      >
        {children}
      </View>
    );
  }

  const tintFill = tintFills[tint];

  return (
    <View
      style={[
        styles.container,
        config.shadow,
        {
          borderRadius,
          borderWidth: config.borderWidth,
          borderColor: config.borderColor,
        },
        style,
      ]}
    >
      <BlurView
        intensity={config.intensity}
        tint="dark"
        style={[
          styles.blurView,
          {
            borderRadius,
            backgroundColor: config.fill,
          },
        ]}
      >
        {tintFill !== 'transparent' && (
          <View style={[styles.tintOverlay, { backgroundColor: tintFill, borderRadius }]} />
        )}
        {sheen && (
          <LinearGradient
            colors={['rgba(255, 255, 255, 0.12)', 'transparent']}
            start={{ x: 0.1, y: 0.1 }}
            end={{ x: 0.8, y: 0.9 }}
            style={[styles.sheenGradient, { borderRadius }]}
          />
        )}
        {children}
      </BlurView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    overflow: 'hidden',
  },
  blurView: {
    overflow: 'hidden',
  },
  tintOverlay: {
    ...StyleSheet.absoluteFillObject,
  },
  sheenGradient: {
    ...StyleSheet.absoluteFillObject,
    pointerEvents: 'none',
  },
});
