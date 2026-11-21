import { describe, expect, it } from 'vitest';
import {
  DraftTeamCaptainSchema,
  DraftTeamSchema,
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

describe('HeroDraftWebSocketMessageSchema chat frames', () => {
  // Exact sender shape from backend draft/services/hero_chat.py _sender_payload (no `avatar`).
  const sender = {
    pk: 7,
    username: null,
    nickname: 'Khang',
    avatarUrl: null,
    discordId: '123',
  };
  const message = {
    id: '0b8f9a52-3c1e-4f5a-9d2b-6a7c8e9f0a1b',
    channel: 'team' as const,
    team_id: 12,
    kind: 'suggest_ban' as const,
    hero_id: 74,
    body: '',
    created_at: '2026-11-20T18:01:02.123456Z',
    sender,
  };
  const allMessage = {
    ...message,
    id: '1c9fab63-4d2f-4a6b-8e3c-7b8d9fa01b2c',
    channel: 'all' as const,
    team_id: null,
    kind: 'text' as const,
    hero_id: null,
    body: 'gl hf',
  };
  const parse = (frame: unknown) =>
    HeroDraftWebSocketMessageSchema.safeParse(frame);

  it('parses chat_history with nullable team_id and hero_id', () => {
    const result = parse({
      type: 'chat_history',
      viewer: {
        role: 'member',
        team_id: 12,
        can_post_team: true,
        can_post_all: true,
      },
      messages: [message, allMessage],
    });
    expect(result.success).toBe(true);
  });

  it('parses a spectator chat_history', () => {
    const result = parse({
      type: 'chat_history',
      viewer: {
        role: 'spectator',
        team_id: null,
        can_post_team: false,
        can_post_all: false,
      },
      messages: [],
    });
    expect(result.success).toBe(true);
  });

  it('parses chat_message', () => {
    expect(parse({ type: 'chat_message', message: allMessage }).success).toBe(
      true,
    );
  });

  it('parses chat_ack with and without client_msg_id', () => {
    expect(
      parse({ type: 'chat_ack', client_msg_id: 'abc-1', id: message.id })
        .success,
    ).toBe(true);
    expect(parse({ type: 'chat_ack', id: message.id }).success).toBe(true);
  });

  it('parses chat_error with and without client_msg_id', () => {
    expect(
      parse({
        type: 'chat_error',
        code: 'rate_limited',
        client_msg_id: 'abc-1',
      }).success,
    ).toBe(true);
    expect(parse({ type: 'chat_error', code: 'unavailable' }).success).toBe(
      true,
    );
  });

  it('rejects an unknown chat_error code', () => {
    expect(parse({ type: 'chat_error', code: 'nope' }).success).toBe(false);
  });

  it('rejects an unknown kind or channel', () => {
    expect(
      parse({ type: 'chat_message', message: { ...message, kind: 'emote' } })
        .success,
    ).toBe(false);
    expect(
      parse({ type: 'chat_message', message: { ...message, channel: 'dm' } })
        .success,
    ).toBe(false);
  });

  it('rejects a non-uuid message id', () => {
    expect(
      parse({ type: 'chat_message', message: { ...message, id: '42' } })
        .success,
    ).toBe(false);
  });
});
