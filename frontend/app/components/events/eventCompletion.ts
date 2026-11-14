import { EventState, type EventType } from '~/components/events/schemas';
import type { OrgFeatureAccess } from '~/features/org-features';

export function canCompleteEvent(
  event: Pick<EventType, 'state' | 'user_can_manage_event_staff'> | undefined,
  access: Pick<OrgFeatureAccess, 'settled'>,
): boolean {
  return (
    !!event?.user_can_manage_event_staff &&
    access.settled &&
    (event.state === EventState.ROLL_CALL || event.state === EventState.IN_PROGRESS)
  );
}
