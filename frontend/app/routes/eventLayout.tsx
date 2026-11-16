import { Outlet, useParams } from 'react-router';

import { useEvent } from '~/hooks/useEvent';
import { DisplayOrgProvider } from '~/lib/displayOrgContext';

export default function EventDisplayOrgLayout() {
  const { eventId } = useParams();
  const id = eventId ? parseInt(eventId, 10) : NaN;
  const { data: event } = useEvent(Number.isNaN(id) ? null : id);
  return (
    <DisplayOrgProvider orgId={event?.organization}>
      <Outlet />
    </DisplayOrgProvider>
  );
}
