import { OpsNoticesCard } from './OpsNoticesCard';
import { canSeeEventOpsNotices } from './opsNoticesAccess';

interface EventOpsNoticesSlotProps {
  event: {
    id: number;
    user_is_event_operator?: boolean;
    user_can_manage?: boolean;
  };
}

export function EventOpsNoticesSlot({ event }: EventOpsNoticesSlotProps) {
  return canSeeEventOpsNotices(event) ? (
    <OpsNoticesCard eventId={event.id} />
  ) : null;
}
