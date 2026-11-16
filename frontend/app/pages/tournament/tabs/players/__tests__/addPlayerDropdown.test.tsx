// @vitest-environment jsdom
import { act, fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { UserType } from '~/components/user/types';
import { useUserCacheStore } from '~/store/userCacheStore';
import { AddPlayerDropdown } from '../addPlayerDropdown';

vi.mock('~/components/api/api');
vi.mock('~/components/user/UserAvatar', () => ({ UserAvatar: () => null }));

const dragon = {
  pk: 1,
  username: 'dc_handle',
  discordNickname: 'GwaihirTheWindlord',
};
const bob = { pk: 2, username: 'bob', discordNickname: 'Bobby' };
const users = [dragon, bob] as never as UserType[];

function Harness({
  addPlayerCallback,
  orgId,
}: {
  addPlayerCallback: (user: UserType) => Promise<void>;
  orgId?: number | null;
}) {
  const [query, setQuery] = useState('');
  return (
    <AddPlayerDropdown
      users={users}
      query={query}
      setQuery={setQuery}
      addPlayerCallback={addPlayerCallback}
      orgId={orgId}
    />
  );
}

const search = (q: string) =>
  fireEvent.change(screen.getByTestId('playerSearchInput'), {
    target: { value: q },
  });

beforeEach(() => {
  useUserCacheStore.getState().reset();
});

describe('AddPlayerDropdown', () => {
  it('matches the org nickname and adds the clicked user by pk', async () => {
    act(() =>
      useUserCacheStore
        .getState()
        .upsert({ ...dragon, guildNickname: 'DragonClaw' } as never, {
          orgId: 7,
        }),
    );
    const add = vi.fn(async () => {});
    render(<Harness addPlayerCallback={add} orgId={7} />);
    search('dragon');
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(1);
    expect(screen.getByText('DragonClaw')).toBeTruthy();
    await act(async () => {
      fireEvent.mouseDown(options[0]);
    });
    expect(add).toHaveBeenCalledTimes(1);
    expect((add.mock.calls[0] as unknown as [UserType])[0].pk).toBe(1);
  });

  it('does not match the org nickname without an org', () => {
    useUserCacheStore
      .getState()
      .upsert({ ...dragon, guildNickname: 'DragonClaw' } as never, {
        orgId: 7,
      });
    render(<Harness addPlayerCallback={vi.fn(async () => {})} />);
    search('dragon');
    expect(screen.queryAllByRole('option')).toHaveLength(0);
  });
});
