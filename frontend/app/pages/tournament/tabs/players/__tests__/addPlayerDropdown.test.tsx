// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import type { UserType } from '~/components/user/types';
import { useUserCacheStore } from '~/store/userCacheStore';

import { AddPlayerDropdown } from '../addPlayerDropdown';

const users = [
  { pk: 1, username: 'alice' },
  { pk: 2, username: 'bob', discordNickname: 'Bobby Tables' },
  { pk: 3, username: 'carol', nickname: 'Caz' },
] as UserType[];

const renderOpen = (query: string) => {
  render(<AddPlayerDropdown users={users} query={query} setQuery={() => {}} />);
  const input = screen.getByTestId('playerSearchInput');
  fireEvent.focus(input);
  fireEvent.keyDown(input, { key: 'ArrowDown' });
};

beforeEach(() => useUserCacheStore.getState().reset());

describe('AddPlayerDropdown', () => {
  it('matches a user by their Discord name', async () => {
    renderOpen('tables');
    expect(await screen.findByTestId('playerOption-bob')).toBeInTheDocument();
    expect(screen.queryByTestId('playerOption-alice')).toBeNull();
  });

  it('shows the display name with the @handle when they differ', async () => {
    renderOpen('');
    expect(await screen.findByTestId('playerOption-carol')).toHaveTextContent(
      'Caz (@carol)',
    );
    expect(screen.getByTestId('playerOption-alice')).not.toHaveTextContent('@');
  });
});
