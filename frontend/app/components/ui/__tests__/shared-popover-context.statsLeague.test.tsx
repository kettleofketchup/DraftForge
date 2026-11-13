// @vitest-environment jsdom
import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import { SharedPopoverProvider, useSharedPopover } from '../shared-popover-context';

const player = { pk: 42, username: 'alice', nickname: 'Alice' } as UserType;
const latest: { value: ReturnType<typeof useSharedPopover> | null } = { value: null };

function Probe() {
  latest.value = useSharedPopover();
  return null;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('SharedPopoverProvider hover context', () => {
  it('stores context from the opening trigger and clears it on a context-less open', () => {
    render(
      <SharedPopoverProvider>
        <Probe />
      </SharedPopoverProvider>,
    );
    const el = document.createElement('span');

    act(() => {
      latest.value!.showPlayerPopover(player, el, { statsLeagueId: 7 });
      vi.advanceTimersByTime(100);
    });
    expect(latest.value!.state.isOpen).toBe(true);
    expect(latest.value!.state.context?.statsLeagueId).toBe(7);

    act(() => {
      latest.value!.showPlayerPopover(player, el);
      vi.advanceTimersByTime(100);
    });
    expect(latest.value!.state.isOpen).toBe(true);
    expect(latest.value!.state.context?.statsLeagueId).toBeUndefined();
  });

  it('openPlayerModal keeps statsLeagueId in playerModalState.context', () => {
    render(
      <SharedPopoverProvider>
        <Probe />
      </SharedPopoverProvider>,
    );
    act(() => {
      latest.value!.openPlayerModal(player, { leagueId: 3, statsLeagueId: 7 });
    });
    expect(latest.value!.playerModalState.context).toEqual({
      leagueId: 3,
      statsLeagueId: 7,
    });
  });
});
