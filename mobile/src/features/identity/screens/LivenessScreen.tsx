import { CameraView, useCameraPermissions, useMicrophonePermissions } from 'expo-camera';
import * as FileSystem from 'expo-file-system/legacy';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../../api/client';
import { Body, Button, Heading, Loading, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { identityApi, type LivenessSession } from '../api';
import { useOnboarding } from '../state';

/**
 * Liveness capture (FR-1.2, §4, §5).
 *
 * §4: "Camera flow issues **server-provided randomized prompts** (blink, head turn); uploads
 * short video to a pre-signed object-storage URL."
 *
 * The randomization is the whole defence and it comes from the server — a client that chose
 * its own prompts could be replayed with a pre-recorded video of someone else performing a
 * known sequence. This screen only *displays* the sequence it was handed.
 */

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
  const [permission, requestPermission] = useCameraPermissions();
  // `recordAsync` captures video WITH audio, so it fails outright without the microphone
  // permission — even though nothing here ever listens to the audio track.
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

  // Advance the on-screen instruction while recording, so the user performs the sequence in
  // the order the server issued it.
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

      // Straight to object storage via the pre-signed URL (§4) — the video never transits
      // the API, and §18 discards it after the embedding is produced.
      //
      // `uploadAsync` rather than fetch+blob: React Native has no real Blob backing a file://
      // URI, so the body would arrive empty. It also matters more here than for photos, since
      // a liveness video is far larger and streaming avoids holding it in memory.
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
        <Heading sub="Sincère verifies every member with a short video, so nobody is talking to a bot or a stolen photo. It is recorded once and deleted after checking.">
          Camera access
        </Heading>
        <Button
          label="Allow camera"
          onPress={() => {
            void (async () => {
              // Both, in sequence: video capture needs the microphone even though the audio
              // is never used, and a partial grant fails at record time with a cryptic error.
              if (!permission.granted) await requestPermission();
              if (!micPermission.granted) await requestMicPermission();
            })();
          }}
        />
        <View style={styles.note}>
          <Body muted>
            We keep a mathematical signature of your face, not the video. The signature cannot
            be turned back into a picture.
          </Body>
          <View style={styles.note}>
            <Body muted>
              Android also asks for the microphone: video recording requires it. Sincère never
              listens to the audio, and the recording is deleted after checking.
            </Body>
          </View>
        </View>
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
      <CameraView ref={camera} style={styles.camera} facing="front" mode="video" />

      <View style={styles.overlay}>
        <View style={styles.promptCard}>
          <Text style={styles.promptStep}>
            STEP {promptIndex + 1} OF {session.prompt_sequence.length}
          </Text>
          <Text style={styles.promptText}>
            {PROMPT_COPY[currentPrompt] ?? currentPrompt.replace(/_/g, ' ')}
          </Text>
        </View>

        {error ? <Text style={styles.error}>{error}</Text> : null}

        <View style={styles.controls}>
          {recording ? (
            <Pressable onPress={stop} style={[styles.button, styles.stop]}>
              <Text style={styles.buttonText}>Done</Text>
            </Pressable>
          ) : (
            <Pressable onPress={() => void capture()} style={styles.button}>
              <Text style={styles.buttonText}>Start</Text>
            </Pressable>
          )}
          <Text style={styles.hint}>
            {recording
              ? 'Follow each instruction as it appears.'
              : 'Hold your phone at eye level in good light.'}
          </Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  camera: { ...StyleSheet.absoluteFillObject },
  overlay: { flex: 1, justifyContent: 'space-between', padding: spacing.lg },
  promptCard: {
    marginTop: spacing.xxl,
    backgroundColor: 'rgba(18,16,26,0.88)',
    borderRadius: radius.lg,
    padding: spacing.lg,
    alignItems: 'center',
  },
  promptStep: { ...typography.label, color: colors.primary },
  promptText: {
    ...typography.title,
    color: colors.text,
    textAlign: 'center',
    marginTop: spacing.xs,
  },
  error: {
    ...typography.caption,
    color: colors.danger,
    backgroundColor: 'rgba(18,16,26,0.9)',
    padding: spacing.sm,
    borderRadius: radius.sm,
    textAlign: 'center',
  },
  controls: { alignItems: 'center', gap: spacing.sm, marginBottom: spacing.xl },
  button: {
    width: 88,
    height: 88,
    borderRadius: 44,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stop: { backgroundColor: colors.danger },
  buttonText: { ...typography.bodyStrong, color: colors.textInverse },
  hint: {
    ...typography.caption,
    color: colors.text,
    textAlign: 'center',
    backgroundColor: 'rgba(18,16,26,0.75)',
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.sm,
  },
  note: { marginTop: spacing.lg },
});
