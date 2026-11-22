import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, patch, put } = vi.hoisted(() => ({
  get: vi.fn(),
  patch: vi.fn(),
  put: vi.fn(),
}));

vi.mock('~/components/api/axios', () => ({ default: { get, patch, put } }));

import {
  getAttendance,
  getConductSettings,
  getForecast,
  getMemberConduct,
  patchConductSettings,
  putAttendance,
} from '../api';
import { HISTORY_PAGE_SIZE } from '../schemas';
import {
  attendance,
  conductSettings,
  conductSettingsValues,
  forecast,
  memberConduct,
} from './fixtures';

const SETTINGS = conductSettings();
const VALUES = conductSettingsValues();

beforeEach(() => {
  get.mockReset();
  patch.mockReset();
  put.mockReset();
});

describe('conduct api', () => {
  it('gets a member page', async () => {
    get.mockResolvedValue({ data: memberConduct() });
    const result = await getMemberConduct(1, 7, {
      limit: HISTORY_PAGE_SIZE,
      offset: 0,
    });
    expect(get).toHaveBeenCalledWith('/organizations/1/conduct/members/7/', {
      params: { limit: 50, offset: 0 },
    });
    expect(result.show_rate).toBe(0.91);
  });

  it('rejects a malformed member payload', async () => {
    get.mockResolvedValue({ data: { ...memberConduct(), status: 'ranked' } });
    await expect(
      getMemberConduct(1, 7, { limit: 50, offset: 0 }),
    ).rejects.toThrow();
  });

  it('gets the settings', async () => {
    get.mockResolvedValue({ data: SETTINGS });
    const result = await getConductSettings(1);
    expect(get).toHaveBeenCalledWith('/organizations/1/conduct/settings/');
    expect(result.defaults.min_events).toBe(3);
  });

  it('patches the settings with the body passed through', async () => {
    patch.mockResolvedValue({ data: { ...SETTINGS, block_enabled: true } });
    const result = await patchConductSettings(1, {
      block_enabled: true,
      block_below: 0.25,
    });
    expect(patch).toHaveBeenCalledWith('/organizations/1/conduct/settings/', {
      block_enabled: true,
      block_below: 0.25,
    });
    expect(result.block_enabled).toBe(true);
  });

  it('gets an event attendance', async () => {
    get.mockResolvedValue({ data: attendance() });
    const result = await getAttendance(1, 5);
    expect(get).toHaveBeenCalledWith(
      '/organizations/1/conduct/events/5/attendance/',
    );
    expect(result.rows).toHaveLength(1);
  });

  it('puts attendance changes with the body passed through', async () => {
    put.mockResolvedValue({ data: attendance({ editable: false }) });
    const body = {
      changes: [{ org_user_pk: 7, outcome: 'no_show' as const }],
      reason: 'Did not show',
    };
    const result = await putAttendance(1, 5, body);
    expect(put).toHaveBeenCalledWith(
      '/organizations/1/conduct/events/5/attendance/',
      body,
    );
    expect(result.editable).toBe(false);
  });

  it('gets an event forecast', async () => {
    get.mockResolvedValue({ data: forecast() });
    const result = await getForecast(1, 5);
    expect(get).toHaveBeenCalledWith(
      '/organizations/1/conduct/events/5/forecast/',
    );
    expect(result.seat_holders).toBe(30);
  });

  it('rejects a malformed forecast payload', async () => {
    get.mockResolvedValue({ data: { ...forecast(), low: 'x' } });
    await expect(getForecast(1, 5)).rejects.toThrow();
  });
});
