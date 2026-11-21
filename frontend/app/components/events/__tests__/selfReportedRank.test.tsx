// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { MmrApprovalModal } from '~/components/events/MmrApprovalModal';
import { RankSignalsCard } from '~/components/events/games/RankSignalsCard';
import type { EventSignupType } from '~/components/events/schemas';
import { GAME_TYPE } from '~/components/game/constants';
import { SharedPopoverProvider } from '~/components/ui/shared-popover-context';
import { TooltipProvider } from '~/components/ui/tooltip';
import { UserEventStrip } from '~/components/user/UserEventStrip';
import type { UserType } from '~/components/user/types';
import { useGameTypeStore } from '~/store/gameTypeStore';

function signup(over: Partial<EventSignupType> = {}): EventSignupType {
  return {
    id: 1,
    user: 7,
    username: 'player',
    user_avatar: null,
    user_data: null,
    org_user_mmr: 2400,
    dota_profile: null,
    suggested_mmr: 2400,
    suggested_mmr_range: [2000, 3000],
    suggested_mmr_range_source: 'fallback',
    self_reported_rank: null,
    self_reported_rank_date: null,
    ...over,
  } as EventSignupType;
}

const noop = () => {};

beforeEach(() => {
  useGameTypeStore.getState().setCurrentGameType(GAME_TYPE.DEADLOCK);
});

afterEach(() => {
  cleanup();
  useGameTypeStore.getState().setCurrentGameType(null);
});

describe('Deadlock rank signals', () => {
  it('shows the self-reported Deadlock rank and its date', () => {
    render(
      <RankSignalsCard
        gameType={GAME_TYPE.DEADLOCK}
        signup={signup({
          self_reported_rank: 'Emissary 1',
          self_reported_rank_date: '2026-10-02',
        })}
      />,
    );
    const row = screen.getByTestId('rank-signals-deadlock-rank');
    expect(row.textContent).toContain('Self-Reported Rank');
    expect(row.textContent).toContain('Emissary 1');
    expect(row.textContent).toContain('2026-10-02');
    expect(screen.queryByTestId('rank-signals-medal')).toBeNull();
  });

  it('shows a dash when the player has no Deadlock rank', () => {
    render(<RankSignalsCard gameType={GAME_TYPE.DEADLOCK} signup={signup()} />);
    expect(
      screen.getByTestId('rank-signals-deadlock-rank').textContent,
    ).toContain('—');
  });
});

describe('MmrApprovalModal on a Deadlock event', () => {
  it('does not describe the player by their Dota profile', () => {
    render(
      <MmrApprovalModal
        signup={signup({ self_reported_rank: 'Emissary 1' })}
        gameType={GAME_TYPE.DEADLOCK}
        open
        onOpenChange={noop}
        onApprove={noop}
      />,
    );
    expect(screen.queryByText('No Dota profile')).toBeNull();
    expect(
      screen.getByTestId('rank-signals-deadlock-rank').textContent,
    ).toContain('Emissary 1');
  });
});

describe('UserEventStrip self-reported rank', () => {
  const user = { pk: 7, username: 'player' } as UserType;

  it('shows the self-reported rank badge', () => {
    render(
      <TooltipProvider>
        <SharedPopoverProvider>
          <UserEventStrip
            user={user}
            gameType={GAME_TYPE.DEADLOCK}
            selfReportedRank="Emissary 1"
          />
        </SharedPopoverProvider>
      </TooltipProvider>,
    );
    expect(
      screen.getByTestId('event-strip-self-reported-rank').textContent,
    ).toBe('Emissary 1');
  });

  it('shows no rank badge without a self-reported rank', () => {
    render(
      <TooltipProvider>
        <SharedPopoverProvider>
          <UserEventStrip
            user={user}
            gameType={GAME_TYPE.DEADLOCK}
            selfReportedRank={null}
          />
        </SharedPopoverProvider>
      </TooltipProvider>,
    );
    expect(screen.queryByTestId('event-strip-self-reported-rank')).toBeNull();
  });
});
