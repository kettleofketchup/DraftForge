import { Megaphone } from 'lucide-react';
import { Link } from 'react-router';
import { SecondaryButton } from '~/components/ui/buttons';
import type { OrgFeatureAccess } from '~/features/org-features';
import { PROMOTABLE_STATES } from './schemas';

export interface PromoteEventButtonProps {
  event: { id: number; organization: number | null | undefined; state: string };
  access: Pick<OrgFeatureAccess, 'settled' | 'canUsePromotion'>;
}

export function canPromoteEvent(
  event: PromoteEventButtonProps['event'],
  access: PromoteEventButtonProps['access'],
): boolean {
  return (
    access.settled &&
    access.canUsePromotion &&
    event.organization != null &&
    PROMOTABLE_STATES.includes(event.state)
  );
}

export function PromoteEventButton({ event, access }: PromoteEventButtonProps) {
  if (!canPromoteEvent(event, access)) return null;
  return (
    <SecondaryButton size="sm" asChild>
      <Link
        to={`/organizations/${event.organization}?tab=promotion&event=${event.id}`}
        data-testid="event-promote-btn"
      >
        <Megaphone className="h-4 w-4 mr-1.5" />
        Promote
      </Link>
    </SecondaryButton>
  );
}
