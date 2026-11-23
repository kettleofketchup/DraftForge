import { describe, expect, it } from 'vitest';
import { RELEASE_BADGES, releaseBadge } from '../releaseState';
import { RELEASE_STATES } from '../schemas';

describe('releaseBadge', () => {
  it.each([
    ['released', 'Released', 'secondary'],
    ['pending', 'Pending release', 'default'],
    ['open', 'Window open', 'outline'],
    ['short', 'Not enough reviews', 'outline'],
    ['voided', 'Voided', 'destructive'],
    ['hidden', 'Hidden', 'outline'],
  ] as const)('%s reads %s', (state, label, tone) => {
    expect(releaseBadge(state)).toEqual({ label, tone });
  });

  it('covers every release state', () => {
    expect(Object.keys(RELEASE_BADGES).sort()).toEqual(
      [...RELEASE_STATES].sort(),
    );
  });
});
