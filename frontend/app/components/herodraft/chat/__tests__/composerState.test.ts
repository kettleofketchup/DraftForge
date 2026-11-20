import { describe, expect, it } from 'vitest';
import type { ChatViewer } from '../../types';
import { composerState } from '../composerState';

const member: ChatViewer = {
  role: 'member',
  team_id: 12,
  can_post_team: true,
  can_post_all: true,
};
const spectator: ChatViewer = {
  role: 'spectator',
  team_id: null,
  can_post_team: false,
  can_post_all: false,
};
const ambiguous: ChatViewer = {
  role: 'ambiguous',
  team_id: null,
  can_post_team: false,
  can_post_all: false,
};

const MEMBER_PLACEHOLDER = 'Team chat… (/all for everyone)';

describe('composerState', () => {
  it('shows Connecting… while no viewer has arrived', () => {
    expect(
      composerState({
        viewer: null,
        draftState: 'drafting',
        connected: true,
        raw: 'hi',
      }),
    ).toEqual({
      inputDisabled: false,
      sendDisabled: true,
      placeholder: 'Connecting…',
    });
  });

  it('shows Connecting… while the socket is not connected', () => {
    expect(
      composerState({
        viewer: member,
        draftState: 'drafting',
        connected: false,
        raw: 'hi',
      }),
    ).toEqual({
      inputDisabled: false,
      sendDisabled: true,
      placeholder: 'Connecting…',
    });
  });

  it('makes spectators read-only', () => {
    expect(
      composerState({
        viewer: spectator,
        draftState: 'drafting',
        connected: true,
        raw: 'hi',
      }),
    ).toEqual({
      inputDisabled: true,
      sendDisabled: true,
      placeholder: 'Spectators can read all chat',
    });
  });

  it('blocks users on both rosters', () => {
    expect(
      composerState({
        viewer: ambiguous,
        draftState: 'drafting',
        connected: true,
        raw: 'hi',
      }),
    ).toEqual({
      inputDisabled: true,
      sendDisabled: true,
      placeholder: "You're on both rosters — ask an admin",
    });
  });

  it.each(['completed', 'abandoned'])(
    'is read-only for a %s draft',
    (draftState) => {
      expect(
        composerState({
          viewer: member,
          draftState,
          connected: true,
          raw: 'hi',
        }),
      ).toEqual({
        inputDisabled: true,
        sendDisabled: true,
        placeholder: 'Draft finished — chat is read-only',
      });
    },
  );

  it.each(['', '   ', '/all', '/ALL  ', '\x00'])(
    'disables send for an empty body %j',
    (raw) => {
      expect(
        composerState({
          viewer: member,
          draftState: 'drafting',
          connected: true,
          raw,
        }),
      ).toEqual({
        inputDisabled: false,
        sendDisabled: true,
        placeholder: MEMBER_PLACEHOLDER,
      });
    },
  );

  it.each([
    'waiting_for_captains',
    'rolling',
    'choosing',
    'drafting',
    'paused',
    'resuming',
  ])('enables send for a member in %s', (draftState) => {
    expect(
      composerState({
        viewer: member,
        draftState,
        connected: true,
        raw: 'gl hf',
      }),
    ).toEqual({
      inputDisabled: false,
      sendDisabled: false,
      placeholder: MEMBER_PLACEHOLDER,
    });
  });

  it('enables send for /all with a body', () => {
    expect(
      composerState({
        viewer: member,
        draftState: 'drafting',
        connected: true,
        raw: '/all gg',
      }).sendDisabled,
    ).toBe(false);
  });
});
