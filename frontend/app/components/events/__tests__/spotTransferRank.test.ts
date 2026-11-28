import { describe, expect, it } from 'vitest';

import {
  compareRank,
  seatStatusAbove,
  swapWouldDemoteRecipient,
} from '../spotTransferRank';

const r = (id: number, status: string, line_rank: number | null) => ({
  id,
  status,
  line_rank,
});

describe('spotTransferRank', () => {
  it('ranks by status class before line rank', () => {
    expect(compareRank(r(1, 'approved', 7), r(2, 'pending_approval', 3))).toBe(
      -1,
    );
    expect(compareRank(r(1, 'waitlisted', 1), r(2, 'tentative', 1))).toBe(-1);
    expect(compareRank(r(1, 'cancelled', 1), r(2, 'tentative', 9))).toBe(1);
  });

  it('breaks ties by line rank, unranked last, then id', () => {
    expect(compareRank(r(1, 'rsvp', 2), r(2, 'pending_approval', 4))).toBe(-1);
    expect(compareRank(r(1, 'rsvp', null), r(2, 'rsvp', 9))).toBe(1);
    expect(compareRank(r(1, 'rsvp', null), r(2, 'rsvp', null))).toBe(-1);
  });

  it('orders seat statuses rsvp < pending < approved < confirmed', () => {
    expect(seatStatusAbove('confirmed', 'approved')).toBe(true);
    expect(seatStatusAbove('approved', 'pending_approval')).toBe(true);
    expect(seatStatusAbove('rsvp', 'pending_approval')).toBe(false);
    expect(seatStatusAbove('waitlisted', 'rsvp')).toBe(false);
  });

  it('matches the server demotion rule', () => {
    expect(
      swapWouldDemoteRecipient(
        r(1, 'approved', 7),
        r(2, 'pending_approval', 3),
      ),
    ).toBe(false);
    expect(
      swapWouldDemoteRecipient(r(1, 'waitlisted', 3), r(2, 'approved', 7)),
    ).toBe(true);
    expect(
      swapWouldDemoteRecipient(r(1, 'approved', 3), r(2, 'confirmed', 7)),
    ).toBe(true);
    expect(
      swapWouldDemoteRecipient(r(1, 'approved', 3), r(2, 'approved', 7)),
    ).toBe(false);
  });
});
