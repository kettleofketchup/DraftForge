import { EventState, SIGNUP_RULES_DEFAULTS } from './schemas';

interface SignupRulesSource {
  allow_user_signups?: boolean | null;
}

export interface SignupRulesValues {
  allow_user_signups: boolean;
}

/** Form values for SignupRulesSection from a loaded event, series or org defaults. */
export function signupRulesFrom(source: SignupRulesSource): SignupRulesValues {
  return {
    allow_user_signups:
      source.allow_user_signups ?? SIGNUP_RULES_DEFAULTS.allow_user_signups,
  };
}

/** Event-page summary of the roster rule for the current phase. */
export function rollCallSummary(event: {
  state: string;
  roll_call_enabled: boolean;
}): string {
  if (event.state === EventState.ROLL_CALL) return 'In progress';
  return event.roll_call_enabled ? 'Confirm to join roster' : 'Optional';
}
