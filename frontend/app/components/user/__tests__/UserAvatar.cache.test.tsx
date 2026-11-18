// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useDisplayOrgStore } from '~/store/displayOrgStore';
import { useUserCacheStore } from '~/store/userCacheStore';

import { DisplayName } from '../avatar';
import { DisplayOrgProvider } from '../DisplayOrgProvider';
import { UserAvatar } from '../UserAvatar';

const upsert = (raw: Record<string, unknown>, orgId?: number) =>
  useUserCacheStore
    .getState()
    .upsert(raw as never, orgId ? { orgId } : undefined);

const img = () => screen.getByRole('img');

beforeEach(() => {
  useUserCacheStore.getState().reset();
  useDisplayOrgStore.setState({ stack: [], orgId: null });
});

describe('UserAvatar with the user cache', () => {
  it('builds the Discord CDN URL from a cached discordId for a user_id payload', () => {
    upsert({ pk: 3, username: 'u', discordId: '42' });
    render(<UserAvatar user={{ user_id: 3, avatar: 'hash' }} />);
    expect(img()).toHaveAttribute(
      'src',
      'https://cdn.discordapp.com/avatars/42/hash',
    );
    expect(img()).toHaveAttribute('alt', 'u');
  });

  it('updates when the cache entry arrives', () => {
    render(<UserAvatar user={{ user_id: 3, avatar: 'hash' }} />);
    expect(img().getAttribute('src')).toContain('ui-avatars.com');
    act(() =>
      upsert({
        pk: 3,
        username: 'u',
        discordId: '42',
        discordNickname: 'Glob',
      }),
    );
    expect(img()).toHaveAttribute(
      'src',
      'https://cdn.discordapp.com/avatars/42/hash',
    );
    expect(img()).toHaveAttribute('alt', 'Glob');
  });

  it('uses the org server nickname inside a DisplayOrgProvider', () => {
    upsert({ pk: 3, username: 'u', guildNickname: 'Server' }, 7);
    render(
      <DisplayOrgProvider orgId={7}>
        <UserAvatar user={{ pk: 3 }} />
      </DisplayOrgProvider>,
    );
    expect(screen.getByText('S')).toBeInTheDocument();
  });

  it('re-renders when only user_id changes', () => {
    upsert({ pk: 3, username: 'three', discordId: '3' });
    upsert({ pk: 4, username: 'four', discordId: '4' });
    const { rerender } = render(
      <UserAvatar user={{ user_id: 3, avatar: 'h' }} />,
    );
    rerender(<UserAvatar user={{ user_id: 4, avatar: 'h' }} />);
    expect(img()).toHaveAttribute(
      'src',
      'https://cdn.discordapp.com/avatars/4/h',
    );
  });
});

describe('DisplayName', () => {
  it('defaults the org to the DisplayOrgProvider org', () => {
    upsert(
      { pk: 1, username: 'u', discordNickname: 'Glob', guildNickname: 'Srv' },
      7,
    );
    expect(DisplayName({ pk: 1 })).toBe('Glob');
    const token = useDisplayOrgStore.getState().push(7);
    expect(DisplayName({ pk: 1 })).toBe('Srv');
    expect(DisplayName({ pk: 1 }, undefined, null)).toBe('Glob');
    useDisplayOrgStore.getState().pop(token);
  });

  it('keeps the (user, maxLength) signature and ignores the site nickname', () => {
    expect(
      DisplayName({ username: 'abcdef', nickname: 'Site' } as never, 3),
    ).toBe('abc…');
  });

  it('reads a payload guildNickname in an org context', () => {
    const Name = () => (
      <span data-testid="n">
        {DisplayName({ user_id: 9, username: 'u', guildNickname: 'Nick' })}
      </span>
    );
    render(
      <DisplayOrgProvider orgId={2}>
        <Name />
      </DisplayOrgProvider>,
    );
    expect(screen.getByTestId('n')).toHaveTextContent('Nick');
  });
});
