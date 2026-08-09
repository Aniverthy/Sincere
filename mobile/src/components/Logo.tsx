import { Image, StyleSheet, Text, View, type ImageSourcePropType } from 'react-native';

import { GlassSurface } from './GlassSurface';
import { colors, radius } from '../theme';

interface LogoProps {
  size?: number; // default 72 for auth/splash, 32 for nav header
  source?: ImageSourcePropType;
}

export function Logo({ size = 72, source }: LogoProps) {
  const isSmall = size <= 40;
  const fontSize = isSmall ? 16 : 38;
  const glintSize = isSmall ? 4 : 10;
  const glintTop = isSmall ? 4 : 12;
  const glintRight = isSmall ? 8 : 20;

  return (
    <GlassSurface
      tier="floating"
      radius={radius.pill}
      style={{ width: size, height: size, borderRadius: size / 2 }}
    >
      <View style={[styles.inner, { width: size, height: size }]}>
        {source ? (
          <Image source={source} style={styles.image} resizeMode="contain" />
        ) : (
          <View style={styles.monogramContainer}>
            <Text style={[styles.monogramText, { fontSize }]}>S</Text>
            {/* Grave accent Rose glint motif */}
            <View
              style={[
                styles.roseGlint,
                {
                  width: glintSize * 1.5,
                  height: glintSize / 2 + 1,
                  top: glintTop,
                  right: glintRight,
                  borderRadius: glintSize / 2,
                },
              ]}
            />
          </View>
        )}
      </View>
    </GlassSurface>
  );
}

const styles = StyleSheet.create({
  inner: {
    alignItems: 'center',
    justifyContent: 'center',
    position: 'relative',
  },
  image: {
    width: '70%',
    height: '70%',
  },
  monogramContainer: {
    position: 'relative',
    alignItems: 'center',
    justifyContent: 'center',
  },
  monogramText: {
    fontFamily: 'Fraunces_600SemiBold',
    color: colors.warmBeige,
    textAlign: 'center',
  },
  roseGlint: {
    position: 'absolute',
    backgroundColor: colors.rose[500],
    transform: [{ rotate: '-35deg' }],
  },
});
