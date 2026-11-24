import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import { getLeagues } from '../leagueAPI';

const league = {
  pk: 3,
  organization: {
    pk: 1,
    name: 'Org',
    logo: '',
    created_at: '2026-01-01T00:00:00Z',
  },
  organization_name: 'Org',
  steam_league_id: null,
  name: 'Spring League',
  tournament_count: 2,
  users_count: 14,
  admin_ids: [5],
  staff_ids: [],
};

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue({ data: [league] });
});

describe('getLeagues', () => {
  it('passes the organization filter as a query param', async () => {
    await getLeagues(1);
    expect(get).toHaveBeenCalledWith('/leagues/', {
      params: { organization: 1 },
    });
  });

  it('requests every league when no organization is given', async () => {
    await getLeagues();
    expect(get).toHaveBeenCalledWith('/leagues/', { params: undefined });
  });

  it('returns the list body without inventing detail-only fields', async () => {
    const leagues = await getLeagues();
    expect(leagues).toEqual([league]);
    for (const field of ['timezone', 'description', 'rules', 'prize_pool']) {
      expect(leagues[0]).not.toHaveProperty(field);
    }
  });

  it('accepts a league with no organization', async () => {
    const orphan = { ...league, organization: null, organization_name: null };
    get.mockResolvedValue({ data: [orphan] });
    await expect(getLeagues()).resolves.toEqual([orphan]);
  });

  it('rejects a body that does not match the list serializer', async () => {
    get.mockResolvedValue({ data: [{ ...league, tournament_count: '2' }] });
    await expect(getLeagues()).rejects.toBeInstanceOf(ZodError);
  });

  it('rejects a non-array body', async () => {
    get.mockResolvedValue({ data: { results: [league] } });
    await expect(getLeagues()).rejects.toBeInstanceOf(ZodError);
  });
});
