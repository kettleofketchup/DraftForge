import { describe, expect, it } from 'vitest';
import { describePointValue } from '../pointValues';
import { PointValueRowSchema } from '../schemas';

describe('describePointValue', () => {
  it('labels a kind with no override as Default with no reset', () => {
    expect(
      describePointValue({ kind: 'event_host', points: 10, default: 10, is_default: true }),
    ).toEqual({ label: 'Default', canReset: false });
  });

  it('labels an override as Changed with reset', () => {
    expect(
      describePointValue({ kind: 'event_host', points: 25, default: 10, is_default: false }),
    ).toEqual({ label: 'Changed', canReset: true });
  });

  it('treats an override equal to the default as Changed', () => {
    expect(
      describePointValue({ kind: 'promo_message', points: 1, default: 1, is_default: false }),
    ).toEqual({ label: 'Changed', canReset: true });
  });
});

describe('PointValueRowSchema', () => {
  it('parses the point-values payload and rejects the manual kind', () => {
    expect(
      PointValueRowSchema.parse({ kind: 'event_helper', points: 5, default: 5, is_default: true }),
    ).toEqual({ kind: 'event_helper', points: 5, default: 5, is_default: true });
    expect(
      PointValueRowSchema.safeParse({ kind: 'manual', points: 5, default: 5, is_default: true })
        .success,
    ).toBe(false);
  });
});
