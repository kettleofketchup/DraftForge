import {
  SIGNUP_OPEN_DEFAULTS,
  SIGNUP_OPEN_MODES,
  type SignupOpenMode,
} from './schemas';

interface SignupOpenSource {
  signup_open_mode?: string | null;
  signups_open_hours_before?: number | null;
}

export interface SignupOpenValues {
  signup_open_mode: SignupOpenMode;
  signups_open_hours_before: number;
}

function isSignupOpenMode(
  mode: string | null | undefined,
): mode is SignupOpenMode {
  return (SIGNUP_OPEN_MODES as readonly string[]).includes(mode ?? '');
}

/** Form values for SignupOpenSection from a loaded event, series or org defaults. */
export function signupOpenFrom(source: SignupOpenSource): SignupOpenValues {
  return {
    signup_open_mode: isSignupOpenMode(source.signup_open_mode)
      ? source.signup_open_mode
      : SIGNUP_OPEN_DEFAULTS.signup_open_mode,
    signups_open_hours_before:
      source.signups_open_hours_before ??
      SIGNUP_OPEN_DEFAULTS.signups_open_hours_before,
  };
}
