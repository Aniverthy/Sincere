import { create } from 'zustand';

/**
 * Onboarding flow state.
 *
 * Separate from the session store because this is transient: it holds the OTP challenge and
 * which onboarding step the user is on, none of which survives sign-in. The session store
 * holds the durable identity.
 */

export type OnboardingStep = 'phone' | 'otp' | 'gender' | 'profile' | 'liveness' | 'verifying';

interface OnboardingState {
  step: OnboardingStep;
  phone: string | null;
  challengeId: string | null;
  /** Dev only — the console SMS provider returns the OTP so the flow is walkable. */
  devOtp: string | null;

  setStep: (step: OnboardingStep) => void;
  setChallenge: (phone: string, challengeId: string, devOtp: string | null) => void;
  reset: () => void;
}

export const useOnboarding = create<OnboardingState>((set) => ({
  step: 'phone',
  phone: null,
  challengeId: null,
  devOtp: null,

  setStep: (step) => set({ step }),
  setChallenge: (phone, challengeId, devOtp) =>
    set({ phone, challengeId, devOtp, step: 'otp' }),
  reset: () => set({ step: 'phone', phone: null, challengeId: null, devOtp: null }),
}));
