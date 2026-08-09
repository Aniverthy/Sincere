import { CameraView, useCameraPermissions, useMicrophonePermissions } from 'expo-camera';
import * as FileSystem from 'expo-file-system/legacy';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';

import { ApiError } from '../../../api/client';
import { Body, Button, Card, GlassSurface, Heading, Loading, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { identityApi, type LivenessSession } from '../api';
import { useOnboarding } from '../state';

const PROMPT_COPY: Record<string, string> = {
  blink_twice: 'Blink twice',
  turn_head_left: 'Turn your head to the left',
  turn_head_right: 'Turn your head to the right',
  look_up: 'Look up',
  smile: 'Smile',
  open_mouth: 'Open your mouth',
};

const SECONDS_PER_PROMPT = 3;

export function LivenessScreen() {
  const setStep = useOnboarding((s) => s.setStep);
  const insets = useSafeAreaInsets();
  const [permission, requestPermission] = useCameraPermissions();
  const [micPermission, requestMicPermission] = useMicrophonePermissions();
  const camera = useRef<CameraView | null>(null);

  const [session, setSession] = useState<LivenessSession | null>(null);
  const [recording, setRecording] = useState(false);
  const [promptIndex, setPromptIndex] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    identityApi
      .startLiveness()
      .then(setSession)
      .catch(() => setError('Could not start verification. Please try again.'));
  }, []);

  useEffect(() => {
    if (!recording || !session) return;
    const timer = setInterval(() => {
      setPromptIndex((index) => {
        if (index + 1 >= session.prompt_sequence.length) {
          clearInterval(timer);
          return index;
        }
        return index + 1;
      });
    }, SECONDS_PER_PROMPT * 1000);
    return () => clearInterval(timer);
  }, [recording, session]);

  const capture = useCallback(async () => {
    if (!camera.current || !session) return;
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);

    setError(null);
    setRecording(true);
    setPromptIndex(0);

    try {
      const video = await camera.current.recordAsync({
        maxDuration: session.prompt_sequence.length * SECONDS_PER_PROMPT + 2,
      });
      setRecording(false);
      if (!video?.uri) throw new Error('no capture');

      setBusy(true);

      const upload = await FileSystem.uploadAsync(session.upload_url, video.uri, {
        httpMethod: 'PUT',
        uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
        headers: { 'Content-Type': 'video/mp4' },
      });
      if (upload.status >= 400) {
        throw new Error(`upload failed with ${upload.status}`);
      }

      await identityApi.submitLiveness(session.session_id, session.object_key);
      setStep('verifying');
    } catch (err) {
      setRecording(false);
      setError(
        err instanceof ApiError
          ? (err.problem.detail ?? err.problem.title)
          : 'That capture did not work. Make sure your face is well lit and try again.',
      );
    } finally {
      setBusy(false);
    }
  }, [session, setStep]);

  const stop = useCallback(() => {
    camera.current?.stopRecording();
  }, []);

  if (!permission || !micPermission) return <Loading />;

  if (!permission.granted || !micPermission.granted) {
    return (
      <Screen>
        <Card tier="raised" style={styles.permissionCard}>
          <Heading sub="Sincère verifies every member with a short video, so nobody is talking to a bot or a stolen photo. It is recorded once and deleted after checking.">
            Camera access
          </Heading>
          <Button
            label="Allow camera & microphone"
            onPress={() => {
              void (async () => {
                if (!permission.granted) await requestPermission();
                if (!micPermission.granted) await requestMicPermission();
              })();
            }}
          />
          <View style={styles.noteBlock}>
            <Body muted>
              We keep a mathematical signature of your face, not the video. The signature cannot
              be turned back into a picture.
            </Body>
          </View>
        </Card>
      </Screen>
    );
  }

  if (busy) return <Loading label="Checking it is really you" />;
  if (!session) {
    return error ? (
      <Screen>
        <Heading>Verification unavailable</Heading>
        <Body muted>{error}</Body>
      </Screen>
    ) : (
      <Loading label="Preparing your check" />
    );
  }

  const currentPrompt = session.prompt_sequence[promptIndex];

  return (
    <View style={styles.container}>
      {/* Full-bleed native camera — NO glass overlay over video itself */}
      <CameraView ref={camera} style={styles.camera} facing="front" mode="video" />

      <View style={[styles.overlay, { paddingTop: Math.max(insets.top, spacing.lg) }]}>
        {/* Tier 3 Floating Glass Top Prompt Card */}
        <GlassSurface tier="floating" radius={radius.xl} sheen style={styles.promptCardGlass}>
          <View style={styles.promptCardInner}>
            <Text style={styles.promptStep}>
              STEP {promptIndex + 1} OF {session.prompt_sequence.length}
            </Text>
            <Text style={styles.promptText}>
              {PROMPT_COPY[currentPrompt] ?? currentPrompt.replace(/_/g, ' ')}
            </Text>
          </View>
        </GlassSurface>

        {error ? (
          <GlassSurface tier="ambient" tint="danger" radius={radius.md} style={styles.errorGlass}>
            <Text style={styles.errorText}>{error}</Text>
          </GlassSurface>
        ) : null}

        {/* Shutter controls */}
        <View style={[styles.controls, { paddingBottom: Math.max(insets.bottom, spacing.xl) }]}>
          {/* Tip banner */}
          <GlassSurface tier="ambient" radius={radius.pill} style={styles.tipBanner}>
            <Text style={styles.tipText}>
              {recording
                ? 'Follow each instruction as it appears'
                : 'Hold phone at eye level in good light'}
            </Text>
          </GlassSurface>

          {/* Lens Ring Shutter Button */}
          <Pressable
            onPress={recording ? stop : () => void capture()}
            accessibilityRole="button"
            accessibilityLabel={recording ? 'Stop recording' : 'Start recording'}
          >
            <GlassSurface
              tier="floating"
              tint={recording ? 'rose' : 'neutral'}
              radius={44}
              style={styles.shutterRing}
            >
              <View style={[styles.shutterInner, recording && styles.shutterInnerRecording]} />
            </GlassSurface>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  camera: { ...StyleSheet.absoluteFillObject },
  overlay: { flex: 1, justifyContent: 'space-between', paddingHorizontal: spacing.lg },

  promptCardGlass: { marginTop: spacing.md },
  promptCardInner: { padding: spacing.lg, alignItems: 'center' },
  promptStep: { ...typography.label, color: colors.rose[300] },
  promptText: {
    fontFamily: 'Fraunces_500Medium',
    fontSize: 24,
    lineHeight: 30,
    color: colors.warmBeige,
    textAlign: 'center',
    marginTop: spacing.xs,
  },

  errorGlass: { padding: spacing.md, marginVertical: spacing.md },
  errorText: { ...typography.caption, color: colors.dangerRed, textAlign: 'center' },

  controls: { alignItems: 'center', gap: spacing.md },
  tipBanner: { paddingHorizontal: spacing.md, paddingVertical: 6 },
  tipText: { ...typography.caption, color: colors.warmBeige },

  shutterRing: { width: 88, height: 88, borderRadius: 44, alignItems: 'center', justifyContent: 'center' },
  shutterInner: { width: 68, height: 68, borderRadius: 34, borderWidth: 3, borderColor: colors.warmBeige },
  shutterInnerRecording: { backgroundColor: colors.rose[500], borderWidth: 0 },

  permissionCard: { marginVertical: 'auto' },
  noteBlock: { marginTop: spacing.lg },
});
