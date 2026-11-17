// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DisplayOrgProvider } from '~/lib/displayOrgContext';
import { useUserCacheStore } from '~/store/userCacheStore';
import { UserPopover } from '../UserPopover';

vi.mock('~/features/leaderboard/queries', () => ({
  useUserLeagueStats: () => ({ data: undefined, isLoading: false }),
}));

vi.mock('~/components/ui/hover-card', () => ({
  HoverCard: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  HoverCardTrigger: ({ children }: { children: ReactNode }) => (
    <div data-testid="trigger">{children}</div>
  ),
  HoverCardContent: ({ children }: { children: ReactNode }) => (
    <div data-testid="content">{children}</div>
  ),
}));

beforeEach(() => {
  useUserCacheStore.getState().reset();
  useUserCacheStore.getState().upsert(
    {
      pk: 1,
      username: 'dc_handle',
      discordNickname: 'GwaihirTheWindlord',
      guildNickname: 'DragonClaw',
    } as never,
    { orgId: 7 },
  );
});

const popover = (
  <UserPopover
    userId={1}
    username="dc_handle"
    discordNickname="GwaihirTheWindlord"
  />
);

describe('UserPopover names', () => {
  it('shows the server nickname inside an org provider', () => {
    render(<DisplayOrgProvider orgId={7}>{popover}</DisplayOrgProvider>);
    expect(screen.getByTestId('trigger').textContent).toBe('DragonClaw');
    expect(screen.getByTestId('content').textContent).toContain('DragonClaw');
  });

  it('shows the global name without org context', () => {
    render(popover);
    expect(screen.getByTestId('trigger').textContent).toBe(
      'GwaihirTheWindlord',
    );
  });
});
