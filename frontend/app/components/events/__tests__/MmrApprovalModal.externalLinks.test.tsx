// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { GAME_TYPE, type GameTypeValue } from '~/components/game/constants';
import { useGameTypeStore } from '~/store/gameTypeStore';

import { MmrApprovalModal } from '../MmrApprovalModal';
import type { EventSignupType } from '../schemas';

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

function renderModal(gameType: GameTypeValue) {
  useGameTypeStore.getState().setCurrentGameType(gameType);
  render(
    <MmrApprovalModal
      signup={signup}
      gameType={gameType}
      open
      onOpenChange={vi.fn()}
      onApprove={vi.fn()}
    />,
  );
}

describe('MmrApprovalModal external profile links', () => {
  afterEach(() => {
    cleanup();
    useGameTypeStore.getState().setCurrentGameType(null);
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
