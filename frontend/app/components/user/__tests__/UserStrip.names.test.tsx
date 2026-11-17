// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { TooltipProvider } from '~/components/ui/tooltip';
import { DisplayOrgProvider } from '~/lib/displayOrgContext';
import { useUserCacheStore } from '~/store/userCacheStore';
import { UserStrip } from '../UserStrip';

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

const dragon = {
  pk: 1,
  username: 'dc_handle',
  discordNickname: 'GwaihirTheWindlord',
};

function wrap(node: ReactNode) {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <TooltipProvider>{node}</TooltipProvider>
    </QueryClientProvider>
  );
}

const upsertNick = (orgId: number) =>
  act(() =>
    useUserCacheStore
      .getState()
      .upsert({ ...dragon, guildNickname: 'DragonClaw' } as never, { orgId }),
  );

beforeEach(() => {
  useUserCacheStore.getState().reset();
});

describe('UserStrip names', () => {
  it('shows the global name without org context', () => {
    render(wrap(<UserStrip user={dragon as never} data-testid="strip" />));
    expect(screen.getAllByText('GwaihirTheWindlord').length).toBeGreaterThan(0);
  });

  it('switches to the server nickname when it arrives in the store', () => {
    render(wrap(<UserStrip user={dragon as never} organizationId={7} />));
    expect(screen.getAllByText('GwaihirTheWindlord').length).toBeGreaterThan(0);
    upsertNick(7);
    expect(screen.getAllByText('DragonClaw').length).toBe(2);
    expect(screen.queryByText('GwaihirTheWindlord')).toBeNull();
  });

  it('falls back to the route org when no organizationId is passed', () => {
    upsertNick(7);
    render(
      wrap(
        <DisplayOrgProvider orgId={7}>
          <UserStrip user={dragon as never} />
        </DisplayOrgProvider>,
      ),
    );
    expect(screen.getAllByText('DragonClaw').length).toBe(2);
  });

  it('never shows another org nickname', () => {
    upsertNick(7);
    render(wrap(<UserStrip user={dragon as never} organizationId={8} />));
    expect(screen.queryByText('DragonClaw')).toBeNull();
    expect(screen.getAllByText('GwaihirTheWindlord').length).toBe(1);
    expect(screen.getByText('GwaihirTheWindl…')).toBeTruthy();
  });

  it('truncates at 20 and 15 with the full name in the title', () => {
    const long = { ...dragon, discordNickname: 'AVeryLongDiscordGlobalName' };
    render(wrap(<UserStrip user={long as never} />));
    expect(screen.getByText('AVeryLongDiscordGlob…')).toBeTruthy();
    expect(screen.getByText('AVeryLongDiscor…')).toBeTruthy();
    expect(
      screen.getByTitle('AVeryLongDiscordGlobalName').textContent,
    ).toContain('AVeryLongDiscordGlob…');
  });
});
