// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import { useUserCacheStore } from '~/store/userCacheStore';
import { SearchUserDropdown } from '../searchUser';

vi.mock('~/components/api/api');
vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));

const dragon = {
  pk: 1,
  username: 'dc_handle',
  discordNickname: 'GwaihirTheWindlord',
};
const twinA = { pk: 2, username: 'twin_a', discordNickname: 'Twin' };
const twinB = { pk: 3, username: 'twin_b', discordNickname: 'Twin' };
const users = [dragon, twinA, twinB] as never as UserType[];

function Harness({
  onSelect,
  orgId,
}: {
  onSelect: (user: UserType) => void;
  orgId?: number | null;
}) {
  const [query, setQuery] = useState('');
  return (
    <SearchUserDropdown
      users={users}
      query={query}
      setQuery={setQuery}
      onSelect={onSelect}
      orgId={orgId}
    />
  );
}

const search = (q: string) =>
  fireEvent.change(screen.getByTestId('userSearchInput'), {
    target: { value: q },
  });

beforeEach(() => {
  useUserCacheStore.getState().reset();
});

describe('SearchUserDropdown', () => {
  it('selects by pk when the shown name differs from the username', () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    search('gwai');
    fireEvent.mouseDown(screen.getByText('GwaihirTheWindlord'));
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect.mock.calls[0][0].pk).toBe(1);
  });

  it('selects the clicked user when two share a display name', () => {
    const onSelect = vi.fn();
    render(<Harness onSelect={onSelect} />);
    search('twin');
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
    fireEvent.mouseDown(options[1]);
    expect(onSelect.mock.calls[0][0].pk).toBe(3);
  });

  it('matches the org server nickname in an org context', () => {
    act(() =>
      useUserCacheStore
        .getState()
        .upsert({ ...dragon, guildNickname: 'DragonClaw' } as never, {
          orgId: 7,
        }),
    );
    render(<Harness onSelect={vi.fn()} orgId={7} />);
    search('dragon');
    expect(screen.getByText('DragonClaw')).toBeTruthy();
  });

  it('does not show a Nick: label', () => {
    render(<Harness onSelect={vi.fn()} />);
    search('gwai');
    expect(screen.queryByText(/Nick:/)).toBeNull();
  });
});
