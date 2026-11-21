import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get, patch } }));

import {
  getConductSettings,
  getMemberConduct,
  patchConductSettings,
} from '../api';
import { HISTORY_PAGE_SIZE } from '../schemas';
import {
  conductSettings,
  conductSettingsValues,
  memberConduct,
} from './fixtures';

const SETTINGS = conductSettings();
const VALUES = conductSettingsValues();

beforeEach(() => {
  get.mockReset();
  patch.mockReset();
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
});
