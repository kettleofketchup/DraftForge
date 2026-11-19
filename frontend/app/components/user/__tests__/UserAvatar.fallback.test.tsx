// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from '~/store/userCacheStore';

import { UserAvatar } from '../UserAvatar';

beforeEach(() => useUserCacheStore.getState().reset());

describe('UserAvatar fallbackName', () => {
  it('shows the fallback name initial when there is no user', () => {
    render(<UserAvatar user={undefined} fallbackName="radiant five" />);
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByText('R')).toBeTruthy();
  });

  it('prefers the user over the fallback name', () => {
    render(
      <UserAvatar user={{ pk: 1, username: 'cap' }} fallbackName="Team" />,
    );
    expect(screen.getByRole('img')).toHaveAttribute('alt', 'cap');
  });

  it('shows ? with no user and no fallback name', () => {
    render(<UserAvatar user={undefined} />);
    expect(screen.getByText('?')).toBeTruthy();
  });
});
