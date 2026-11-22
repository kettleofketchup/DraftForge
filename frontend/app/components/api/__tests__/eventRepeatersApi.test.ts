import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import { getEventRepeaters } from '../eventsAPI';

const row = {
  id: 7,
  organization: 1,
  organization_name: 'Org',
  name: 'Weekly Inhouse',
  frequency: 'weekly',
  day_of_week: null,
  time_of_day: '19:00:00',
  timezone: 'America/New_York',
  is_active: true,
  discord_notify_new_events: true,
  subscriber_count: 2,
  is_subscribed: true,
  next_event_date: '2026-11-25T00:00:00Z',
};

beforeEach(() => {
  get.mockReset();
});

describe('getEventRepeaters', () => {
  it('requests the list filtered by organization and parses each row', async () => {
    get.mockResolvedValue({ data: [row] });
    await expect(getEventRepeaters({ organization: 1 })).resolves.toEqual([
      row,
    ]);
    expect(get).toHaveBeenCalledWith('/events/repeaters/', {
      params: { organization: 1 },
    });
  });

  it('rejects a row without the per-user is_subscribed flag', async () => {
    const { is_subscribed: _, ...withoutFlag } = row;
    get.mockResolvedValue({ data: [withoutFlag] });
    await expect(getEventRepeaters()).rejects.toBeInstanceOf(ZodError);
  });
});
