import { type EventSignupType, SignupStatus } from './schemas';

// Mirrors backend events/services.py _PLACE_CLASS, _place_rank and _seat_status_above.
const PLACE_CLASS: Record<string, number> = {
  [SignupStatus.APPROVED]: 0,
  [SignupStatus.CONFIRMED]: 0,
  [SignupStatus.RSVP]: 1,
  [SignupStatus.PENDING_APPROVAL]: 1,
  [SignupStatus.WAITLISTED]: 2,
  [SignupStatus.TENTATIVE]: 3,
};
const UNPLACED_CLASS = 4;

const SEAT_STATUS_ORDER: readonly string[] = [
  SignupStatus.RSVP,
  SignupStatus.PENDING_APPROVAL,
  SignupStatus.APPROVED,
  SignupStatus.CONFIRMED,
];

type Ranked = Pick<EventSignupType, 'id' | 'status' | 'line_rank'>;

export function placeRank(row: Ranked): [number, number, number] {
  return [
    PLACE_CLASS[row.status] ?? UNPLACED_CLASS,
    row.line_rank ?? Number.POSITIVE_INFINITY,
    row.id,
  ];
}

export function compareRank(a: Ranked, b: Ranked): number {
  const ra = placeRank(a);
  const rb = placeRank(b);
  for (let i = 0; i < ra.length; i++) {
    if (ra[i] !== rb[i]) return ra[i] < rb[i] ? -1 : 1;
  }
  return 0;
}

export function seatStatusAbove(status: string, other: string): boolean {
  const a = SEAT_STATUS_ORDER.indexOf(status);
  const b = SEAT_STATUS_ORDER.indexOf(other);
  return a >= 0 && b >= 0 && a > b;
}

/** Member swaps may only move the recipient to an equal or better place. */
export function swapWouldDemoteRecipient(
  giver: Ranked,
  target: Ranked,
): boolean {
  return (
    compareRank(giver, target) >= 0 ||
    seatStatusAbove(target.status, giver.status)
  );
}
