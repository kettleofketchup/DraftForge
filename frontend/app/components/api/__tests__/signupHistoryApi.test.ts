import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import {
  SIGNUP_LEDGER_ACTIONS,
  signupHistoryEntrySchema,
  signupHistoryPageSchema,
  signupLedgerActionSchema,
} from '~/components/events/schemas';
import { nextCursor } from '~/hooks/useTournamentList';

import { getEventSignupHistory } from '../eventsAPI';
import page from './fixtures/signup-history-page.json';

beforeEach(() => {
  get.mockReset();
});

describe('signup history schemas', () => {
  it('parses the shared backend fixture', () => {
    const parsed = signupHistoryPageSchema.parse(page);
    expect(parsed.results).toHaveLength(2);
    expect(parsed.results[0].actor.role).toBe('system');
    expect(parsed.results[0].caused_by).toBe(1);
    expect(parsed.results[1].before).toBeNull();
    expect(parsed.results[1].after?.extra).toEqual({ staff_power: true });
    expect(parsed.results[1].subject.discord_id).toBe('100000000000009003');
  });

  it('lists all 22 backend ledger actions', () => {
    expect(SIGNUP_LEDGER_ACTIONS).toHaveLength(22);
    expect(new Set(SIGNUP_LEDGER_ACTIONS).size).toBe(22);
    expect(signupLedgerActionSchema.parse('promoted')).toBe('promoted');
  });

  it('accepts unknown action, means and role strings', () => {
    const entry = {
      ...page.results[0],
      action: 'future_action',
      means: 'carrier_pigeon',
      actor: { ...page.results[0].actor, role: 'robot' },
    };
    const parsed = signupHistoryEntrySchema.parse(entry);
    expect(parsed.action).toBe('future_action');
    expect(parsed.means).toBe('carrier_pigeon');
    expect(parsed.actor.role).toBe('robot');
  });

  it('extracts the cursor from next', () => {
    expect(nextCursor(page.next)).toBe('MjAyNi0xMS0yMFQxODowMjowMCswMDowMHwy');
  });
});

describe('getEventSignupHistory', () => {
  it('omits undefined params and parses the page', async () => {
    get.mockResolvedValue({ data: page });
    const result = await getEventSignupHistory(2, {
      user: undefined,
      action: undefined,
    });
    expect(result.count).toBe(3);
    expect(get).toHaveBeenCalledWith('/events/2/signup-history/', {
      params: {},
    });
    const params = get.mock.calls[0][1].params as Record<string, unknown>;
    expect(Object.keys(params)).toEqual([]);
  });

  it('sends user, action and cursor when given', async () => {
    get.mockResolvedValue({ data: page });
    await getEventSignupHistory(2, {
      user: 9001,
      action: 'withdrew',
      cursor: 'abc',
    });
    expect(get).toHaveBeenCalledWith('/events/2/signup-history/', {
      params: { user: 9001, action: 'withdrew', cursor: 'abc' },
    });
  });

  it('rejects a body without results', async () => {
    const { results: _, ...withoutResults } = page;
    get.mockResolvedValue({ data: withoutResults });
    await expect(getEventSignupHistory(2, {})).rejects.toBeInstanceOf(ZodError);
  });
});
