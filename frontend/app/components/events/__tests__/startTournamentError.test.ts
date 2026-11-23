import { describe, expect, it } from 'vitest';

import { startTournamentErrorMessage } from '../startTournamentError';

const HELD = 'The ready check is held for staff; resolve it before starting.';
const FALLBACK = 'Failed to start tournament';

describe('startTournamentErrorMessage', () => {
  it('shows the held message from the server', () => {
    expect(
      startTournamentErrorMessage({
        response: { data: { code: 'ready_check_held', error: HELD } },
      }),
    ).toBe(HELD);
  });

  it('falls back when the held response has no error text', () => {
    expect(
      startTournamentErrorMessage({
        response: { data: { code: 'ready_check_held' } },
      }),
    ).toBe(FALLBACK);
  });

  it('falls back for other errors', () => {
    expect(
      startTournamentErrorMessage({
        response: { data: { error: 'Something else broke.' } },
      }),
    ).toBe(FALLBACK);
    expect(startTournamentErrorMessage(new Error('Network Error'))).toBe(
      FALLBACK,
    );
  });

  it('falls back for undefined', () => {
    expect(startTournamentErrorMessage(undefined)).toBe(FALLBACK);
  });
});
