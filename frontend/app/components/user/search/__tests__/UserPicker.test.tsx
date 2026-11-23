// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { filterUsers } from '~/lib/userSearch';
import { useUserCacheStore } from '~/store/userCacheStore';

import { UserPicker } from '../UserPicker';

const users = [
  { pk: 1, username: 'alice' },
  { pk: 2, username: 'bob', discordNickname: 'Bobby Tables' },
  { pk: 3, username: 'carol', nickname: 'Caz' },
];

const testIds = {
  input: 'picker-input',
  option: (u: { pk: number }) => `picker-option-${u.pk}`,
  hint: 'picker-hint',
  searching: 'picker-searching',
  empty: 'picker-empty',
  error: 'picker-error',
};

function renderPicker(
  props: Partial<Parameters<typeof UserPicker<(typeof users)[number]>>[0]>,
) {
  const onSelect = vi.fn();
  render(
    <UserPicker
      query=""
      onQueryChange={() => {}}
      results={users}
      onSelect={onSelect}
      testIds={testIds}
      {...props}
    />,
  );
  return { onSelect };
}

beforeEach(() => useUserCacheStore.getState().reset());

describe('UserPicker', () => {
  it('shows the display name with the @handle only when they differ', () => {
    renderPicker({});
    expect(screen.getByTestId('picker-option-2')).toHaveTextContent(
      'Bobby Tables@bob',
    );
    expect(screen.getByTestId('picker-option-1')).not.toHaveTextContent('@');
  });

  it('selects a user and skips disabled ones', () => {
    const { onSelect } = renderPicker({ isDisabled: (u) => u.pk === 3 });
    fireEvent.click(screen.getByTestId('picker-option-1'));
    expect(onSelect).toHaveBeenCalledWith(users[0]);
    expect(screen.getByTestId('picker-option-3')).toHaveAttribute(
      'data-disabled',
      'true',
    );
  });

  it('renders remote search states', () => {
    const { unmount } = render(
      <UserPicker
        query="ab"
        onQueryChange={() => {}}
        results={[]}
        status="too-short"
        onSelect={() => {}}
        testIds={testIds}
      />,
    );
    expect(screen.getByTestId('picker-hint')).toHaveTextContent(
      'at least 3 characters',
    );
    unmount();
    renderPicker({ results: [], status: 'error', errorMessage: 'Nope' });
    expect(screen.getByTestId('picker-error')).toHaveTextContent('Nope');
  });

  it('caps the rows and says how many matched', () => {
    renderPicker({ limit: 2 });
    expect(screen.queryByTestId('picker-option-3')).toBeNull();
    expect(screen.getByText(/Showing 2 of 3/)).toBeInTheDocument();
  });

  it('works with filterUsers for a client-side list', () => {
    renderPicker({ results: filterUsers(users, 'tables') });
    expect(screen.getByTestId('picker-option-2')).toBeInTheDocument();
    expect(screen.queryByTestId('picker-option-1')).toBeNull();
  });

  it('shows the empty message', () => {
    renderPicker({ results: [], emptyMessage: 'Nobody' });
    expect(screen.getByTestId('picker-empty')).toHaveTextContent('Nobody');
  });
});
