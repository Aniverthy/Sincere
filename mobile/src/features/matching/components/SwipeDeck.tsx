import { useCallback, useRef } from 'react';
import { Dimensions, Image, Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  interpolate,
  Extrapolation,
} from 'react-native-reanimated';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import { LinearGradient } from 'expo-linear-gradient';
import * as Haptics from 'expo-haptics';

import { BoostedBadge, GlassSurface, Pill } from '../../../components';
import { colors, motion, radius, spacing, typography } from '../../../theme';
import type { DailyCandidate } from '../api';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const SWIPE_THRESHOLD = SCREEN_WIDTH * 0.35;

interface SwipeDeckProps {
  candidates: DailyCandidate[];
  currentIndex: number;
  onSwipe: (candidate: DailyCandidate, direction: 'left' | 'right') => void;
}

export function SwipeDeck({ candidates, currentIndex, onSwipe }: SwipeDeckProps) {
  const currentCandidate = candidates[currentIndex];
  const nextCandidate = candidates[currentIndex + 1];
  const thirdCandidate = candidates[currentIndex + 2];

  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);
  const startX = useSharedValue(0);
  const startY = useSharedValue(0);
  const isSwiping = useRef(false);

  const handleSwipeComplete = useCallback(
    (direction: 'left' | 'right') => {
      if (isSwiping.current || !currentCandidate) return;
      isSwiping.current = true;
      void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      onSwipe(currentCandidate, direction);
      translateX.value = 0;
      translateY.value = 0;
      isSwiping.current = false;
    },
    [currentCandidate, onSwipe, translateX, translateY],
  );

  const panGesture = Gesture.Pan()
    .onStart(() => {
      startX.value = translateX.value;
      startY.value = translateY.value;
    })
    .onUpdate((event) => {
      translateX.value = startX.value + event.translationX;
      translateY.value = startY.value + event.translationY;
    })
    .onEnd((event) => {
      if (Math.abs(event.translationX) > SWIPE_THRESHOLD || Math.abs(event.velocityX) > 800) {
        const direction = event.translationX > 0 ? 'right' : 'left';
        const targetX = direction === 'right' ? SCREEN_WIDTH * 1.5 : -SCREEN_WIDTH * 1.5;
        translateX.value = withSpring(targetX, motion.swipeRelease, () => {
          runOnJS(handleSwipeComplete)(direction);
        });
      } else {
        translateX.value = withSpring(0, motion.swipeRelease);
        translateY.value = withSpring(0, motion.swipeRelease);
      }
    });

  const animatedCardStyle = useAnimatedStyle(() => {
    const rotateY = interpolate(
      translateX.value,
      [-SCREEN_WIDTH, 0, SCREEN_WIDTH],
      [-18, 0, 18],
      Extrapolation.CLAMP,
    );
    const rotateZ = interpolate(
      translateX.value,
      [-SCREEN_WIDTH, 0, SCREEN_WIDTH],
      [-8, 0, 8],
      Extrapolation.CLAMP,
    );

    return {
      transform: [
        { translateX: translateX.value },
        { translateY: translateY.value },
        { perspective: 800 },
        { rotateY: `${rotateY}deg` },
        { rotateZ: `${rotateZ}deg` },
      ],
    };
  });

  const passButtonAnimStyle = useAnimatedStyle(() => {
    const scale = interpolate(
      translateX.value,
      [-SWIPE_THRESHOLD, 0],
      [1.15, 1],
      Extrapolation.CLAMP,
    );
    return { transform: [{ scale }] };
  });

  const likeButtonAnimStyle = useAnimatedStyle(() => {
    const scale = interpolate(
      translateX.value,
      [0, SWIPE_THRESHOLD],
      [1, 1.15],
      Extrapolation.CLAMP,
    );
    return { transform: [{ scale }] };
  });

  if (!currentCandidate) return null;

  return (
    <View style={styles.container}>
      {/* Background card #3 */}
      {thirdCandidate && (
        <View style={[styles.cardContainer, styles.stackCard3]}>
          <ProfileCard candidate={thirdCandidate} />
        </View>
      )}

      {/* Background card #2 */}
      {nextCandidate && (
        <View style={[styles.cardContainer, styles.stackCard2]}>
          <ProfileCard candidate={nextCandidate} />
        </View>
      )}

      {/* Interactive Top Card #1 */}
      <GestureDetector gesture={panGesture}>
        <Animated.View style={[styles.cardContainer, animatedCardStyle]}>
          <ProfileCard candidate={currentCandidate} />
        </Animated.View>
      </GestureDetector>

      {/* Floating Action Buttons below Card Stack */}
      <View style={styles.actionsRow}>
        <Animated.View style={passButtonAnimStyle}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Pass candidate"
            onPress={() => handleSwipeComplete('left')}
            style={styles.actionPressable}
          >
            <GlassSurface tier="floating" tint="neutral" radius={36} style={styles.actionButtonGlass}>
              <View style={styles.actionButtonInner}>
                <Text style={styles.passIcon}>✕</Text>
              </View>
            </GlassSurface>
          </Pressable>
        </Animated.View>

        <Animated.View style={likeButtonAnimStyle}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Like candidate"
            onPress={() => handleSwipeComplete('right')}
            style={styles.actionPressable}
          >
            <GlassSurface tier="floating" tint="rose" radius={36} style={styles.actionButtonGlass}>
              <View style={styles.actionButtonInner}>
                <Text style={styles.likeIcon}>♥</Text>
              </View>
            </GlassSurface>
          </Pressable>
        </Animated.View>
      </View>
    </View>
  );
}

