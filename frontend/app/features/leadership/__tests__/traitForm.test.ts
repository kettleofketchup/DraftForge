import { describe, expect, it } from 'vitest';
import {
  slugifyTraitKey,
  toTraitForm,
  toTraitPut,
  traitFieldErrors,
} from '../traitForm';

const httpError = (data: unknown) => ({ response: { status: 400, data } });

describe('slugifyTraitKey', () => {
  it('lower-cases and joins words with underscores', () => {
    expect(slugifyTraitKey('Shot Calling!', new Set())).toBe('shot_calling');
  });

  it('suffixes a taken key', () => {
    expect(slugifyTraitKey('Shot calling', new Set(['shot_calling']))).toBe(
      'shot_calling_2',
    );
    expect(slugifyTraitKey('Calm', new Set(['calm', 'calm_2', 'calm_3']))).toBe(
      'calm_4',
    );
  });

  it('keeps long keys within 32 characters, suffix included', () => {
    const label = 'A very long trait name that keeps on going';
    const key = slugifyTraitKey(label, new Set());
    expect(key.length).toBeLessThanOrEqual(32);
    const second = slugifyTraitKey(label, new Set([key]));
    expect(second.length).toBeLessThanOrEqual(32);
    expect(second).toMatch(/_2$/);
  });

  it('falls back to trait for a label with no letters or digits', () => {
    expect(slugifyTraitKey('***', new Set())).toBe('trait');
  });
});

describe('trait form values', () => {
  it('orders by order and writes the index back as order', () => {
    const form = toTraitForm([
      { key: 'b', label: 'B', order: 2, active: true },
      { key: 'a', label: 'A', order: 0, active: false },
    ]);
    expect(form.traits).toEqual([
      { key: 'a', label: 'A', active: false, saved: true },
      { key: 'b', label: 'B', active: true, saved: true },
    ]);
    expect(toTraitPut({ traits: [...form.traits].reverse() })).toEqual([
      { key: 'b', label: 'B', order: 0, active: true },
      { key: 'a', label: 'A', order: 1, active: false },
    ]);
  });

  it('trims labels', () => {
    expect(
      toTraitPut({
        traits: [{ key: 'a', label: '  A  ', active: true, saved: false }],
      }),
    ).toEqual([{ key: 'a', label: 'A', order: 0, active: true }]);
  });
});

describe('traitFieldErrors', () => {
  it('maps per-row errors onto their row', () => {
    expect(
      traitFieldErrors(httpError({ traits: [{}, { label: ['Required.'] }] })),
    ).toEqual([['traits.1.label', 'Required.']]);
  });

  it('maps a detail onto the list root', () => {
    expect(
      traitFieldErrors(
        httpError({ detail: ['At most 8 traits can be active.'] }),
      ),
    ).toEqual([['traits', 'At most 8 traits can be active.']]);
  });

  it('maps nothing for an unrelated payload', () => {
    expect(traitFieldErrors(new Error('boom'))).toEqual([]);
    expect(traitFieldErrors(httpError({ other: ['x'] }))).toEqual([]);
  });
});
