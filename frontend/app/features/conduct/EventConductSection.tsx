import type { EventType } from '~/components/events/schemas';
import type { OrganizationType } from '~/components/organization/schemas';
import type { OrgFeatureAccess } from '~/features/org-features';
import { AttendancePanel } from './AttendancePanel';
import { ConductForecastCard } from './ConductForecastCard';
import {
  ATTENDANCE_STATES,
  eventConductEnabled,
  FORECAST_STATES,
} from './eventConduct';

export interface EventConductSectionProps {
  event: Pick<EventType, 'id' | 'organization' | 'state' | 'user_can_manage'>;
  access: OrgFeatureAccess;
  org: OrganizationType | undefined;
}

export function EventConductSection({
  event,
  access,
  org,
}: EventConductSectionProps) {
  if (!eventConductEnabled(event, org, access) || event.organization == null)
    return null;
  const orgId = event.organization;
  return (
    <>
      {FORECAST_STATES.has(event.state) && (
        <div className="mb-4">
          <ConductForecastCard
            key={`${orgId}:${event.id}`}
            orgId={orgId}
            eventId={event.id}
            access={access}
          />
        </div>
      )}
      {ATTENDANCE_STATES.has(event.state) && (
        <div className="mb-4">
          <AttendancePanel
            key={`${orgId}:${event.id}`}
            orgId={orgId}
            eventId={event.id}
            eventState={event.state}
            access={access}
          />
        </div>
      )}
    </>
  );
}
