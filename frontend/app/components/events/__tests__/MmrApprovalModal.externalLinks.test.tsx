// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GAME_TYPE, type GameTypeValue } from '~/components/game/constants';

import { resetGameType, withGameType } from '~/test-utils/gameType';
import { MmrApprovalModal } from '../MmrApprovalModal';
import type { EventSignupType } from '../schemas';

const mutate = vi.hoisted(() => vi.fn());
vi.mock('~/features/steam-verification', () => ({
  useSetSteamVerification: () => ({ mutate, isPending: false }),
}));

const signup = {
  id: 11,
  user: 5,
  username: 'player-five',
  status: 'pending',
  suggested_mmr: 3000,
  suggested_mmr_range: [2800, 3200],
  suggested_mmr_range_source: 'self_report',
  org_user_mmr: null,
  dota_profile: null,
  user_data: { pk: 5, username: 'player-five', steam_account_id: 123456 },
} as unknown as EventSignupType;

function renderModal(gameType: GameTypeValue, row: EventSignupType = signup) {
  withGameType(gameType);
  render(
    <MmrApprovalModal
      signup={row}
      open
      onOpenChange={vi.fn()}
      onApprove={vi.fn()}
    />,
  );
}

describe('MmrApprovalModal external profile links', () => {
  afterEach(() => {
    cleanup();
    resetGameType();
  });

  it('shows the Dotabuff link on a Dota 2 event', () => {
    renderModal(GAME_TYPE.DOTA2);
    expect(screen.getByTitle('View Dotabuff profile')).toBeTruthy();
  });

  it('hides the Dotabuff link on a Deadlock event', () => {
    renderModal(GAME_TYPE.DEADLOCK);
    expect(screen.getByText('player-five')).toBeTruthy();
    expect(screen.queryByTitle('View Dotabuff profile')).toBeNull();
    expect(screen.queryByText('Dotabuff')).toBeNull();
  });
});

describe('MmrApprovalModal Friend ID verification', () => {
  afterEach(() => {
    cleanup();
    resetGameType();
    mutate.mockReset();
  });

  const verifiable = {
    ...signup,
    can_verify_steam_account: true,
    user_data: {
      ...signup.user_data,
      steam_account_verified: false,
      steam_account_exists_checked: true,
    },
  } as unknown as EventSignupType;

  it.each([GAME_TYPE.DOTA2, GAME_TYPE.DEADLOCK])(
    'shows the Unverified badge next to the Friend ID (game %s)',
    (gameType) => {
      renderModal(gameType);
      expect(screen.getByTestId('mmr-modal-friend-id').textContent).toContain(
        'Friend ID 123456',
      );
      expect(screen.getByTestId('steam-verification-unverified')).toBeTruthy();
    },
  );

  it('hides Verify when the row says the viewer cannot verify', () => {
    renderModal(GAME_TYPE.DOTA2);
    expect(screen.queryByTestId('steam-verify-button')).toBeNull();
  });

  it('Verify posts the displayed Friend ID when the row allows it', () => {
    renderModal(GAME_TYPE.DOTA2, verifiable);
    fireEvent.click(screen.getByTestId('steam-verify-button'));
    expect(mutate).toHaveBeenCalledWith({
      verified: true,
      steamAccountId: 123456,
    });
  });

  it('keeps a single Dotabuff link on Dota and none on Deadlock', () => {
    renderModal(GAME_TYPE.DOTA2, verifiable);
    expect(screen.getAllByTitle('View Dotabuff profile')).toHaveLength(1);
    cleanup();
    renderModal(GAME_TYPE.DEADLOCK, verifiable);
    expect(screen.queryByTitle('View Dotabuff profile')).toBeNull();
  });
});
