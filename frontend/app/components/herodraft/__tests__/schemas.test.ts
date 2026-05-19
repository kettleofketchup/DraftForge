import { describe, it, expect } from 'vitest';
import {
  DraftTeamCaptainSchema,
  DraftTeamSchema,
  HeroDraftSchema,
  HeroDraftWebSocketMessageSchema,
} from '~/components/herodraft/schemas';

// CustomUser.username is declared null=True at the model level so that
// Steam-only signups (no Discord OAuth, no chosen handle) can still exist
// as DB rows. When such a user is added to a tournament team, the team
// gets included verbatim in the HeroDraft initial_state WS payload via
// DraftTeamSerializerFull. Before this PR, the frontend Zod schemas had
// ``username: z.string()`` — a single Steam-only player on any team in
// any draft was enough to fail safeParse on the entire ``initial_state``
// message, causing heroDraftStore to early-return without setting
// ``draft``. The page then rendered blank.
//
// These tests lock the schema contract to match the model.

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
