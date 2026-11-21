// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import type { EventSignupType } from '~/components/events/schemas';
import { GAME_TYPE, type GameTypeValue } from '~/components/game/constants';
import { TooltipProvider } from '~/components/ui/tooltip';
import { MmrApprovalModal } from './MmrApprovalModal';

vi.mock('~/components/ui/shared-popover-context', () => ({
  useSharedPopoverActions: () => ({
    showPlayerPopover: vi.fn(),
    hidePopover: vi.fn(),
    openPlayerModal: vi.fn(),
    openTeamModal: vi.fn(),
  }),
}));

vi.mock('~/features/league-stats/queries', () => ({
  usePlayerLeagueSummary: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
  }),
}));

function signup(over: Partial<EventSignupType> = {}): EventSignupType {
  return {
    id: 7,
    user: 5,
    username: 'player',
    user_avatar: null,
    user_data: null,
    dota_profile: null,
    org_user_mmr: null,
    suggested_mmr: 3200,
    suggested_mmr_range: [3000, 3500],
    suggested_mmr_range_source: 'medal',
    self_reported_rank: null,
    self_reported_rank_date: null,
    ...over,
  } as EventSignupType;
}

function wrap(node: ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>
  );
}

function renderModal(gameType: GameTypeValue, s: EventSignupType) {
  const onApprove = vi.fn();
  render(
    wrap(
      <MmrApprovalModal
        signup={s}
        open
        onOpenChange={() => {}}
        onApprove={onApprove}
        gameType={gameType}
      />,
    ),
  );
  return onApprove;
}

function input(): HTMLInputElement {
  return screen.getByTestId('mmr-input') as HTMLInputElement;
}

async function setInput(value: string) {
  await act(async () => {
    fireEvent.change(input(), { target: { value } });
  });
}

async function submit() {
  await act(async () => {
    fireEvent.click(screen.getByTestId('mmr-modal-approve'));
  });
}

async function confirm() {
  await act(async () => {
    fireEvent.click(await screen.findByTestId('mmr-confirm-approve'));
  });
}

describe('MmrApprovalModal gameType', () => {
  it('titles the input with the game org MMR', () => {
    renderModal(GAME_TYPE.DEADLOCK, signup());
    expect(screen.getByText('Set Deadlock org MMR')).toBeTruthy();
  });

  it('shows the Dota suggested-range hint only for Dota', () => {
    renderModal(GAME_TYPE.DOTA2, signup());
    expect(screen.getByTestId('suggested-range-helper')).toBeTruthy();
  });

  it('hides the suggested-range hint for Deadlock', () => {
    renderModal(GAME_TYPE.DEADLOCK, signup());
    expect(screen.queryByTestId('suggested-range-helper')).toBeNull();
  });

  it('Deadlock null suggestion starts empty and blocks approve', async () => {
    const onApprove = renderModal(
      GAME_TYPE.DEADLOCK,
      signup({ suggested_mmr: null, suggested_mmr_range: null }),
    );
    expect(input().value).toBe('');
    await submit();
    expect(screen.queryByTestId('mmr-confirm-approve')).toBeNull();
    expect(onApprove).not.toHaveBeenCalled();
  });

  it('Deadlock 0 is blocked', async () => {
    const onApprove = renderModal(GAME_TYPE.DEADLOCK, signup());
    await setInput('0');
    await submit();
    expect(screen.queryByTestId('mmr-confirm-approve')).toBeNull();
    expect(onApprove).not.toHaveBeenCalled();
  });

  it('Deadlock positive value approves with that value', async () => {
    const onApprove = renderModal(
      GAME_TYPE.DEADLOCK,
      signup({ suggested_mmr: null }),
    );
    await setInput('2500');
    await submit();
    await confirm();
    expect(onApprove).toHaveBeenCalledWith(7, 2500);
  });

  it('Dota 0 is allowed and submits 0', async () => {
    const onApprove = renderModal(GAME_TYPE.DOTA2, signup());
    await setInput('0');
    await submit();
    await confirm();
    expect(onApprove).toHaveBeenCalledWith(7, 0);
  });

  it('Dota empty input blocks approve (no || 0 fallback)', async () => {
    const onApprove = renderModal(GAME_TYPE.DOTA2, signup());
    await setInput('');
    await submit();
    expect(screen.queryByTestId('mmr-confirm-approve')).toBeNull();
    expect(onApprove).not.toHaveBeenCalled();
  });
});
