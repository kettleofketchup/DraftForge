import { describe, expect, it } from 'vitest';
import { rollCallSummary, signupRulesFrom } from '../signupRules';

describe('rollCallSummary', () => {
  it('reports an active roll call whatever the flag', () => {
    expect(
      rollCallSummary({ state: 'roll_call', roll_call_enabled: false }),
    ).toBe('In progress');
  });

  it('describes the roster rule during signups', () => {
    expect(
      rollCallSummary({ state: 'signups_open', roll_call_enabled: true }),
    ).toBe('Confirm to join roster');
    expect(
      rollCallSummary({ state: 'signups_open', roll_call_enabled: false }),
    ).toBe('Optional');
  });
});

describe('signupRulesFrom', () => {
  it('copies the self sign-up flag from a loaded entity', () => {
    expect(signupRulesFrom({ allow_user_signups: false })).toEqual({
      allow_user_signups: false,
    });
  });

  it('falls back to the default when the flag is missing', () => {
    expect(signupRulesFrom({})).toEqual({ allow_user_signups: true });
  });
});
