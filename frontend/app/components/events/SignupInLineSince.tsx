import type { EventSignupType } from '~/components/events/schemas';
import { HistoryTime } from '~/components/events/signupHistoryColumns';
import { isRemovedSignup } from '~/components/events/signupPartitions';

export function SignupInLineSince({
  signup,
  eventTimezone,
}: {
  signup: Pick<EventSignupType, 'id' | 'status' | 'signed_up_at'>;
  eventTimezone?: string;
}) {
  const since = signup.signed_up_at;
  if (!since || isRemovedSignup(signup.status)) return null;
  return (
    <span
      className="text-xs text-muted-foreground"
      data-testid={`signup-in-line-since-${signup.id}`}
    >
      in line since <HistoryTime iso={since} eventTimezone={eventTimezone} />
    </span>
  );
}
