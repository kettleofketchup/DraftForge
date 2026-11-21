// @vitest-environment jsdom
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from '~/store/userCacheStore';

import { UserAvatar } from '../UserAvatar';

beforeEach(() => useUserCacheStore.getState().reset());

describe('UserAvatar with a stale Discord avatar hash', () => {
  const user = {
    pk: 3001,
    username: 'clarexlauda',
    discordId: '990297849688391831',
    avatar: 'deadbeefdeadbeefdeadbeefdeadbeef',
  };

  it('loads the Discord CDN url built from discordId and hash', () => {
    render(<UserAvatar user={user} />);
    expect(screen.getByRole('img')).toHaveAttribute(
      'src',
      'https://cdn.discordapp.com/avatars/990297849688391831/deadbeefdeadbeefdeadbeefdeadbeef',
    );
  });

  it('falls back to initials when the image 404s', () => {
    render(<UserAvatar user={user} />);
    expect(screen.getByText('C')).toHaveClass('opacity-0');
    fireEvent.error(screen.getByRole('img'));
    expect(screen.queryByRole('img')).toBeNull();
    expect(screen.getByText('C')).toHaveClass('opacity-100');
  });
});
