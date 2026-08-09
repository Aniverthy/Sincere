import * as FileSystem from 'expo-file-system/legacy';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { useCallback, useMemo, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { ApiError } from '../../../api/client';
import { Body, Button, Card, Heading, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { identityApi } from '../api';
import { useOnboarding } from '../state';

/**
 * Profile builder — prompts, tags, photos (§4 screen map, FR-1.1).
 *
 * Comes **before** the liveness capture, which the §4 diagram draws the other way round. §5's
 * sequence diagram has it in this order ("profile data, photos" then "request liveness
 * session"), and FR-1.5 settles it: the photo-to-selfie match needs photos to already exist
 * when the selfie is taken.
 *
 * Validation is shown, never silent. An earlier version disabled the continue button until
 * every requirement was met and said nothing about which one was missing — the user was left
 * tapping a dead control. Requirements are now listed with live tick marks, and the button
 * stays tappable so pressing it can explain what is outstanding.
 */

const PROMPT_QUESTIONS = [
  'A perfect Sunday',
  'The thing I get irrationally excited about',
  'I will not shut up about',
  'An opinion I will defend',
  'Best meal I have had this year',
];

const TAG_OPTIONS = [
  'coffee', 'films', 'hiking', 'books', 'music', 'cooking', 'travel', 'art',
  'running', 'photography', 'gaming', 'theatre', 'cycling', 'dogs', 'cats',
  'yoga', 'football', 'cricket', 'writing', 'dancing',
];

const MIN_TAGS = 3;

/** Insert the dashes as the user types, so the format can't be got wrong. */
function formatDob(input: string): string {
  const digits = input.replace(/\D/g, '').slice(0, 8);
  if (digits.length <= 4) return digits;
  if (digits.length <= 6) return `${digits.slice(0, 4)}-${digits.slice(4)}`;
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6)}`;
}

function ageFrom(dob: string): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dob)) return null;
  const date = new Date(`${dob}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  const now = new Date();
  let age = now.getUTCFullYear() - date.getUTCFullYear();
  const beforeBirthday =
    now.getUTCMonth() < date.getUTCMonth() ||
    (now.getUTCMonth() === date.getUTCMonth() && now.getUTCDate() < date.getUTCDate());
  if (beforeBirthday) age -= 1;
  return age;
}

