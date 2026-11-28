import { AxiosError, AxiosHeaders } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { post } }));

import {
  adminAddSignup,
  approveSignup,
  cancelSignup,
  confirmSignup,
  demoteSignup,
  getSpotTransferRefusal,
  reinstateSignup,
  rejectSignup,
  transferSpot,
  unconfirmSignup,
  voidWithdrawal,
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
  ['void-withdrawal', (id: number) => voidWithdrawal(id)],
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

describe('void withdrawal and restore acknowledgements', () => {
  it('void sends no reason or codes when none are given', async () => {
    await expect(voidWithdrawal(5, {})).resolves.toEqual(signup);
    expect(post).toHaveBeenCalledWith('/events/signups/5/void-withdrawal/', {});
  });

  it('void drops a blank reason and empty codes', async () => {
    await voidWithdrawal(5, { reason: '  ', acknowledged_codes: [] });
    expect(post).toHaveBeenCalledWith('/events/signups/5/void-withdrawal/', {});
  });

  it('void sends the trimmed reason and acknowledged codes', async () => {
    await voidWithdrawal(5, {
      reason: ' r ',
      acknowledged_codes: ['over_capacity'],
    });
    expect(post).toHaveBeenCalledWith('/events/signups/5/void-withdrawal/', {
      reason: 'r',
      acknowledged_codes: ['over_capacity'],
    });
  });

  it('void rejects a malformed response', async () => {
    post.mockResolvedValue({ data: { id: 5 } });
    await expect(voidWithdrawal(5, { reason: 'r' })).rejects.toThrow();
  });

  it('reinstate sends acknowledged codes with the reason', async () => {
    await reinstateSignup(5, 'r', ['over_capacity']);
    expect(post).toHaveBeenCalledWith('/events/signups/5/reinstate/', {
      reason: 'r',
      acknowledged_codes: ['over_capacity'],
    });
  });

  it('reinstate sends codes without a reason', async () => {
    await reinstateSignup(5, undefined, ['over_capacity']);
    expect(post).toHaveBeenCalledWith('/events/signups/5/reinstate/', {
      acknowledged_codes: ['over_capacity'],
    });
  });

  it('reinstate omits empty codes', async () => {
    await reinstateSignup(5, 'r', []);
    expect(post).toHaveBeenCalledWith('/events/signups/5/reinstate/', {
      reason: 'r',
    });
    await reinstateSignup(5);
    expect(post).toHaveBeenLastCalledWith(
      '/events/signups/5/reinstate/',
      undefined,
    );
  });
});

function axiosError(status: number, data: unknown): AxiosError {
  return new AxiosError('fail', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
    statusText: '',
    data,
    headers: {},
    config: { headers: new AxiosHeaders() },
  });
}

describe('spot transfer', () => {
  const recipient = { ...signup, id: 6, user: 3, status: 'approved' };
  const response = {
    mode: 'transfer',
    correlation_id: 'xfer:abc',
    giver: { ...signup, status: 'cancelled' },
    recipient,
  };

  it('posts the recipient, reason and codes and returns the parsed body', async () => {
    post.mockResolvedValue({ data: response });
    await expect(
      transferSpot(5, {
        recipient_user_id: 3,
        reason: ' r ',
        acknowledged_codes: ['not_org_member'],
      }),
    ).resolves.toEqual(response);
    expect(post).toHaveBeenCalledWith('/events/signups/5/transfer/', {
      recipient_user_id: 3,
      reason: 'r',
      acknowledged_codes: ['not_org_member'],
    });
  });

  it('sends only the recipient when no reason or codes are given', async () => {
    post.mockResolvedValue({ data: { ...response, mode: 'swap' } });
    await transferSpot(5, {
      recipient_user_id: 3,
      reason: '  ',
      acknowledged_codes: [],
    });
    expect(post).toHaveBeenCalledWith('/events/signups/5/transfer/', {
      recipient_user_id: 3,
    });
  });

  it('rejects a malformed response', async () => {
    post.mockResolvedValue({ data: { ...response, mode: 'gift' } });
    await expect(transferSpot(5, { recipient_user_id: 3 })).rejects.toThrow();
    post.mockResolvedValue({ data: { ...response, recipient: { id: 6 } } });
    await expect(transferSpot(5, { recipient_user_id: 3 })).rejects.toThrow();
  });

  it('reads an ineligible refusal with member-safe reasons', () => {
    const reasons = [
      { code: 'steam_missing', rule: 'steam', message: 'Steam missing' },
      {
        code: 'recipient_ineligible',
        rule: 'eligibility',
        message: 'Not eligible for this event',
      },
    ];
    expect(
      getSpotTransferRefusal(
        axiosError(400, {
          code: 'recipient_ineligible',
          error: 'They cannot take this place',
          reasons,
        }),
      ),
    ).toEqual({
      code: 'recipient_ineligible',
      error: 'They cannot take this place',
      reasons,
    });
  });

  it('defaults reasons to an empty list', () => {
    expect(
      getSpotTransferRefusal(
        axiosError(400, { code: 'transfer_disabled', error: 'Off' }),
      ),
    ).toEqual({ code: 'transfer_disabled', error: 'Off', reasons: [] });
  });

  it('returns null for anything that is not a transfer refusal', () => {
    expect(getSpotTransferRefusal(new Error('x'))).toBeNull();
    expect(
      getSpotTransferRefusal(axiosError(409, { code: 'x', error: 'y' })),
    ).toBeNull();
    expect(
      getSpotTransferRefusal(axiosError(400, { error: 'reason_required' })),
    ).toBeNull();
    expect(
      getSpotTransferRefusal(
        axiosError(400, { code: 'x', error: 'y', reasons: [{ code: 1 }] }),
      ),
    ).toBeNull();
  });
});
