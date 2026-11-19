import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get, put, patch } = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
}));

vi.mock('~/components/api/axios', () => ({ default: { get, put, patch } }));

import { getForecast, getMemberConduct, putAttendance } from '../api';

const member = {
  org_user_pk: 7,
  user_pk: 11,
  username: 'alice',
  nickname: null,
  discordNickname: null,
  guildNickname: null,
  avatarUrl: null,
};

const forecastBody = {
  seat_holders: 2,
  expected: 1.7,
  low: 1,
  high: 2,
  waitlisted: 0,
  pending_approval: 1,
  capacity: null,
  expected_open_seats: null,
  new_members: 1,
  members: {
    '11': { show_rate: 0.85, status: 'new', tier: 'ok', deferred: false },
  },
};

const attendanceBody = {
  event_id: 5,
  state: 'roll_call',
  finalized_at: null,
  editable: true,
  editable_reason: null,
  rows: [
    {
      member: { ...member, org_user_pk: null },
      org_user_pk: null,
      signup_status: 'confirmed',
      outcome: 'pending',
      source: 'default',
      committed: true,
      virtual: true,
      finalized: false,
      voided: false,
      flag: 'roll_call_unconfirmed',
      set_by: null,
      reason: '',
      show_rate: 0.85,
      status: 'new',
    },
  ],
};

beforeEach(() => {
  get.mockReset();
  put.mockReset();
  patch.mockReset();
});

describe('conduct api', () => {
  it('parses the forecast', async () => {
    get.mockResolvedValue({ data: forecastBody });
    const result = await getForecast(3, 5);
    expect(get).toHaveBeenCalledWith(
      '/organizations/3/conduct/events/5/forecast/',
    );
    expect(result.members['11'].tier).toBe('ok');
  });

  it('rejects a malformed forecast with a ZodError', async () => {
    get.mockResolvedValue({ data: { ...forecastBody, expected: 'many' } });
    await expect(getForecast(3, 5)).rejects.toBeInstanceOf(ZodError);
  });

  it('pages member history with limit and offset', async () => {
    get.mockResolvedValue({
      data: {
        member,
        show_rate: 0.793,
        status: 'scored',
        counted_events: 4,
        weighted_events: 3.9,
        totals: { attended: 3, no_show: 1, late_cancel: 0, excused: 0 },
        history: [
          {
            event_id: null,
            event_name: 'Old night',
            event_starts_at: '2026-10-01T18:00:00Z',
            outcome: 'no_show',
            source: 'staff',
            committed: true,
            finalized: true,
            voided: false,
            weight: 0.8,
            reason: 'Did not show',
            set_by: { user_pk: 1, username: 'admin' },
          },
        ],
      },
    });
    const result = await getMemberConduct(3, 7, { limit: 50, offset: 50 });
    expect(get).toHaveBeenCalledWith('/organizations/3/conduct/members/7/', {
      params: { limit: 50, offset: 50 },
    });
    expect(result.history[0].event_id).toBeNull();
  });

  it('puts an attendance batch and parses rows with a virtual member', async () => {
    put.mockResolvedValue({ data: attendanceBody });
    const body = {
      changes: [{ user_pk: 11, outcome: 'attended' as const }],
      reason: 'Walked in',
    };
    const result = await putAttendance(3, 5, body);
    expect(put).toHaveBeenCalledWith(
      '/organizations/3/conduct/events/5/attendance/',
      body,
    );
    expect(result.rows[0].member.org_user_pk).toBeNull();
  });
});
