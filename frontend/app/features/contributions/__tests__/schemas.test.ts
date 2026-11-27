import { describe, expect, it } from 'vitest';
import {
  CONTRIBUTION_KINDS,
  ContributionEntrySchema,
  KIND_LABELS,
  RATED_KINDS,
} from '../schemas';

describe('contribution kinds', () => {
  it('parses promotion point reversals', () => {
    for (const kind of ['promo_void', 'promo_restore'] as const) {
      const entry = ContributionEntrySchema.parse({
        pk: 1,
        kind,
        points: kind === 'promo_void' ? -1 : 1,
        event: { id: 4, name: 'Weekly Cup' },
        event_name: 'Weekly Cup',
        occurred_at: '2026-11-01T12:00:00Z',
      });
      expect(entry.kind).toBe(kind);
    }
  });

  it('labels promotion point reversals', () => {
    expect(CONTRIBUTION_KINDS).toContain('promo_void');
    expect(CONTRIBUTION_KINDS).toContain('promo_restore');
    expect(KIND_LABELS.promo_void).toBe('Promotion point voided');
    expect(KIND_LABELS.promo_restore).toBe('Promotion point restored');
  });

  it('keeps reversals out of the rated kinds', () => {
    expect(RATED_KINDS).not.toContain('promo_void');
    expect(RATED_KINDS).not.toContain('promo_restore');
  });
});
