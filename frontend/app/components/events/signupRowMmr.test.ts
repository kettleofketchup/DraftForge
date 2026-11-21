import { describe, expect, it } from 'vitest';
import type { EventSignupType } from '~/components/events/schemas';
import { GAME_TYPE } from '~/components/game/constants';
import type { UserEntry } from '~/store/userCacheTypes';
import { signupRowMmr } from './signupRowMmr';

const entry: UserEntry = {
  pk: 5,
  username: 'p',
  orgData: { 3: { id: 9, mmrs: { 1: 4000, 2: 2500 }, _fetchedAt: 0 } },
  leagueData: {},
  _fetchedAt: 0,
};

function signup(over: Partial<EventSignupType> = {}): EventSignupType {
  return {
    org_user_mmr: null,
    dota_profile: null,
    ...over,
  } as EventSignupType;
}

const dotaProfile = { mmr: 5555 } as EventSignupType['dota_profile'];

describe('signupRowMmr', () => {
  it('Deadlock event reads the Deadlock cache value, not Dota', () => {
    expect(signupRowMmr(entry, signup(), 3, GAME_TYPE.DEADLOCK)).toBe(2500);
  });

  it('Dota event reads the Dota cache value', () => {
    expect(signupRowMmr(entry, signup(), 3, GAME_TYPE.DOTA2)).toBe(4000);
  });

  it('no cache entry falls back to org_user_mmr', () => {
    expect(
      signupRowMmr(
        undefined,
        signup({ org_user_mmr: 1800 }),
        3,
        GAME_TYPE.DEADLOCK,
      ),
    ).toBe(1800);
  });

  it('Deadlock never falls back to the self-reported Dota MMR', () => {
    expect(
      signupRowMmr(
        undefined,
        signup({ dota_profile: dotaProfile }),
        3,
        GAME_TYPE.DEADLOCK,
      ),
    ).toBeNull();
  });

  it('Dota falls back to the self-reported Dota MMR last', () => {
    expect(
      signupRowMmr(
        undefined,
        signup({ dota_profile: dotaProfile }),
        3,
        GAME_TYPE.DOTA2,
      ),
    ).toBe(5555);
  });
});
