import type { EventSignupType } from './schemas';
import { REMOVED_SIGNUP_STATUSES, SignupStatus } from './schemas';

export interface SignupPartitions {
  active: EventSignupType[];
  tentative: EventSignupType[];
  waitlisted: EventSignupType[];
  removed: EventSignupType[];
}

const removedStatuses: ReadonlySet<string> = new Set(REMOVED_SIGNUP_STATUSES);

export function isRemovedSignup(status: string): boolean {
  return removedStatuses.has(status);
}

export function partitionSignups(signups: EventSignupType[]): SignupPartitions {
  const parts: SignupPartitions = {
    active: [],
    tentative: [],
    waitlisted: [],
    removed: [],
  };
  for (const signup of signups) {
    if (isRemovedSignup(signup.status)) parts.removed.push(signup);
    else if (signup.status === SignupStatus.TENTATIVE)
      parts.tentative.push(signup);
    else if (signup.status === SignupStatus.WAITLISTED)
      parts.waitlisted.push(signup);
    else parts.active.push(signup);
  }
  return parts;
}
