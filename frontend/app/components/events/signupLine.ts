import { SIGNUP_LINE_DEFAULTS, type SignupLineFields } from './schemas';

/** Form values for SignupLineConfigSection from a loaded event, series or org defaults. */
export function signupLineFrom(
  source: Partial<SignupLineFields> | null | undefined,
): SignupLineFields {
  return {
    line_withdraw_forfeits:
      source?.line_withdraw_forfeits ??
      SIGNUP_LINE_DEFAULTS.line_withdraw_forfeits,
    line_switch_restamps:
      source?.line_switch_restamps ?? SIGNUP_LINE_DEFAULTS.line_switch_restamps,
  };
}
