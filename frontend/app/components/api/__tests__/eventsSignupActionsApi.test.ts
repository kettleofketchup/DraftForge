import { beforeEach, describe, expect, it, vi } from 'vitest';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { post } }));

import {
  adminAddSignup,
  approveSignup,
  cancelSignup,
  confirmSignup,
  demoteSignup,
  reinstateSignup,
  rejectSignup,
  unconfirmSignup,
} from '../eventsAPI';

const signup = {
  id: 5,
  event: 1,
  user: 2,
  username: 'player',
  user_avatar: null,
  user_data: null,
  dota_profile: null,
  org_user_mmr: null,
  org_user_pk: null,
  organization: null,
  suggested_mmr: null,
  suggested_mmr_range: null,
  suggested_mmr_range_source: 'none',
  event_team: null,
  signup_type: 'individual',
  status: 'approved',
  waitlist_position: null,
  created_at: '2026-11-25T00:00:00Z',
  updated_at: '2026-11-25T00:00:00Z',
  signed_up_at: null,
  commitment: 'main',
  rsvp_class: 'standard',
  first_signed_up_at: null,
  line_rank: null,
};

beforeEach(() => {
  post.mockReset();
  post.mockResolvedValue({ data: signup });
});

const SINGLE_REASON = [
  ['reject', rejectSignup],
  ['confirm', confirmSignup],
  ['unconfirm', unconfirmSignup],
  ['cancel_signup', cancelSignup],
  ['demote', demoteSignup],
  ['reinstate', reinstateSignup],
] as const;

const steamOnlySignup = {
  ...signup,
  username: 'Steam Player',
  user_data: {
    pk: 2,
    username: null,
    nickname: 'Steam Player',
    avatar: null,
    discordId: null,
    discordNickname: null,
    positions: null,
    steam_account_id: 123456789,
    steam_account_verified: false,
    steam_account_verified_at: null,
    steam_account_exists_checked: true,
    steam_account_verified_org_name: null,
    avatarUrl: null,
  },
};

const SIGNUP_ACTIONS = [
  ...SINGLE_REASON,
  ['approve', (id: number) => approveSignup(id)],
  ['admin add', () => adminAddSignup(1, 2)],
] as const;

describe('signup action reasons', () => {
  it.each(SIGNUP_ACTIONS)(
    '%s accepts a Steam-only user without a site username',
    async (_path, fn) => {
      post.mockResolvedValue({ data: steamOnlySignup });
      await expect(fn(5)).resolves.toEqual(steamOnlySignup);
    },
  );

  it.each(SIGNUP_ACTIONS)(
    '%s rejects an invalid nested username',
    async (_path, fn) => {
      post.mockResolvedValue({
        data: {
          ...steamOnlySignup,
          user_data: { ...steamOnlySignup.user_data, username: 123 },
        },
      });
      await expect(fn(5)).rejects.toThrow();
    },
  );
  it.each(SINGLE_REASON)(
    '%s rejects a malformed response',
    async (_path, fn) => {
      post.mockResolvedValue({ data: { id: 5 } });
      await expect(fn(5, 'reason')).rejects.toThrow();
    },
  );

  it('approve rejects a malformed response', async () => {
    post.mockResolvedValue({ data: { id: 5 } });
    await expect(approveSignup(5, { reason: 'reason' })).rejects.toThrow();
  });

  it('admin add rejects a malformed response', async () => {
    post.mockResolvedValue({ data: { id: 5 } });
    await expect(adminAddSignup(1, 2, 'reason')).rejects.toThrow();
  });

  it.each(SINGLE_REASON)(
    '%s sends no body without a reason',
    async (path, fn) => {
      await fn(5);
      expect(post).toHaveBeenCalledWith(
        `/events/signups/5/${path}/`,
        undefined,
      );
    },
  );

  it.each(SINGLE_REASON)(
    '%s sends no reason when it is only whitespace',
    async (path, fn) => {
      await fn(5, '   ');
      expect(post).toHaveBeenCalledWith(
        `/events/signups/5/${path}/`,
        undefined,
      );
    },
  );

  it.each(SINGLE_REASON)('%s sends the trimmed reason', async (path, fn) => {
    await expect(fn(5, ' x ')).resolves.toEqual(signup);
    expect(post).toHaveBeenCalledWith(`/events/signups/5/${path}/`, {
      reason: 'x',
    });
  });

  it('approve sends MMR and reason together', async () => {
    await approveSignup(5, { mmr: 4200, reason: 'r' });
    expect(post).toHaveBeenCalledWith('/events/signups/5/approve/', {
      mmr: 4200,
      reason: 'r',
    });
  });

  it('approve sends MMR alone, or nothing', async () => {
    await approveSignup(5, { mmr: 4200, reason: '  ' });
    expect(post).toHaveBeenLastCalledWith('/events/signups/5/approve/', {
      mmr: 4200,
    });
    await approveSignup(5);
    expect(post).toHaveBeenLastCalledWith(
      '/events/signups/5/approve/',
      undefined,
    );
  });

  it('admin add sends the user and reason', async () => {
    await adminAddSignup(1, 2, 'r');
    expect(post).toHaveBeenLastCalledWith('/events/1/admin-signup/', {
      user_id: 2,
      reason: 'r',
    });
    await adminAddSignup(1, 2, ' ');
    expect(post).toHaveBeenLastCalledWith('/events/1/admin-signup/', {
      user_id: 2,
    });
  });
});
