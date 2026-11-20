import { describe, expect, it } from 'vitest';
import type { DraftTeamUsage } from '~/components/api/types';
import {
  forceResetMessage,
  ineligibleReasonText,
  usageBreakdown,
  usageTeamNames,
} from '../draftResetText';

const games = (count: number): DraftTeamUsage => ({
  model: 'app.Game',
  label: 'game',
  label_plural: 'games',
  count,
  teams: [
    { pk: 1, name: 'Team A' },
    { pk: 2, name: 'Team B' },
  ],
});

const herodraft: DraftTeamUsage = {
  model: 'app.HeroDraft',
  label: 'HeroDraft',
  label_plural: 'HeroDrafts',
  count: 1,
  teams: [{ pk: 2, name: 'Team B' }],
};

const slots: DraftTeamUsage = {
  model: 'bracket.BracketSlot',
  label: 'bracket slot',
  label_plural: 'bracket slots',
  count: 4,
  teams: [{ pk: 3, name: 'Team C' }],
};

describe('usageBreakdown', () => {
  it('uses the singular for one record', () => {
    expect(usageBreakdown([games(1)])).toBe('1 game');
  });

  it('joins kinds with commas and "and"', () => {
    expect(usageBreakdown([games(2), herodraft])).toBe(
      '2 games and 1 HeroDraft',
    );
    expect(usageBreakdown([games(2), herodraft, slots])).toBe(
      '2 games, 1 HeroDraft and 4 bracket slots',
    );
  });
});

describe('usageTeamNames', () => {
  it('lists each affected team once, in order', () => {
    expect(usageTeamNames([games(2), herodraft, slots])).toEqual([
      'Team A',
      'Team B',
      'Team C',
    ]);
  });
});

describe('forceResetMessage', () => {
  it('says what uses which teams', () => {
    expect(
      forceResetMessage({ references: {}, usage: [games(2), herodraft] }),
    ).toBe(
      '2 games and 1 HeroDraft use Team A and Team B. Resetting keeps those records, but these teams go back to just their captains.',
    );
  });

  it('names a single team in the singular', () => {
    expect(forceResetMessage({ references: {}, usage: [herodraft] })).toBe(
      '1 HeroDraft uses Team B. Resetting keeps those records, but this team goes back to just its captain.',
    );
  });

  it('falls back when the server sends no usage', () => {
    expect(
      forceResetMessage({
        references: { 'app.Game.radiant_team': 2 },
        usage: [],
      }),
    ).toBe(
      'Games or other records use these teams. Resetting keeps those records, but these teams go back to just their captains.',
    );
  });
});

describe('ineligibleReasonText', () => {
  it('explains each reason', () => {
    expect(ineligibleReasonText('no_captain')).toBe('No captain');
    expect(ineligibleReasonText('captain_not_in_pool')).toBe(
      'Captain is not in the player pool',
    );
  });
});
