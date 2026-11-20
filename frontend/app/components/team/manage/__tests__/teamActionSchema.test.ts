import { describe, expect, it } from 'vitest';
import { subInSchema, teamActionSchema } from '../teamActionSchema';

describe('teamActionSchema', () => {
  it('rejects a reason shorter than 3 characters after trimming', () => {
    const result = teamActionSchema.safeParse({ reason: '  ab  ' });
    expect(result.success).toBe(false);
    expect(result.error?.issues[0].message).toBe(
      'Give a reason (at least 3 characters).',
    );
  });

  it('trims the reason', () => {
    expect(teamActionSchema.parse({ reason: ' abc ' })).toEqual({
      reason: 'abc',
    });
  });

  it('rejects a reason over 500 characters', () => {
    expect(
      teamActionSchema.safeParse({ reason: 'a'.repeat(501) }).success,
    ).toBe(false);
    expect(
      teamActionSchema.safeParse({ reason: 'a'.repeat(500) }).success,
    ).toBe(true);
  });
});

describe('subInSchema', () => {
  it('accepts a null replacing_id', () => {
    expect(subInSchema.parse({ reason: 'abc', replacing_id: null })).toEqual({
      reason: 'abc',
      replacing_id: null,
    });
  });

  it('rejects a non-positive replacing_id', () => {
    expect(
      subInSchema.safeParse({ reason: 'abc', replacing_id: 0 }).success,
    ).toBe(false);
  });
});
