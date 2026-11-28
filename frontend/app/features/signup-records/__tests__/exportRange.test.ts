import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  defaultExportRange,
  exportRangeSchema,
  toExportParams,
} from '../exportRange';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('toExportParams', () => {
  it('makes until exclusive by adding one day', () => {
    expect(toExportParams({ from: '2026-02-27', to: '2026-02-28' })).toEqual({
      since: '2026-02-27',
      until: '2026-03-01',
    });
  });

  it('rolls over months, years and leap days', () => {
    expect(toExportParams({ from: '2026-12-01', to: '2026-12-31' }).until).toBe(
      '2027-01-01',
    );
    expect(toExportParams({ from: '2028-02-01', to: '2028-02-28' }).until).toBe(
      '2028-02-29',
    );
    expect(toExportParams({ from: '2026-04-01', to: '2026-04-30' }).until).toBe(
      '2026-05-01',
    );
  });

  it.each(['America/Chicago', 'Pacific/Auckland', 'UTC', 'Asia/Kolkata'])(
    'ignores the runner timezone (%s) across DST days',
    (tz) => {
      vi.stubEnv('TZ', tz);
      expect(
        toExportParams({ from: '2026-03-01', to: '2026-03-08' }).until,
      ).toBe('2026-03-09');
      expect(
        toExportParams({ from: '2026-10-01', to: '2026-11-01' }).until,
      ).toBe('2026-11-02');
    },
  );
});

describe('exportRangeSchema', () => {
  it('accepts a valid range, including a single day', () => {
    expect(
      exportRangeSchema.safeParse({ from: '2026-01-01', to: '2026-01-01' })
        .success,
    ).toBe(true);
  });

  it('rejects to before from on the to field', () => {
    const result = exportRangeSchema.safeParse({
      from: '2026-02-02',
      to: '2026-02-01',
    });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0]).toMatchObject({
      path: ['to'],
      message: 'To must be on or after From.',
    });
  });

  it('rejects empty and malformed dates', () => {
    expect(exportRangeSchema.safeParse({ from: '', to: '' }).success).toBe(
      false,
    );
    expect(
      exportRangeSchema.safeParse({ from: '2026-02-30', to: '2026-03-01' })
        .success,
    ).toBe(false);
    expect(
      exportRangeSchema.safeParse({ from: '2026/01/01', to: '2026-03-01' })
        .success,
    ).toBe(false);
  });
});

describe('defaultExportRange', () => {
  it('covers the last 90 days ending today in the local calendar', () => {
    expect(defaultExportRange(new Date(2026, 10, 27, 23, 30))).toEqual({
      from: '2026-08-29',
      to: '2026-11-27',
    });
  });

  it('crosses a year boundary', () => {
    expect(defaultExportRange(new Date(2026, 0, 15, 0, 5))).toEqual({
      from: '2025-10-17',
      to: '2026-01-15',
    });
  });
});
