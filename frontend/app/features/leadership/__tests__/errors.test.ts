import { describe, expect, it } from 'vitest';
import { refusalCode, refusalMessage } from '../errors';

function refused(status: number, code?: string, detail = 'x') {
  return {
    response: { status, data: code ? { code, detail } : { detail } },
  };
}

describe('refusalCode', () => {
  it('reads the code from the response body', () => {
    expect(refusalCode(refused(409, 'review_window_closed'))).toBe(
      'review_window_closed',
    );
  });

  it('is null for an error without a response', () => {
    expect(refusalCode(new Error())).toBeNull();
  });
});

describe('refusalMessage', () => {
  it('maps a known code', () => {
    expect(refusalMessage(refused(409, 'review_window_closed'))).toBe(
      'The review window has closed.',
    );
    expect(refusalMessage(refused(403, 'review_moderated'))).toBe(
      "An organizer removed your review, so it can't be changed.",
    );
    expect(refusalMessage(refused(409, 'trait_in_use'))).toBe(
      'This trait has scores. Deactivate it instead.',
    );
  });

  it('words not_in_pool by context', () => {
    expect(refusalMessage(refused(403, 'not_in_pool'))).toBe(
      "You can't rate this captain.",
    );
    expect(refusalMessage(refused(409, 'not_in_pool'), 'unvoid')).toBe(
      "The rater is no longer on this captain's team.",
    );
  });

  it('words not_permitted by context', () => {
    expect(refusalMessage(refused(403, 'not_permitted'))).toBe(
      "You can't do that here.",
    );
    expect(refusalMessage(refused(403, 'not_permitted'), 'member')).toBe(
      "Only org staff can see other captains' details.",
    );
  });

  it('words own-review moderation for any moderator', () => {
    expect(refusalMessage(refused(403, 'cannot_moderate_own_reviews'))).toBe(
      'You captained this team. Another moderator has to moderate its reviews.',
    );
  });

  it('words every release refusal', () => {
    const cases: [number, string, string][] = [
      [
        403,
        'cannot_release_own_reviews',
        'You captained this team. Another moderator has to release its results.',
      ],
      [409, 'already_released', 'These results were already released.'],
      [409, 'window_open', 'The review window is still open.'],
      [409, 'not_enough_reviews', 'Not enough reviews to release yet.'],
      [409, 'nothing_to_release', 'Nothing is waiting for release.'],
      [409, 'release_not_required', 'This org releases results automatically.'],
    ];
    for (const [status, code, text] of cases) {
      expect(refusalMessage(refused(status, code), 'release')).toBe(text);
    }
  });

  it('words a self-releasing settings change', () => {
    expect(
      refusalMessage(refused(409, 'would_release_own_results'), 'settings'),
    ).toBe(
      'This change would release your own results. Ask another moderator to release them first.',
    );
  });

  it('words a 404 by context', () => {
    expect(refusalMessage(refused(404), 'submit')).toBe(
      'This captain can no longer be rated.',
    );
    expect(refusalMessage(refused(404), 'withdraw')).toBe(
      'You have no review to withdraw.',
    );
    expect(refusalMessage(refused(404), 'moderate')).toBe(
      'That review no longer exists.',
    );
    expect(refusalMessage(refused(404))).toBe('That review no longer exists.');
  });

  it('maps the throttle', () => {
    expect(refusalMessage(refused(429))).toBe(
      'Too many changes. Try again in a minute.',
    );
  });

  it('falls back to the server detail', () => {
    expect(
      refusalMessage({ response: { status: 400, data: { detail: 'Custom' } } }),
    ).toBe('Custom');
  });

  it('falls back to a generic message', () => {
    expect(refusalMessage(new Error())).toBe('Something went wrong.');
  });
});
