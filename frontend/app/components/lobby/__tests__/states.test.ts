import { describe, expect, it } from 'vitest';
import {
  LOBBY_DOT_BASE,
  lobbyStateDot,
  lobbyStateLabel,
  lobbyStateTone,
  lobbyStateToneName,
  showLobbyDot,
} from '../states';
import { LOBBY_STATES } from '../schemas';

describe('lobby state indicators', () => {
  it('labels every state', () => {
    for (const state of LOBBY_STATES) {
      expect(lobbyStateLabel(state)).not.toBe(state);
    }
  });

  it('tells a live match apart from a lobby that needs attention', () => {
    expect(lobbyStateToneName('in_game')).toBe('live');
    expect(lobbyStateToneName('failed')).toBe('problem');
    expect(lobbyStateToneName('timed_out')).toBe('problem');
    expect(lobbyStateDot('in_game')).not.toBe(lobbyStateDot('failed'));
    expect(lobbyStateTone('in_game')).not.toBe(lobbyStateTone('failed'));
  });

  it('gives each shown tone its own dot colour', () => {
    const shown = ['requested', 'waiting', 'in_game', 'failed'];
    const dots = shown.map(lobbyStateDot);
    expect(new Set(dots).size).toBe(shown.length);
    expect(lobbyStateDot('waiting')).toBe(lobbyStateDot('ready'));
    expect(lobbyStateDot('in_game')).toContain('bg-success');
    expect(lobbyStateDot('waiting')).toContain('bg-warning');
    expect(lobbyStateDot('failed')).toContain('bg-destructive');
  });

  it('rings the dot so it reads on every bracket header', () => {
    expect(LOBBY_DOT_BASE).toMatch(/\bring-1\b/);
    expect(LOBBY_DOT_BASE).toContain('ring-foreground');
  });

  it('hides the dot for lobbies that simply ended', () => {
    expect(showLobbyDot('finished')).toBe(false);
    expect(showLobbyDot('closed')).toBe(false);
    expect(showLobbyDot(null)).toBe(false);
    expect(showLobbyDot('failed')).toBe(true);
    expect(showLobbyDot('in_game')).toBe(true);
  });
});