function ProfileCard({ candidate }: { candidate: DailyCandidate }) {
  return (
    <GlassSurface tier="raised" radius={radius.xl} sheen style={styles.cardGlass}>
      <View style={styles.photoContainer}>
        {candidate.photos[0]?.url ? (
          <Image source={{ uri: candidate.photos[0].url }} style={styles.photo} />
        ) : (
          <View style={styles.photoPlaceholder}>
            <Text style={styles.placeholderMonogram}>{candidate.name?.[0] ?? 'S'}</Text>
          </View>
        )}

        <LinearGradient
          colors={['transparent', 'rgba(93, 49, 64, 0.95)']}
          start={{ x: 0.5, y: 0.5 }}
          end={{ x: 0.5, y: 1.0 }}
          style={styles.photoGradientScrim}
        />

        {candidate.boosted && (
          <View style={styles.boostedBadgeWrapper}>
            <BoostedBadge />
          </View>
        )}

        <View style={styles.photoOverlayText}>
          <Text style={styles.nameAge}>
            {candidate.name ?? 'Someone'}
            {candidate.age ? `, ${candidate.age}` : ''}
          </Text>
        </View>
      </View>

      <View style={styles.detailsPanel}>
        {candidate.bio ? <Text style={styles.bioText}>{candidate.bio}</Text> : null}

        {candidate.prompts.map((prompt) => (
          <View key={prompt.q} style={styles.promptBlock}>
            <Text style={styles.promptQ}>{prompt.q}</Text>
            <Text style={styles.promptA}>{prompt.a}</Text>
          </View>
        ))}

        {candidate.tags.length > 0 ? (
          <View style={styles.tagsRow}>
            {candidate.tags.map((tag) => (
              <Pill key={tag} label={tag} tone="neutral" />
            ))}
          </View>
        ) : null}
      </View>
    </GlassSurface>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', position: 'relative' },
  cardContainer: { width: '100%', height: '82%', position: 'absolute', top: 0 },
  stackCard2: { transform: [{ scale: 0.95 }, { translateY: 12 }], opacity: 0.85 },
  stackCard3: { transform: [{ scale: 0.90 }, { translateY: 24 }], opacity: 0.65 },

  cardGlass: { flex: 1, overflow: 'hidden' },

  photoContainer: { width: '100%', height: 340, position: 'relative', overflow: 'hidden' },
  photo: { width: '100%', height: '100%' },
  photoPlaceholder: {
    width: '100%',
    height: '100%',
    backgroundColor: 'rgba(255,255,255,0.05)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  placeholderMonogram: { fontFamily: 'Fraunces_600SemiBold', fontSize: 64, color: colors.warmBeige },
  photoGradientScrim: { ...StyleSheet.absoluteFillObject },

  boostedBadgeWrapper: { position: 'absolute', top: spacing.md, right: spacing.md },
  photoOverlayText: { position: 'absolute', bottom: spacing.md, left: spacing.md, right: spacing.md },
  nameAge: { fontFamily: 'Fraunces_600SemiBold', fontSize: 26, lineHeight: 32, color: colors.warmBeige },

  detailsPanel: { padding: spacing.md, gap: spacing.sm },
  bioText: { ...typography.bodyM, color: colors.text.primary, lineHeight: 21 },
  promptBlock: { borderTopWidth: 1, borderTopColor: colors.glass.ambient.border, paddingTop: spacing.xs },
  promptQ: { ...typography.caption, color: colors.text.muted },
  promptA: { ...typography.bodyL, color: colors.warmBeige, marginTop: 2 },
  tagsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs },

  actionsRow: {
    position: 'absolute',
    bottom: spacing.lg,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xxl,
  },
  actionPressable: { width: 72, height: 72, borderRadius: 36 },
  actionButtonGlass: { width: 72, height: 72, borderRadius: 36 },
  actionButtonInner: { width: 72, height: 72, alignItems: 'center', justifyContent: 'center' },
  passIcon: { fontSize: 28, color: colors.passSlate, fontFamily: 'Manrope_700Bold' },
  likeIcon: { fontSize: 30, color: colors.text.onRose },
});