export function ProfileBuilderScreen() {
  const setStep = useOnboarding((s) => s.setStep);

  const [name, setName] = useState('');
  const [dob, setDob] = useState('');
  const [bio, setBio] = useState('');
  const [tags, setTags] = useState<string[]>([]);
  const [promptIndex, setPromptIndex] = useState(0);
  const [promptAnswer, setPromptAnswer] = useState('');
  const [photos, setPhotos] = useState<
    { uri: string; object_key: string; public_url: string }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const age = ageFrom(dob);

  /** Each requirement, with the reason it exists, so the UI can explain itself. */
  const requirements = useMemo(
    () => [
      { label: 'Your name', met: name.trim().length > 0 },
      {
        label:
          age === null
            ? 'Date of birth (YYYY-MM-DD)'
            : age < 18
              ? 'You must be 18 or older'
              : `Date of birth — you are ${age}`,
        met: age !== null && age >= 18 && age < 120,
      },
      {
        label: `At least ${MIN_TAGS} interests (${tags.length} chosen)`,
        met: tags.length >= MIN_TAGS,
      },
      { label: 'At least one photo', met: photos.length > 0 },
    ],
    [name, age, tags.length, photos.length],
  );

  const missing = requirements.filter((r) => !r.met);

  const toggleTag = (tag: string) =>
    setTags((current) =>
      current.includes(tag) ? current.filter((t) => t !== tag) : [...current, tag],
    );

  /**
   * Upload straight to object storage through a pre-signed URL (§4).
   * The bytes never transit the API — a §19 performance choice and a §18 minimization one.
   */
  const addPhoto = useCallback(async () => {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError('Photo access is needed to add pictures to your profile.');
      return;
    }

    const picked = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.8,
      allowsEditing: true,
      aspect: [4, 5],
    });
    if (picked.canceled || !picked.assets[0]) return;

    const asset = picked.assets[0];
    setBusy(true);
    setError(null);
    try {
      const target = await identityApi.photoUploadUrl('image/jpeg');

      // `fetch(fileUri).blob()` is unreliable in React Native — Hermes has no real Blob
      // backing a file:// URI, so the body arrives empty or the call throws outright.
      // `uploadAsync` streams the file from disk, which is what it exists for.
      const result = await FileSystem.uploadAsync(target.upload_url, asset.uri, {
        httpMethod: 'PUT',
        uploadType: FileSystem.FileSystemUploadType.BINARY_CONTENT,
        headers: { 'Content-Type': 'image/jpeg' },
      });
      if (result.status >= 400) throw new Error(`upload failed with ${result.status}`);

      setPhotos((current) => [
        ...current,
        {
          uri: asset.uri,
          object_key: target.object_key,
          // Store what the server will serve, not the local file:// path — that URI is
          // meaningless to anyone else looking at the profile.
          public_url: target.public_url ?? asset.uri,
        },
      ]);
    } catch {
      setError('That photo could not be uploaded. Try another.');
    } finally {
      setBusy(false);
    }
  }, []);

  const removePhoto = (objectKey: string) =>
    setPhotos((current) => current.filter((p) => p.object_key !== objectKey));

  /** §4/FR-3.3: location captured once, no background permission requested. */
  const captureLocation = useCallback(async () => {
    const { status } = await Location.requestForegroundPermissionsAsync();
    if (status !== 'granted') return false;
    const position = await Location.getCurrentPositionAsync({});
    await identityApi.setLocation(position.coords.latitude, position.coords.longitude);
    return true;
  }, []);

  const submit = async () => {
    if (missing.length > 0) {
      setError(`Still needed: ${missing.map((m) => m.label).join(', ')}.`);
      return;
    }

    setError(null);
    setBusy(true);
    try {
      await identityApi.updateProfile({
        name: name.trim(),
        dob,
        bio: bio.trim() || null,
        tags,
        prompts: promptAnswer.trim()
          ? [{ q: PROMPT_QUESTIONS[promptIndex], a: promptAnswer.trim() }]
          : [],
        photos: photos.map((p) => ({ url: p.public_url, object_key: p.object_key })),
      });

      const located = await captureLocation();
      if (!located) {
        setError(
          'Sincère needs your location once to find people near you. We read it only while the app is open, and keep no history.',
        );
        return;
      }
      setStep('liveness');
    } catch (err) {
      setError(
        err instanceof ApiError ? (err.problem.detail ?? err.problem.title) : 'Could not save.',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen scroll>
      <Heading sub="This is what people see. Say something real — the matching reads it too.">
        Build your profile
      </Heading>

      <Field label="YOUR NAME">
        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="Aditi"
          placeholderTextColor={colors.textFaint}
          style={styles.input}
        />
      </Field>

      <Field label="DATE OF BIRTH">
        <TextInput
          value={dob}
          onChangeText={(text) => setDob(formatDob(text))}
          placeholder="1996-04-12"
          placeholderTextColor={colors.textFaint}
          keyboardType="number-pad"
          maxLength={10}
          style={styles.input}
        />
        <Text style={styles.hint}>
          {age === null
            ? 'Type the numbers — we add the dashes. Year, month, day.'
            : age < 18
              ? 'You must be 18 or older to use Sincère.'
              : `You are ${age}. This is shown on your profile.`}
        </Text>
      </Field>

      <Field label="ABOUT YOU (OPTIONAL)">
        <TextInput
          value={bio}
          onChangeText={setBio}
          placeholder="Long walks, short deadlines."
          placeholderTextColor={colors.textFaint}
          multiline
          maxLength={500}
          style={[styles.input, styles.multiline]}
        />
      </Field>

      <Field label="A PROMPT (OPTIONAL)">
        <Text style={styles.question}>{PROMPT_QUESTIONS[promptIndex]}</Text>
        <TextInput
          value={promptAnswer}
          onChangeText={setPromptAnswer}
          placeholder="A bookshop and no plans."
          placeholderTextColor={colors.textFaint}
          multiline
          maxLength={400}
          style={[styles.input, styles.multiline]}
        />
        <Pressable
          onPress={() => setPromptIndex((i) => (i + 1) % PROMPT_QUESTIONS.length)}
          accessibilityRole="button"
        >
          <Text style={styles.link}>Try a different question</Text>
        </Pressable>
      </Field>

      <Field label={`INTERESTS — PICK AT LEAST ${MIN_TAGS}`}>
        <View style={styles.tags}>
          {TAG_OPTIONS.map((tag) => {
            const on = tags.includes(tag);
            return (
              <Pressable
                key={tag}
                onPress={() => toggleTag(tag)}
                accessibilityRole="checkbox"
                accessibilityState={{ checked: on }}
                style={[styles.tag, on && styles.tagOn]}
              >
                <Text style={[styles.tagText, on && styles.tagTextOn]}>{tag}</Text>
              </Pressable>
            );
          })}
        </View>
      </Field>

      <Field label="PHOTOS">
        <View style={styles.photos}>
          {photos.map((photo) => (
            <Pressable
              key={photo.object_key}
              onPress={() => removePhoto(photo.object_key)}
              accessibilityLabel="Remove photo"
            >
              <Image source={{ uri: photo.uri }} style={styles.photo} />
              <View style={styles.removeBadge}>
                <Text style={styles.removeText}>×</Text>
              </View>
            </Pressable>
          ))}
          {photos.length < 6 ? (
            <Pressable
              onPress={() => void addPhoto()}
              style={styles.addPhoto}
              accessibilityLabel="Add a photo"
            >
              <Text style={styles.addPhotoText}>+</Text>
            </Pressable>
          ) : null}
        </View>
        <Body muted>
          Your photos are checked against your verification selfie, so they have to be you.
        </Body>
      </Field>

      <Card style={styles.checklist}>
        <Text style={styles.label}>BEFORE YOU CONTINUE</Text>
        {requirements.map((req) => (
          <View key={req.label} style={styles.requirement}>
            <Text style={[styles.check, req.met && styles.checkMet]}>{req.met ? '✓' : '○'}</Text>
            <Text style={[styles.requirementText, req.met && styles.requirementMet]}>
              {req.label}
            </Text>
          </View>
        ))}
      </Card>

      {error ? <Text style={styles.error}>{error}</Text> : null}

      <View style={styles.action}>
        <Button
          label={
            missing.length > 0
              ? `${missing.length} thing${missing.length === 1 ? '' : 's'} left`
              : 'Continue to verification'
          }
          onPress={() => void submit()}
          loading={busy}
        />
      </View>
    </Screen>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Card style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      {children}
    </Card>
  );
}

const styles = StyleSheet.create({
  field: { marginBottom: spacing.sm, gap: spacing.xs },
  label: { ...typography.label, color: colors.textFaint },
  question: { ...typography.bodyStrong, color: colors.text },
  input: {
    minHeight: 48,
    backgroundColor: colors.surfaceRaised,
    borderRadius: radius.sm,
    color: colors.text,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    ...typography.body,
  },
  multiline: { minHeight: 88, textAlignVertical: 'top' },
  hint: { ...typography.caption, color: colors.textMuted },
  link: { ...typography.caption, color: colors.primary, marginTop: spacing.xs },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  tag: {
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
  },
  tagOn: { backgroundColor: colors.primary, borderColor: colors.primary },
  tagText: { ...typography.caption, color: colors.textMuted },
  tagTextOn: { color: colors.textInverse, fontWeight: '600' },
  photos: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  photo: { width: 76, height: 95, borderRadius: radius.sm },
  removeBadge: {
    position: 'absolute',
    top: -6,
    right: -6,
    width: 22,
    height: 22,
    borderRadius: 11,
    backgroundColor: colors.danger,
    alignItems: 'center',
    justifyContent: 'center',
  },
  removeText: { color: colors.text, fontSize: 15, fontWeight: '700', lineHeight: 18 },
  addPhoto: {
    width: 76,
    height: 95,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  addPhotoText: { ...typography.title, color: colors.textFaint },
  checklist: { marginTop: spacing.sm, gap: spacing.xs },
  requirement: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  check: { ...typography.body, color: colors.textFaint, width: 18 },
  checkMet: { color: colors.success },
  requirementText: { ...typography.caption, color: colors.textMuted, flex: 1 },
  requirementMet: { color: colors.text },
  error: { ...typography.caption, color: colors.danger, marginTop: spacing.sm },
  action: { marginTop: spacing.md, marginBottom: spacing.xl },
});
