import { describe, expect, it } from 'vitest';
import { reviewAction } from '../reviewState';

const SCORES = { communication: 4 };

describe('reviewAction', () => {
  it('an unrated captain shows Rate', () => {
    expect(reviewAction({ scores: null, void_kind: '' })).toEqual({
      state: 'todo',
      label: 'Rate',
      badge: null,
    });
  });

  it('a withdrawn review shows Rate', () => {
    expect(reviewAction({ scores: SCORES, void_kind: 'withdrawn' })).toEqual({
      state: 'todo',
      label: 'Rate',
      badge: 'Withdrawn',
    });
  });

  it('a lifecycle-voided review no longer counts', () => {
    expect(reviewAction({ scores: SCORES, void_kind: 'lifecycle' })).toEqual({
      state: 'todo',
      label: 'Rate',
      badge: 'No longer counted',
    });
  });

  it('a live review can be edited', () => {
    expect(reviewAction({ scores: SCORES, void_kind: '' })).toEqual({
      state: 'submitted',
      label: 'Edit',
      badge: 'Submitted',
    });
  });

  it('a moderated review is view only', () => {
    expect(reviewAction({ scores: SCORES, void_kind: 'moderated' })).toEqual({
      state: 'moderated',
      label: 'View',
      badge: 'Removed by an organizer',
    });
  });
});
