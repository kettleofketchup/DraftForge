// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { PlayerPopoverTrigger } from '~/components/player/PlayerPopoverTrigger';
import type { UserType } from '~/components/user/types';
import { HIDE_DELAY_MS, SharedPopoverProvider } from '../shared-popover-context';
import { SharedPopoverRenderer } from '../shared-popover-renderer';

const modal = vi.hoisted(() => ({ open: vi.fn() }));

vi.mock('~/components/user/positions', () => ({ RolePositions: () => null }));
vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));
vi.mock('~/components/player/PlayerModal', () => ({
  PlayerModal: ({ open }: { open: boolean }) => {
    if (open) modal.open();
    return null;
  },
}));
vi.mock('~/components/team/TeamModal', () => ({ TeamModal: () => null }));
vi.mock('~/components/team/TeamPopoverContent', () => ({ TeamPopoverContent: () => null }));

const player = { pk: 42, username: 'alice', nickname: 'Alice' } as UserType;

function renderHoverCard() {
  render(
    <SharedPopoverProvider>
      <PlayerPopoverTrigger player={player}>
        <span>Alice</span>
      </PlayerPopoverTrigger>
      <SharedPopoverRenderer />
    </SharedPopoverProvider>,
  );
  const trigger = screen.getByRole('button', { name: 'View profile for Alice' });
  fireEvent.mouseEnter(trigger);
  act(() => vi.advanceTimersByTime(60));
  return trigger;
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe('hover card close grace period', () => {
  it('stays open while the pointer moves from the trigger onto the card', () => {
    const trigger = renderHoverCard();
    expect(screen.getByRole('tooltip')).toBeTruthy();

    fireEvent.mouseLeave(trigger);
    act(() => vi.advanceTimersByTime(HIDE_DELAY_MS - 50));
    fireEvent.mouseEnter(screen.getByRole('tooltip'));
    act(() => vi.advanceTimersByTime(HIDE_DELAY_MS * 2));

    expect(screen.getByRole('tooltip')).toBeTruthy();
    fireEvent.click(screen.getByRole('tooltip'));
    expect(modal.open).toHaveBeenCalled();
  });

  it('closes after the grace period when the pointer leaves for good', () => {
    const trigger = renderHoverCard();

    fireEvent.mouseLeave(trigger);
    act(() => vi.advanceTimersByTime(HIDE_DELAY_MS - 1));
    expect(screen.getByRole('tooltip')).toBeTruthy();
    act(() => vi.advanceTimersByTime(1));
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('closes after the grace period when the pointer leaves the card', () => {
    const trigger = renderHoverCard();
    fireEvent.mouseLeave(trigger);
    fireEvent.mouseEnter(screen.getByRole('tooltip'));

    fireEvent.mouseLeave(screen.getByRole('tooltip'));
    act(() => vi.advanceTimersByTime(HIDE_DELAY_MS));
    expect(screen.queryByRole('tooltip')).toBeNull();
  });

  it('Escape on the trigger still closes immediately', () => {
    const trigger = renderHoverCard();
    fireEvent.keyDown(trigger, { key: 'Escape' });
    expect(screen.queryByRole('tooltip')).toBeNull();
  });
});
