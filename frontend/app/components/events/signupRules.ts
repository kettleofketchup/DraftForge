import {
  EventState,
  ROLL_CALL_MODES,
  SIGNUP_RULES_DEFAULTS,
  type RollCallMode,
} from './schemas';

interface SignupRulesSource {
  roll_call_enabled?: boolean | null;
  allow_user_signups?: boolean | null;
  roll_call_mode?: string | null;
}

export interface SignupRulesValues {
  roll_call_enabled: boolean;
  allow_user_signups: boolean;
  roll_call_mode: RollCallMode | undefined;
}

function isRollCallMode(mode: string | null | undefined): mode is RollCallMode {
  return (ROLL_CALL_MODES as readonly string[]).includes(mode ?? '');
}

/** Form values for SignupRulesSection from a loaded event, series or org defaults. */
export function signupRulesFrom(source: SignupRulesSource): SignupRulesValues {
  return {
    roll_call_enabled:
      source.roll_call_enabled ?? SIGNUP_RULES_DEFAULTS.roll_call_enabled,
    allow_user_signups:
      source.allow_user_signups ?? SIGNUP_RULES_DEFAULTS.allow_user_signups,
    roll_call_mode: isRollCallMode(source.roll_call_mode)
      ? source.roll_call_mode
      : undefined,
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
