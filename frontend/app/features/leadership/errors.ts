import { extractApiError } from '~/lib/apiError';

export type RefusalContext =
  | 'submit'
  | 'withdraw'
  | 'moderate'
  | 'unvoid'
  | 'member'
  | 'trait'
  | 'release'
  | 'settings';

// backend/org/leadership/reviews.py ReviewRefused codes and
// backend/org/feature_errors.py.
const REFUSALS: Record<string, string> = {
  review_window_closed: 'The review window has closed.',
  snapshot_voided:
    'Reviews for this event were closed because the event was reopened or cancelled.',
  not_in_pool: "You can't rate this captain.",
  review_moderated: "An organizer removed your review, so it can't be changed.",
  cannot_moderate_own_reviews:
    'You captained this team. Another moderator has to moderate its reviews.',
  invalid_scores: 'Score every trait from 1 to 5.',
  reason_required: 'Give a reason.',
  not_moderated: 'Only a review removed by an organizer can be restored.',
  trait_in_use: 'This trait has scores. Deactivate it instead.',
  feature_locked: 'Leadership is not enabled for this organization.',
  not_permitted: "You can't do that here.",
};

const CONTEXT_REFUSALS: Partial<
  Record<RefusalContext, Record<string, string>>
> = {
  unvoid: { not_in_pool: "The rater is no longer on this captain's team." },
  member: { not_permitted: "Only org staff can see other captains' details." },
  release: {
    cannot_release_own_reviews:
      'You captained this team. Another moderator has to release its results.',
    already_released: 'These results were already released.',
    window_open: 'The review window is still open.',
    not_enough_reviews: 'Not enough reviews to release yet.',
    nothing_to_release: 'Nothing is waiting for release.',
    release_not_required: 'This org releases results automatically.',
  },
  settings: {
    would_release_own_results:
      'This change would release your own results. Ask another moderator to release them first.',
  },
};

const NOT_FOUND: Record<RefusalContext, string> = {
  submit: 'This captain can no longer be rated.',
  withdraw: 'You have no review to withdraw.',
  moderate: 'That review no longer exists.',
  unvoid: 'That review no longer exists.',
  member: 'That member is not in this organization.',
  trait: 'That trait was already deleted.',
  release: 'That event or captain is no longer in this organization.',
  settings: 'Leadership settings are not available here.',
};

type ResponseLike = { response?: { status?: number; data?: unknown } };

function response(err: unknown): ResponseLike['response'] {
  if (!err || typeof err !== 'object') return undefined;
  return (err as ResponseLike).response;
}

/** The DRF response body of an axios error, if any. */
export function drfErrorData(err: unknown): unknown {
  return response(err)?.data;
}

/** A DRF error value (`"msg"` or `["msg", ...]`) as its first message. */
export function firstMessage(value: unknown): string | null {
  const message = Array.isArray(value) ? value[0] : value;
  return typeof message === 'string' ? message : null;
}

export function refusalStatus(err: unknown): number | undefined {
  return response(err)?.status;
}

export function refusalText(code: string): string {
  return REFUSALS[code] ?? 'Something went wrong.';
}

export function refusalCode(err: unknown): string | null {
  const data = drfErrorData(err);
  if (!data || typeof data !== 'object') return null;
  const code = (data as Record<string, unknown>).code;
  return typeof code === 'string' && code.length > 0 ? code : null;
}

export function refusalMessage(err: unknown, context?: RefusalContext): string {
  const code = refusalCode(err);
  if (code) {
    const message =
      (context && CONTEXT_REFUSALS[context]?.[code]) ?? REFUSALS[code];
    if (message) return message;
  }
  const status = refusalStatus(err);
  if (status === 404) return NOT_FOUND[context ?? 'moderate'];
  if (status === 429) return 'Too many changes. Try again in a minute.';
  return extractApiError(err) ?? 'Something went wrong.';
}
