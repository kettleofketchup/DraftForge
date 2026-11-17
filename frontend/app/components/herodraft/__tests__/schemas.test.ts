import { describe, expect, it } from 'vitest';
import {
  DraftTeamCaptainSchema,
  DraftTeamSchema,
  HeroDraftSchema,
  HeroDraftWebSocketMessageSchema,
} from '~/components/herodraft/schemas';

const captainStub = {
  pk: 1,
  username: 'kettleofketchup',
  nickname: null,
  avatar: null,
};

const captainStubNullUsername = {
  ...captainStub,
  username: null,
};

describe('DraftTeamCaptainSchema', () => {
  it('accepts a Steam-only user (username: null)', () => {
    expect(() =>
      DraftTeamCaptainSchema.parse(captainStubNullUsername),
    ).not.toThrow();
  });

  it('still accepts a normal user (username: string)', () => {
    expect(() => DraftTeamCaptainSchema.parse(captainStub)).not.toThrow();
  });
});

describe('DraftTeamSchema members[]', () => {
  it('accepts a roster that includes a Steam-only member', () => {
    const team = {
      id: 1,
      tournament_team: 35,
      captain: captainStub,
      team_name: 'Team 1',
      members: [
        captainStub,
        captainStubNullUsername, // the regression case
      ],
      is_first_pick: null,
      is_radiant: null,
      reserve_time_remaining: 90000,
      is_ready: false,
      is_connected: false,
    };
    expect(() => DraftTeamSchema.parse(team)).not.toThrow();
  });
});

describe('HeroDraftWebSocketMessageSchema initial_state', () => {
  it('parses a real shape with a Steam-only member nested under draft_teams', () => {
    // Mirrors the payload tournament 8 / herodraft 2 sends — the
    // exact case that triggered the blank-screen bug.
    const initial = {
      type: 'initial_state' as const,
      draft_state: {
        id: 2,
        game: 99,
        tournament_id: 8,
        state: 'waiting_for_captains' as const,
        roll_winner: null,
        draft_teams: [
          {
            id: 1,
            tournament_team: 35,
            captain: captainStub,
            team_name: 'Team 1',
            members: [captainStub],
            is_first_pick: null,
            is_radiant: null,
            reserve_time_remaining: 90000,
            is_ready: false,
            is_connected: false,
          },
          {
            id: 2,
            tournament_team: 36,
            captain: captainStub,
            team_name: 'Team 2',
            members: [
              captainStub,
              captainStubNullUsername, // the actual production payload shape
            ],
            is_first_pick: null,
            is_radiant: null,
            reserve_time_remaining: 90000,
            is_ready: false,
            is_connected: false,
          },
        ],
        rounds: [],
        current_round: null,
        created_at: '2026-05-19T00:00:00Z',
        updated_at: '2026-05-19T00:00:00Z',
      },
    };
    const parsed = HeroDraftWebSocketMessageSchema.safeParse(initial);
    expect(parsed.success).toBe(true);
  });
});

describe('HeroDraftSchema', () => {
  it('rejects a username of the wrong type (number) — sanity check', () => {
    const team = {
      ...captainStub,
      username: 123 as unknown as string,
    };
    expect(() => DraftTeamCaptainSchema.parse(team)).toThrow();
  });
});

describe('Discord name keys on herodraft captains', () => {
  const team = (captain: Record<string, unknown>) => ({
    id: 1,
    tournament_team: 35,
    captain,
    team_name: 'Team 1',
    members: [captain],
    is_first_pick: null,
    is_radiant: null,
    reserve_time_remaining: 90000,
    is_ready: false,
    is_connected: false,
  });
  const initial = (
    captain: Record<string, unknown>,
    extra: Record<string, unknown> = {},
  ) => ({
    type: 'initial_state' as const,
    draft_state: {
      id: 2,
      game: 99,
      tournament_id: 8,
      state: 'waiting_for_captains' as const,
      roll_winner: null,
      draft_teams: [team(captain)],
      rounds: [],
      current_round: null,
      created_at: '2026-05-19T00:00:00Z',
      updated_at: '2026-05-19T00:00:00Z',
      ...extra,
    },
  });

  it('keeps discordNickname, guildNickname and organization_pk from the current backend shape', () => {
    const captain = {
      pk: 1,
      username: 'dc_handle',
      nickname: null,
      discordNickname: 'GwaihirTheWindlord',
      guildNickname: 'DragonClaw',
      avatar: null,
    };
    const parsed = HeroDraftWebSocketMessageSchema.safeParse(
      initial(captain, { organization_pk: 7 }),
    );
    expect(parsed.success).toBe(true);
    if (!parsed.success || parsed.data.type !== 'initial_state') return;
    const draft = parsed.data.draft_state;
    expect(draft.organization_pk).toBe(7);
    expect(draft.draft_teams[0].captain).toMatchObject({
      discordNickname: 'GwaihirTheWindlord',
      guildNickname: 'DragonClaw',
    });
    expect(draft.draft_teams[0].members[0]).toMatchObject({
      guildNickname: 'DragonClaw',
    });
    expect('nickname' in draft.draft_teams[0].captain!).toBe(false);
  });

  it('accepts a captain without nickname or either Discord name key', () => {
    const parsed = HeroDraftWebSocketMessageSchema.safeParse(
      initial({ pk: 1, username: 'u', avatar: null }),
    );
    expect(parsed.success).toBe(true);
  });

  it('accepts a null organization_pk', () => {
    expect(
      HeroDraftSchema.safeParse({
        ...initial(captainStub).draft_state,
        organization_pk: null,
      }).success,
    ).toBe(true);
  });
});
