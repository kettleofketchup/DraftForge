import { AxiosError, AxiosHeaders } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ZodError } from 'zod';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock('~/components/api/axios', () => ({ default: { get } }));

import { signupRecordsResponseSchema } from '~/components/events/signupRecordsSchemas';
import { extractApiError } from '~/lib/apiError';

import {
  downloadSignupRecordsCsv,
  getSignupRecords,
  signupRecordsErrorCode,
} from '../eventsAPI';

const RECORDS = {
  organization: 12,
  count: 2,
  results: [
    {
      event_id: 801,
      event_name: 'Inhouse Friday',
      scheduled_at: '2026-10-02T19:00:00Z',
      event_state: 'deleted',
      series_id: 33,
      user_id: 4512,
      discord_id: '190000000000000001',
      original: {
        signed_up_at: '2026-09-28T10:11:12Z',
        commitment: 'main',
        rsvp_class: 'standard',
        means: 'discord_button',
      },
      final: {
        status: 'cancelled',
        commitment: 'main',
        rsvp_class: 'standard',
        signed_up_at: '2026-09-28T10:11:12Z',
        line_seq: 3,
      },
      withdrawn_at: '2026-10-01T08:00:00Z',
      change_count: 2,
      last_changed_at: '2026-10-01T08:00:00Z',
    },
    {
      event_id: 802,
      event_name: 'Gone Event',
      scheduled_at: null,
      event_state: 'deleted',
      series_id: null,
      user_id: 4513,
      discord_id: null,
      original: null,
      final: null,
      withdrawn_at: null,
      change_count: 1,
      last_changed_at: '2026-10-03T08:00:00Z',
    },
  ],
};

const TOO_MANY = {
  detail: 'Too many records; narrow the date range.',
  code: 'too_many_records',
};

function blobError(body: string, status = 400): AxiosError {
  const headers = new AxiosHeaders();
  return new AxiosError('Request failed', 'ERR_BAD_REQUEST', undefined, null, {
    data: new Blob([body], { type: 'application/json' }),
    status,
    statusText: 'Bad Request',
    headers,
    config: { headers },
  });
}

beforeEach(() => {
  get.mockReset();
});

describe('signupRecordsResponseSchema', () => {
  it('parses the spec fixture including a row with no snapshots', () => {
    const parsed = signupRecordsResponseSchema.parse(RECORDS);
    expect(parsed.count).toBe(2);
    expect(parsed.results[0].original?.means).toBe('discord_button');
    expect(parsed.results[0].final?.line_seq).toBe(3);
    expect(parsed.results[1].original).toBeNull();
    expect(parsed.results[1].final).toBeNull();
    expect(parsed.results[1].discord_id).toBeNull();
  });

  it('rejects a row without event_state', () => {
    const { event_state: _, ...row } = RECORDS.results[0];
    expect(() =>
      signupRecordsResponseSchema.parse({ ...RECORDS, results: [row] }),
    ).toThrow(ZodError);
  });
});

describe('getSignupRecords', () => {
  it('sends only defined filters and parses the body', async () => {
    get.mockResolvedValue({ data: RECORDS });
    const parsed = await getSignupRecords(12, {
      since: '2026-10-01',
      series: 33,
    });
    expect(get).toHaveBeenCalledWith('/organizations/12/signup-records/', {
      params: { since: '2026-10-01', series: 33 },
    });
    expect(parsed.results).toHaveLength(2);
  });

  it('rejects a malformed body', async () => {
    get.mockResolvedValue({ data: { organization: 12, count: 'x' } });
    await expect(getSignupRecords(12, {})).rejects.toBeInstanceOf(ZodError);
  });
});

describe('downloadSignupRecordsCsv', () => {
  it('requests a CSV blob and takes the filename from the header', async () => {
    const blob = new Blob(['event_id\n'], { type: 'text/csv' });
    get.mockResolvedValue({
      data: blob,
      headers: {
        'content-disposition':
          'attachment; filename="signup-records-12-20261127.csv"',
      },
    });
    const result = await downloadSignupRecordsCsv(12, {
      since: '2026-10-01',
      until: '2026-11-01',
    });
    expect(get).toHaveBeenCalledWith('/organizations/12/signup-records/', {
      params: { since: '2026-10-01', until: '2026-11-01', format: 'csv' },
      responseType: 'blob',
    });
    expect(result.blob).toBe(blob);
    expect(result.filename).toBe('signup-records-12-20261127.csv');
  });

  it('prefers an encoded filename* parameter', async () => {
    get.mockResolvedValue({
      data: new Blob(['']),
      headers: {
        'content-disposition':
          'attachment; filename="x.csv"; filename*=UTF-8\'\'records%20one.csv',
      },
    });
    const result = await downloadSignupRecordsCsv(12, {
      since: '2026-10-01',
      until: '2026-11-01',
    });
    expect(result.filename).toBe('records one.csv');
  });

  it('falls back to a default filename', async () => {
    get.mockResolvedValue({ data: new Blob(['']), headers: {} });
    const result = await downloadSignupRecordsCsv(12, {
      since: '2026-10-01',
      until: '2026-11-01',
    });
    expect(result.filename).toBe('signup-records-12.csv');
  });

  it('turns a JSON blob error into a DRF error with its code', async () => {
    get.mockRejectedValue(blobError(JSON.stringify(TOO_MANY)));
    const err = await downloadSignupRecordsCsv(12, {
      since: '2026-01-01',
      until: '2026-11-01',
    }).catch((e: unknown) => e);
    expect(extractApiError(err)).toBe(TOO_MANY.detail);
    expect(signupRecordsErrorCode(err)).toBe('too_many_records');
    expect((err as AxiosError).response?.status).toBe(400);
  });

  it('keeps a non-JSON error body unparsed', async () => {
    get.mockRejectedValue(blobError('<html>oops</html>', 502));
    const err = await downloadSignupRecordsCsv(12, {
      since: '2026-01-01',
      until: '2026-11-01',
    }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(AxiosError);
    expect(extractApiError(err)).toBeUndefined();
    expect(signupRecordsErrorCode(err)).toBeUndefined();
  });

  it('rethrows non-axios errors unchanged', async () => {
    const boom = new Error('boom');
    get.mockRejectedValue(boom);
    await expect(
      downloadSignupRecordsCsv(12, { since: 'a', until: 'b' }),
    ).rejects.toBe(boom);
  });
});
