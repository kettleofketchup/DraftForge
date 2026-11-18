// @vitest-environment jsdom
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from '~/store/userCacheStore';

import { DisplayName } from '../avatar';
import { UserAvatar } from '../UserAvatar';

const upsert = (raw: Record<string, unknown>, orgId?: number) =>
  useUserCacheStore
    .getState()
    .upsert(raw as never, orgId ? { orgId } : undefined);

const img = () => screen.getByRole('img');
const goTo = (path: string) => window.history.pushState({}, '', path);

afterEach(() => goTo('/'));

beforeEach(() => {
  useUserCacheStore.getState().reset();
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

  it('re-renders when the site nickname changes', () => {
    const { rerender } = render(
      <UserAvatar user={{ pk: 4, username: 'u', nickname: 'Old' }} />,
    );
    expect(img()).toHaveAttribute('alt', 'Old');
    rerender(<UserAvatar user={{ pk: 4, username: 'u', nickname: 'New' }} />);
    expect(img()).toHaveAttribute('alt', 'New');
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

  it('uses the org server nickname on an org page', () => {
    upsert({ pk: 3, username: 'u', guildNickname: 'Server' }, 7);
    goTo('/organizations/7');
    render(<UserAvatar user={{ pk: 3 }} />);
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
  it("defaults the org to the current page's org", () => {
    upsert(
      { pk: 1, username: 'u', discordNickname: 'Glob', guildNickname: 'Srv' },
      7,
    );
    expect(DisplayName({ pk: 1 })).toBe('Glob');
    goTo('/organizations/7');
    expect(DisplayName({ pk: 1 })).toBe('Srv');
    expect(DisplayName({ pk: 1 }, undefined, null)).toBe('Glob');
    goTo('/users');
    expect(DisplayName({ pk: 1 })).toBe('Glob');
  });

  it('keeps the (user, maxLength) signature', () => {
    expect(DisplayName({ username: 'abcdef' }, 3)).toBe('abc…');
    expect(DisplayName({ username: 'u', nickname: 'Sitename' }, 4)).toBe(
      'Site…',
    );
  });

  it('reads a payload guildNickname in an org context', () => {
    const Name = () => (
      <span data-testid="n">
        {DisplayName({ user_id: 9, username: 'u', guildNickname: 'Nick' })}
      </span>
    );
    goTo('/organizations/2');
    render(<Name />);
    expect(screen.getByTestId('n')).toHaveTextContent('Nick');
  });
});
