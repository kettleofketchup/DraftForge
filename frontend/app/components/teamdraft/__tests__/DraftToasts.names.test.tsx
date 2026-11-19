// @vitest-environment jsdom
import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useUserCacheStore } from '~/store/userCacheStore';

import { PlayerPickedToast } from '../DraftToasts';

const goTo = (path: string) => window.history.pushState({}, '', path);

const payload = {
  pick_number: 2,
  captain_id: 3,
  captain_name: 'cap_user',
  captain_avatar_url: null,
  picked_id: 4,
  picked_name: 'pick_user',
  picked_avatar_url: null,
  team_id: 1,
  team_name: 'Team',
};

beforeEach(() => useUserCacheStore.getState().reset());
afterEach(() => goTo('/'));

describe('PlayerPickedToast names', () => {
  it('shows the payload usernames when the cache has nothing better', () => {
    render(<PlayerPickedToast payload={payload} />);
    expect(screen.getByText('cap_user')).toBeInTheDocument();
    expect(screen.getByText('pick_user')).toBeInTheDocument();
  });

  it('resolves cached Discord names and org server nicknames by pk', () => {
    useUserCacheStore
      .getState()
      .upsert(
        { pk: 3, username: 'cap_user', guildNickname: 'CapServer' } as never,
        { orgId: 7 },
      );
    useUserCacheStore.getState().upsert({
      pk: 4,
      username: 'pick_user',
      discordNickname: 'PickGlobal',
    } as never);
    goTo('/organizations/7');
    render(<PlayerPickedToast payload={payload} />);
    expect(screen.getByText('CapServer')).toBeInTheDocument();
    expect(screen.getByText('PickGlobal')).toBeInTheDocument();
  });
});
