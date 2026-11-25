import { describe, expect, it } from 'vitest';
import { GAME_TYPE } from '~/components/game/constants';
import {
  MmrChangeRequestSchema,
  MmrRequestListSchema,
  PendingCountSchema,
  UserMmrSummarySchema,
  rejectFormSchema,
  requestMmrFormSchema,
  staffSetFormSchema,
} from '../schemas';
import { mmrRequest, mmrSummary } from './fixtures';

const png = () => new File(['x'], 'shot.png', { type: 'image/png' });

describe('response schemas', () => {
  it('parses a server request row', () => {
    const row = mmrRequest({
      target: 'league',
      league: { pk: 5, name: 'Season 4' },
      status: 'superseded',
      approved_mmr: 5000,
    });
    expect(MmrChangeRequestSchema.parse(row)).toEqual(row);
    expect(MmrRequestListSchema.parse([row])).toHaveLength(1);
  });

  it('parses the summary', () => {
    const summary = mmrSummary();
    expect(UserMmrSummarySchema.parse(summary)).toEqual(summary);
  });

  it('parses the pending count', () => {
    expect(PendingCountSchema.parse({ count: 3 })).toEqual({ count: 3 });
  });

  it('rejects an unknown status', () => {
    expect(() =>
      MmrChangeRequestSchema.parse({ ...mmrRequest(), status: 'odd' }),
    ).toThrow();
  });
});

describe('requestMmrFormSchema', () => {
  const schema = requestMmrFormSchema(GAME_TYPE.DOTA2);

  it.each([0, 20001])('rejects requested_mmr %i', (value) => {
    const result = schema.safeParse({
      requested_mmr: value,
      screenshot: png(),
      note: '',
    });
    expect(result.success).toBe(false);
  });

  it('accepts a value with a screenshot', () => {
    const result = schema.safeParse({
      requested_mmr: '4800',
      screenshot: png(),
      note: 'season',
    });
    expect(result.success).toBe(true);
    expect(result.data?.requested_mmr).toBe(4800);
  });

  it('requires a screenshot', () => {
    expect(
      schema.safeParse({ requested_mmr: 4800, screenshot: null, note: '' })
        .success,
    ).toBe(false);
  });

  it('caps the note at 500 characters', () => {
    expect(
      schema.safeParse({
        requested_mmr: 4800,
        screenshot: png(),
        note: 'a'.repeat(501),
      }).success,
    ).toBe(false);
  });
});

describe('staffSetFormSchema', () => {
  const schema = staffSetFormSchema(GAME_TYPE.DOTA2);

  it('makes the screenshot optional', () => {
    expect(
      schema.safeParse({ mmr: 4800, screenshot: null, note: '' }).success,
    ).toBe(true);
    expect(schema.safeParse({ mmr: 4800, note: '' }).success).toBe(true);
  });

  it.each([0, 20001])('rejects mmr %i', (value) => {
    expect(schema.safeParse({ mmr: value, note: '' }).success).toBe(false);
  });
});

describe('rejectFormSchema', () => {
  it('requires a reason up to 500 characters', () => {
    expect(rejectFormSchema.safeParse({ reason: '' }).success).toBe(false);
    expect(rejectFormSchema.safeParse({ reason: '   ' }).success).toBe(false);
    expect(
      rejectFormSchema.safeParse({ reason: 'a'.repeat(501) }).success,
    ).toBe(false);
    expect(rejectFormSchema.safeParse({ reason: 'Blurry' }).success).toBe(true);
  });
});
