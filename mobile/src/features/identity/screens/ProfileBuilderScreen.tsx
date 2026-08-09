import * as FileSystem from 'expo-file-system/legacy';
import * as ImagePicker from 'expo-image-picker';
import * as Location from 'expo-location';
import { useCallback, useMemo, useState } from 'react';
import { Image, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import * as Haptics from 'expo-haptics';

import { ApiError } from '../../../api/client';
import { Body, Button, Card, GlassInput, GlassSurface, Heading, Pill, Screen } from '../../../components';
import { colors, radius, spacing, typography } from '../../../theme';
import { identityApi } from '../api';
import { useOnboarding } from '../state';

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

  const toggleTag = (tag: string) => {
    setTags((current) =>
      current.includes(tag) ? current.filter((t) => t !== tag) : [...current, tag],
    );
  };

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
          public_url: target.public_url ?? asset.uri,
        },
      ]);
    } catch {
      setError('That photo could not be uploaded. Try another.');
    } finally {
      setBusy(false);
    }
  }, []);

  const removePhoto = (objectKey: string) => {
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setPhotos((current) => current.filter((p) => p.object_key !== objectKey));
  };

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

      <GlassInput
        label="YOUR NAME"
        value={name}
        onChangeText={setName}
        placeholder="Aditi"
      />

      <View style={styles.dobBlock}>
        <View style={styles.dobHeader}>
          <Text style={styles.label}>DATE OF BIRTH</Text>
          {age !== null && age >= 18 && (
            <Pill label={`Age ${age}`} tone="rose" />
          )}
        </View>
        <GlassInput
          value={dob}
          onChangeText={(text) => setDob(formatDob(text))}
          placeholder="1996-04-12"
          keyboardType="number-pad"
          maxLength={10}
        />
        <Text style={styles.hint}>
          {age === null
            ? 'Type the numbers — we add the dashes. Year, month, day.'
            : age < 18
              ? 'You must be 18 or older to use Sincère.'
              : `You are ${age}. This is shown on your profile.`}
        </Text>
      </View>

      <View style={styles.sectionBlock}>
        <Text style={styles.label}>ABOUT YOU (OPTIONAL)</Text>
        <GlassSurface tier="ambient" radius={radius.lg}>
          <View style={styles.multilineInner}>
            <TextInput
              value={bio}
              onChangeText={setBio}
              placeholder="Long walks, short deadlines."
              placeholderTextColor={colors.text.muted}
              multiline
              maxLength={500}
              style={styles.multilineInput}
            />
            <Text style={styles.charCount}>{bio.length}/500</Text>
          </View>
        </GlassSurface>
      </View>

      <View style={styles.sectionBlock}>
        <Text style={styles.label}>A PROMPT (OPTIONAL)</Text>
        <Card tier="raised">
          <Text style={styles.question}>{PROMPT_QUESTIONS[promptIndex]}</Text>
          <GlassSurface tier="ambient" radius={radius.md} style={styles.promptInputGlass}>
            <TextInput
              value={promptAnswer}
              onChangeText={setPromptAnswer}
              placeholder="A bookshop and no plans."
              placeholderTextColor={colors.text.muted}
              multiline
              maxLength={400}
              style={styles.promptInput}
            />
          </GlassSurface>
          <Pressable
            onPress={() => {
              void Haptics.selectionAsync();
              setPromptIndex((i) => (i + 1) % PROMPT_QUESTIONS.length);
            }}
            accessibilityRole="button"
            style={styles.promptChangeLink}
          >
            <Text style={styles.link}>Change prompt question</Text>
          </Pressable>
        </Card>
      </View>

      <View style={styles.sectionBlock}>
        <Text style={styles.label}>INTERESTS — PICK AT LEAST {MIN_TAGS}</Text>
        <View style={styles.tagsGrid}>
          {TAG_OPTIONS.map((tag) => {
            const selected = tags.includes(tag);
            return (
              <Pill
                key={tag}
                label={tag}
                selected={selected}
                onPress={() => toggleTag(tag)}
              />
            );
          })}
        </View>
      </View>

      <View style={styles.sectionBlock}>
        <Text style={styles.label}>PHOTOS</Text>
        <View style={styles.photosGrid}>
          {photos.map((photo) => (
            <GlassSurface
              key={photo.object_key}
              tier="raised"
              radius={radius.md}
              style={styles.photoFrame}
            >
              <Image source={{ uri: photo.uri }} style={styles.photoImage} />
              <Pressable
                onPress={() => removePhoto(photo.object_key)}
                accessibilityLabel="Remove photo"
                style={styles.removeBadge}
              >
                <GlassSurface tier="floating" tint="danger" radius={radius.pill} style={styles.removeBadgeGlass}>
                  <Text style={styles.removeText}>×</Text>
                </GlassSurface>
              </Pressable>
            </GlassSurface>
          ))}
          {photos.length < 6 ? (
            <Pressable onPress={() => void addPhoto()} accessibilityLabel="Add a photo">
              <GlassSurface tier="ambient" radius={radius.md} style={styles.addPhotoTile}>
                <Text style={styles.addPhotoPlus}>+</Text>
              </GlassSurface>
            </Pressable>
          ) : null}
        </View>
        <Body muted style={styles.photoNotice}>
          Your photos are checked against your verification selfie, so they have to be you.
        </Body>
      </View>

      <Card tier="raised" style={styles.checklist}>
        <Text style={styles.label}>BEFORE YOU CONTINUE</Text>
        {requirements.map((req) => (
          <View key={req.label} style={styles.requirementRow}>
            <GlassSurface
              tier="ambient"
              tint={req.met ? 'rose' : 'neutral'}
              radius={radius.pill}
              style={styles.checkBadge}
            >
              <Text style={[styles.checkText, req.met && styles.checkTextMet]}>
                {req.met ? '✓' : '○'}
              </Text>
            </GlassSurface>
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
              ? `${missing.length} requirement${missing.length === 1 ? '' : 's'} remaining`
              : 'Continue to verification'
          }
          onPress={() => void submit()}
          loading={busy}
          disabled={missing.length > 0}
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  dobBlock: { marginBottom: spacing.md },
  dobHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.xs },
  sectionBlock: { marginBottom: spacing.lg },
  label: { ...typography.label, color: colors.text.muted, marginBottom: spacing.xs },

  hint: { ...typography.caption, color: colors.text.muted, marginTop: spacing.xs },

  multilineInner: { padding: spacing.md, minHeight: 90 },
  multilineInput: { flex: 1, ...typography.bodyL, color: colors.text.primary, textAlignVertical: 'top' },
  charCount: { ...typography.caption, color: colors.text.muted, alignSelf: 'flex-end', marginTop: spacing.xs },

  question: { ...typography.displayM, color: colors.warmBeige, marginBottom: spacing.sm },
  promptInputGlass: { marginVertical: spacing.xs },
  promptInput: { padding: spacing.md, minHeight: 70, ...typography.bodyL, color: colors.text.primary, textAlignVertical: 'top' },
  promptChangeLink: { marginTop: spacing.sm },
  link: { ...typography.caption, color: colors.rose[300], textDecorationLine: 'underline' },

  tagsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: spacing.xs },

  photosGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xs },
  photoFrame: { width: 84, height: 105, overflow: 'hidden', position: 'relative' },
  photoImage: { width: '100%', height: '100%' },
  removeBadge: { position: 'absolute', top: 4, right: 4 },
  removeBadgeGlass: { width: 24, height: 24, alignItems: 'center', justifyContent: 'center' },
  removeText: { color: colors.text.onRose, fontSize: 16, fontFamily: 'Manrope_700Bold', lineHeight: 18 },
  addPhotoTile: { width: 84, height: 105, alignItems: 'center', justifyContent: 'center', borderStyle: 'dashed' },
  addPhotoPlus: { fontFamily: 'Fraunces_500Medium', fontSize: 32, color: colors.rose[300] },
  photoNotice: { marginTop: spacing.xs },

  checklist: { marginTop: spacing.sm, gap: spacing.sm },
  requirementRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  checkBadge: { width: 24, height: 24, alignItems: 'center', justifyContent: 'center' },
  checkText: { ...typography.caption, color: colors.text.muted },
  checkTextMet: { color: colors.text.onRose, fontFamily: 'Manrope_700Bold' },
  requirementText: { ...typography.caption, color: colors.text.muted, flex: 1 },
  requirementMet: { color: colors.warmBeige, fontFamily: 'Manrope_600SemiBold' },

  error: { ...typography.caption, color: colors.dangerRed, marginTop: spacing.sm },
  action: { marginTop: spacing.lg, marginBottom: spacing.xxl },
});
