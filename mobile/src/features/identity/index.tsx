/**
 * identity feature — public surface.
 *
 * Mirrors `sincere/identity` (FR-1.1-1.7, §5, §9). The §4 screen map, in the order §5's
 * sequence diagram actually requires:
 *
 *   Signup (phone) → OTP → Gender → Profile builder → Liveness → { verified | review | rejected }
 *
 * §4's diagram draws liveness before the profile builder; FR-1.5 settles the order the other
 * way, because the photo-to-selfie match needs photos to exist when the selfie is taken.
 */

export { OnboardingFlow } from './OnboardingFlow';
export { RejectedScreen } from './screens/RejectedScreen';
export { VerifyingScreen } from './screens/VerifyingScreen';
export { identityApi } from './api';
export { useOnboarding } from './state';
