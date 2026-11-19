import type { EventSignupType } from './schemas';

export interface SignupPartition {
  active: EventSignupType[];
  tentative: EventSignupType[];
  waitlisted: EventSignupType[];
}

export function partitionSignups(signups: EventSignupType[]): SignupPartition {
  return {
    active: signups.filter((s) => s.holds_seat ?? false),
    tentative: signups.filter((s) => s.status === 'tentative'),
    waitlisted: signups.filter((s) => s.status === 'waitlisted'),
  };
}
