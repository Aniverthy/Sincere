import { GenderScreen } from './screens/GenderScreen';
import { LivenessScreen } from './screens/LivenessScreen';
import { OtpScreen } from './screens/OtpScreen';
import { ProfileBuilderScreen } from './screens/ProfileBuilderScreen';
import { SignupScreen } from './screens/SignupScreen';
import { VerifyingScreen } from './screens/VerifyingScreen';
import { useOnboarding } from './state';

/**
 * The onboarding flow (§4 screen map, §5 sequence).
 *
 * A step switch rather than a navigation stack, for the same reason the root navigator is a
 * switch: onboarding is a strictly linear sequence with no back-navigation that would make
 * sense. You cannot un-verify, and going "back" from the liveness capture to the profile
 * builder after the capture has been submitted would misrepresent what the server has already
 * recorded.
 */
export function OnboardingFlow() {
  const step = useOnboarding((s) => s.step);

  switch (step) {
    case 'phone':
      return <SignupScreen onSent={() => useOnboarding.getState().setStep('otp')} />;
    case 'otp':
      return <OtpScreen />;
    case 'gender':
      return <GenderScreen />;
    case 'profile':
      return <ProfileBuilderScreen />;
    case 'liveness':
      return <LivenessScreen />;
    case 'verifying':
      return <VerifyingScreen />;
    default:
      return <SignupScreen onSent={() => useOnboarding.getState().setStep('otp')} />;
  }
}
