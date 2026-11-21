import { describe, expect, it } from 'vitest';
import { OrgFeatureRowsSchema } from '../schemas';

const row = (feature: string) => ({
  feature,
  enabled: false,
  notes: '',
  enabled_by: null,
  enabled_at: null,
});

describe('OrgFeatureRowsSchema', () => {
  it('accepts every feature row the backend returns, conduct included', () => {
    const parsed = OrgFeatureRowsSchema.parse([
      row('conduct'),
      row('contributions'),
      row('promotion'),
    ]);
    expect(parsed.map((r) => r.feature)).toEqual([
      'conduct',
      'contributions',
      'promotion',
    ]);
  });

  it('rejects an unknown feature key', () => {
    expect(() => OrgFeatureRowsSchema.parse([row('bogus')])).toThrow();
  });
});
