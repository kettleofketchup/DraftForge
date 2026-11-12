import { describe, expect, it } from 'vitest';
import { GameLobbyResponseSchema, GameLobbySchema, InviteResultSchema } from '../schemas';
import { provisionalWinnerSlot } from '../provisional';
import { lobbyErrorText } from '../api';
import { lobbyStateLabel, showLobbyDot } from '../states';
import { publicLobby } from './fixtures';


describe('GameLobbySchema', () => {
  it('parses the public view without private fields', () => {
    const lobby = GameLobbySchema.parse(publicLobby);
    expect(lobby.password).toBeUndefined();
    // Missing lists parse as empty, like null ones.
    expect(lobby.players).toEqual([]);
  });

  it('parses null lists as empty lists', () => {
    const lobby = GameLobbySchema.parse({
      ...publicLobby,
      password: 'abc',
      players: null,
      pending_invites: null,
    });
    expect(lobby.players).toEqual([]);
    expect(lobby.pending_invites).toEqual([]);
  });

  it('keeps unknown states instead of failing', () => {
    expect(GameLobbySchema.parse({ ...publicLobby, state: 'warming_up' }).state).toBe(
      'warming_up',
    );
    expect(lobbyStateLabel('warming_up')).toBe('warming_up');
  });

  it('rejects a lobby without its state', () => {
    const { state: _state, ...rest } = publicLobby;
    expect(GameLobbySchema.safeParse(rest).success).toBe(false);
  });
});

describe('GameLobbyResponseSchema', () => {
  it('parses a staff response with eligibility and null player lists', () => {
    const data = GameLobbyResponseSchema.parse({
      game_id: 1,
      enabled: true,
      mode: 'manual',
      can_manage: true,
      is_player: false,
      lobby: null,
      eligibility: {
        ok: false,
        code: 'missing_steam_ids',
        details: { user_ids: [5], players: null },
      },
      players: null,
    });
    expect(data.players).toEqual([]);
    expect(data.eligibility?.details.players).toEqual([]);
  });

  it('parses an invite result with null lists', () => {
    expect(InviteResultSchema.parse({ invited: null, skipped: null })).toEqual({
      invited: [],
      skipped: [],
    });
  });
});

describe('provisionalWinnerSlot', () => {
  it('maps the reported team onto the bracket slot', () => {
    const lobby = { provisional_winner_team_id: 11, provisional_scored: true };
    expect(provisionalWinnerSlot(lobby, 10, 11)).toBe('dire');
    expect(provisionalWinnerSlot(lobby, 11, 10)).toBe('radiant');
  });

  it('suggests nothing for unscored, unknown or missing results', () => {
    expect(provisionalWinnerSlot(null, 10, 11)).toBeNull();
    expect(
      provisionalWinnerSlot({ provisional_winner_team_id: 11, provisional_scored: false }, 10, 11),
    ).toBeNull();
    expect(
      provisionalWinnerSlot({ provisional_winner_team_id: 99, provisional_scored: true }, 10, 11),
    ).toBeNull();
  });
});

describe('lobby helpers', () => {
  it('describes known error codes and falls back to the server message', () => {
    expect(lobbyErrorText('league_not_held')).toMatch(/league/);
    expect(lobbyErrorText('something_new', 'Server says no')).toBe('Server says no');
    expect(lobbyErrorText(null)).toBe('Unknown error');
  });

  it('hides the bracket dot for lobbies that simply ended', () => {
    expect(showLobbyDot('waiting')).toBe(true);
    expect(showLobbyDot('timed_out')).toBe(true);
    expect(showLobbyDot('closed')).toBe(false);
    expect(showLobbyDot('finished')).toBe(false);
    expect(showLobbyDot(undefined)).toBe(false);
  });
});
