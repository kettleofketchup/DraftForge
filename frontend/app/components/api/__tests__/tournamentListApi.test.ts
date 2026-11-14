import { AxiosError, type AxiosResponse } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import * as barrel from '~/components/api/api';
import { getTournaments, getTournamentsPage } from '../tournamentAPI';
import { PaginatedTournamentsSchema } from '~/components/tournament/schemas';

function requestedUrl(): string {
  return get.mock.calls[0][0] as string;
}

function requestedParams(): URLSearchParams {
  return new URLSearchParams(requestedUrl().split('?')[1] ?? '');
}

function axiosErrorWithStatus(status: number): AxiosError {
  return new AxiosError('x', 'ERR_BAD_REQUEST', undefined, undefined, {
    status,
  } as AxiosResponse);
}

const emptyPage = { count: 0, next: null, previous: null, results: [] };

beforeEach(() => {
  get.mockReset();
  get.mockResolvedValue({ data: [] });
});

describe('getTournaments', () => {
  it('requests the bare list when no filters are given', async () => {
    await getTournaments();
    expect(requestedUrl()).toBe('/tournaments-list/');
  });

  it('sends bucket, organization and search, and omits an unset league', async () => {
    await getTournaments({ bucket: 'upcoming', organizationId: 30, search: 'ab' });
    const params = requestedParams();
    expect(requestedUrl().startsWith('/tournaments-list/?')).toBe(true);
    expect(params.get('bucket')).toBe('upcoming');
    expect(params.get('organization')).toBe('30');
    expect(params.get('search')).toBe('ab');
    expect(params.has('league')).toBe(false);
  });

  it('skips a NaN organization id', async () => {
    await getTournaments({ organizationId: Number.NaN });
    expect(requestedParams().has('organization')).toBe(false);
  });

  it('sends an organization id of 0', async () => {
    await getTournaments({ organizationId: 0 });
    expect(requestedParams().get('organization')).toBe('0');
  });

  it('sends organizations=mine and open_signups', async () => {
    await getTournaments({ bucket: 'upcoming', mine: true, openSignups: true });
    const params = requestedParams();
    expect(params.get('organizations')).toBe('mine');
    expect(params.get('open_signups')).toBe('1');
    expect(params.has('organization')).toBe(false);
  });

  it('omits organizations and open_signups when false', async () => {
    await getTournaments({ bucket: 'archived', mine: false, openSignups: false });
    const params = requestedParams();
    expect(params.has('organizations')).toBe(false);
    expect(params.has('open_signups')).toBe(false);
  });
});

describe('getTournamentsPage', () => {
  it('requests the given page of a bucket', async () => {
    get.mockResolvedValue({ data: emptyPage });
    await getTournamentsPage({ bucket: 'archived', page: 2 });
    const params = requestedParams();
    expect(requestedUrl().startsWith('/tournaments-list/?')).toBe(true);
    expect(params.get('bucket')).toBe('archived');
    expect(params.get('page')).toBe('2');
    expect(params.has('page_size')).toBe(false);
  });

  it('sends the cursor instead of a page number', async () => {
    get.mockResolvedValue({ data: emptyPage });
    await getTournamentsPage({ bucket: 'archived', cursor: 'abc_-1', pageSize: 5 });
    const params = requestedParams();
    expect(params.get('cursor')).toBe('abc_-1');
    expect(params.has('page')).toBe(false);
    expect(params.get('page_size')).toBe('5');
  });

  it('rejects a 404 on a cursor page', async () => {
    get.mockRejectedValue(axiosErrorWithStatus(404));
    await expect(
      getTournamentsPage({ bucket: 'archived', cursor: 'abc' }),
    ).rejects.toBeInstanceOf(AxiosError);
  });

  it('sends page_size when given', async () => {
    get.mockResolvedValue({ data: emptyPage });
    await getTournamentsPage({ bucket: 'archived', page: 1, pageSize: 50 });
    expect(requestedParams().get('page_size')).toBe('50');
  });

  it('treats a 404 past the first page as the end of the list', async () => {
    get.mockRejectedValue(axiosErrorWithStatus(404));
    await expect(getTournamentsPage({ bucket: 'archived', page: 2 })).resolves.toEqual(emptyPage);
  });

  it('rejects a 404 on the first page', async () => {
    get.mockRejectedValue(axiosErrorWithStatus(404));
    await expect(getTournamentsPage({ bucket: 'archived', page: 1 })).rejects.toBeInstanceOf(AxiosError);
  });

  it('rejects a 500 past the first page', async () => {
    get.mockRejectedValue(axiosErrorWithStatus(500));
    await expect(getTournamentsPage({ bucket: 'archived', page: 2 })).rejects.toBeInstanceOf(AxiosError);
  });

  it('rethrows a 404-shaped object that is not an axios error', async () => {
    const notAxios = { response: { status: 404 } };
    get.mockRejectedValue(notAxios);
    await expect(getTournamentsPage({ bucket: 'archived', page: 2 })).rejects.toBe(notAxios);
  });
});

describe('PaginatedTournamentsSchema', () => {
  it('accepts a page whose league has no organization', () => {
    const parsed = PaginatedTournamentsSchema.parse({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          pk: 900,
          name: 'Cup',
          date_played: '2026-11-20T18:00:00Z',
          state: 'future',
          tournament_type: 'double_elimination',
          league: {
            pk: 30,
            name: 'League',
            organization_name: null,
            organization_id: null,
            organization_logo: null,
          },
        },
      ],
    });
    expect(parsed.results[0].league).toMatchObject({ organization_id: null, organization_logo: null });
  });
});

describe('api barrel', () => {
  it('re-exports getTournamentsPage', () => {
    expect(typeof barrel.getTournamentsPage).toBe('function');
  });
});
