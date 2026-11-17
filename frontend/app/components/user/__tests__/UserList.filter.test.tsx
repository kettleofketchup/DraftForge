// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useUserCacheStore } from '~/store/userCacheStore';
import { UserList } from '../UserList';

vi.mock('~/components/user/VirtualizedUserGrid', () => ({
  VirtualizedUserGrid: ({ users }: { users: { pk: number }[] }) => (
    <ul>
      {users.map((u) => (
        <li key={u.pk} data-testid={`row-${u.pk}`} />
      ))}
    </ul>
  ),
}));

const dragon = {
  pk: 1,
  username: 'dc_handle',
  discordNickname: 'GwaihirTheWindlord',
};
const bob = { pk: 2, username: 'bob', discordNickname: 'Bobby' };
const users = [dragon, bob] as never;

const shown = (pk: number) => screen.queryByTestId(`row-${pk}`) !== null;

beforeEach(() => {
  useUserCacheStore.getState().reset();
});

describe('UserList filter', () => {
  it('matches the org server nickname once it arrives, without remounting', () => {
    render(<UserList users={users} searchQuery="dragon" organizationId={7} />);
    expect(shown(1)).toBe(false);

    act(() =>
      useUserCacheStore
        .getState()
        .upsert({ ...dragon, guildNickname: 'DragonClaw' } as never, {
          orgId: 7,
        }),
    );
    expect(shown(1)).toBe(true);
    expect(shown(2)).toBe(false);
  });

  it('matches the global Discord name', () => {
    render(<UserList users={users} searchQuery="gwai" organizationId={7} />);
    expect(shown(1)).toBe(true);
    expect(shown(2)).toBe(false);
  });

  it('ignores org nicknames without an organizationId', () => {
    useUserCacheStore
      .getState()
      .upsert({ ...dragon, guildNickname: 'DragonClaw' } as never, {
        orgId: 7,
      });
    render(<UserList users={users} searchQuery="dragon" />);
    expect(shown(1)).toBe(false);
  });

  it('does not match a stale site nickname', () => {
    const stale = [{ ...dragon, nickname: 'Site' }, bob] as never;
    render(<UserList users={stale} searchQuery="site" />);
    expect(shown(1)).toBe(false);
  });
});
