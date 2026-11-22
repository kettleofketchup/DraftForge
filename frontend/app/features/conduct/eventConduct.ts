import { EventState } from '~/components/events/schemas';
import type { OrgFeatureAccess } from '~/features/org-features';

export const FORECAST_STATES: ReadonlySet<string> = new Set([
  EventState.UPCOMING,
  EventState.SIGNUPS_OPEN,
  EventState.ROLL_CALL,
]);

export const ATTENDANCE_STATES: ReadonlySet<string> = new Set([
  EventState.ROLL_CALL,
  EventState.IN_PROGRESS,
  EventState.COMPLETED,
  EventState.CANCELLED,
]);

export function eventConductEnabled(
  event:
    | { user_can_manage?: boolean | null; organization?: number | null }
    | null
    | undefined,
  org: { features?: readonly string[] | null } | null | undefined,
  access: Pick<OrgFeatureAccess, 'settled'>,
): boolean {
  return (
    event?.user_can_manage === true &&
    event.organization != null &&
    (org?.features ?? []).includes('conduct') &&
    access.settled
  );
}
