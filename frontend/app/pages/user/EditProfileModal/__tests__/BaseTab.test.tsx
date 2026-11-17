// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import BaseTab from '~/pages/user/EditProfileModal/tabs/BaseTab';
import { useUserCacheStore } from '~/store/userCacheStore';
import type { UserProfileEntry } from '~/store/userProfileTypes';
import { useUserStore } from '~/store/userStore';

vi.mock('~/components/api/userProfileApi', () => ({}));

function profile(pk: number): UserProfileEntry {
  return {
    pk,
    base: { avatar: null },
    gameUser: {},
    orgProfiles: {},
    _fetchedAt: 0,
  };
}

function renderTab(pk: number) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <BaseTab profile={profile(pk)} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe('BaseTab (read-only Discord name)', () => {
  beforeEach(() => {
    useUserCacheStore.getState().reset();
    useUserStore.setState({
      currentUser: {
        pk: 5,
        username: 'dc_handle',
        discordNickname: 'GwaihirTheWindlord',
      },
    } as never);
  });

  it('shows the current user global Discord name with no form', () => {
    const { container } = renderTab(5);
    expect(screen.getByText('GwaihirTheWindlord')).toBeTruthy();
    expect(screen.getByText(/Synced from Discord/)).toBeTruthy();
    expect(container.querySelector('input')).toBeNull();
    expect(screen.queryByTestId('edit-user-save')).toBeNull();
  });

  it('reads another user from the user cache', () => {
    useUserCacheStore
      .getState()
      .upsert([
        { pk: 9, username: 'other', discordNickname: 'Other Global' } as never,
      ]);
    renderTab(9);
    expect(screen.getByText('Other Global')).toBeTruthy();
  });

  it('ignores the server nickname (global context)', () => {
    useUserCacheStore
      .getState()
      .upsert([{ pk: 9, username: 'other', discordNickname: null } as never]);
    useUserCacheStore.setState((s) => ({
      entities: {
        ...s.entities,
        9: { ...s.entities[9], orgNicknames: { 7: 'ServerNick' } },
      },
    }));
    renderTab(9);
    expect(screen.getByText('other')).toBeTruthy();
    expect(screen.queryByText('ServerNick')).toBeNull();
  });
});
