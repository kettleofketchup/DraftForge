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
  it('copies both flags from a loaded entity', () => {
    expect(
      signupRulesFrom({
        roll_call_enabled: true,
        allow_user_signups: false,
        roll_call_mode: 'manual',
      }),
    ).toEqual({
      roll_call_enabled: true,
      allow_user_signups: false,
      roll_call_mode: 'manual',
    });
  });

  it('drops a roll-call mode the form does not offer', () => {
    expect(
      signupRulesFrom({
        roll_call_enabled: false,
        allow_user_signups: true,
        roll_call_mode: 'none',
      }).roll_call_mode,
    ).toBeUndefined();
  });

  it('falls back to the defaults for missing flags', () => {
    expect(signupRulesFrom({})).toEqual({
      roll_call_enabled: false,
      allow_user_signups: true,
      roll_call_mode: undefined,
    });
  });
});
