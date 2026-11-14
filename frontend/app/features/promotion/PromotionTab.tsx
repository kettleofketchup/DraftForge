import type { OrgFeatureAccess } from '~/features/org-features';
import { PromotionDashboard } from './PromotionDashboard';
import { usePromoEvents } from './queries';
import type { SampleOrg, SampleSender } from './render';
import { TemplatesManager } from './TemplatesManager';

export interface PromotionTabProps {
  orgId: number;
  org: SampleOrg;
  sender: SampleSender | null | undefined;
  access: OrgFeatureAccess;
}

export function PromotionTab({ orgId, org, sender, access }: PromotionTabProps) {
  const { data: events } = usePromoEvents(orgId, access);
  return (
    <div className="flex flex-col gap-6" data-testid="promotion-tab">
      <div>
        <h2 className="text-xl font-semibold">Promotion</h2>
        <p className="text-sm text-muted-foreground">
          Invite recent players to upcoming events over Discord DMs.
        </p>
      </div>
      <PromotionDashboard orgId={orgId} access={access} />
      <TemplatesManager
        orgId={orgId}
        access={access}
        org={org}
        sender={sender}
        sampleEvent={events?.[0] ?? null}
      />
    </div>
  );
}
