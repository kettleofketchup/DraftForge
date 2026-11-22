import { useMemo } from 'react';
import type { OrgFeatureAccess } from '~/features/org-features';
import { useEvents } from '~/hooks/useEvent';
import { LedgerTable } from './admin/LedgerTable';
import { ManualAwardForm, type AwardEvent } from './admin/ManualAwardForm';
import { PointValuesSettings } from './admin/PointValuesSettings';
import { MemberBreakdown } from './MemberBreakdown';

export interface ContributionsDetailProps {
  orgId: number;
  orgUserPk: number;
  period: string;
  timeZone: string | undefined;
  access: OrgFeatureAccess;
  onClose: () => void;
}

export function ContributionsDetail({
  orgId,
  orgUserPk,
  period,
  timeZone,
  access,
  onClose,
}: ContributionsDetailProps) {
  return (
    <MemberBreakdown
      orgId={orgId}
      orgUserPk={orgUserPk}
      period={period}
      timeZone={timeZone}
      access={access}
      onClose={onClose}
    />
  );
}

export interface ContributionsAdminProps {
  orgId: number;
  timeZone: string | undefined;
  access: OrgFeatureAccess;
}

export function ContributionsAdmin(props: ContributionsAdminProps) {
  if (!props.access.settled || !props.access.canManageContributions)
    return null;
  return <ContributionsAdminSection {...props} />;
}

function ContributionsAdminSection({
  orgId,
  timeZone,
  access,
}: ContributionsAdminProps) {
  const { data: orgEvents } = useEvents({ organization: orgId });
  const events = useMemo<AwardEvent[]>(
    () =>
      (orgEvents ?? []).map((e) => ({
        id: e.id,
        name: e.name,
        scheduled_at: e.scheduled_at,
      })),
    [orgEvents],
  );

  return (
    <section
      className="flex flex-col gap-6 rounded-lg border border-primary/40 bg-base-900/40 p-4"
      data-testid="contributions-admin"
    >
      <div>
        <h3 className="text-lg font-semibold">Manage contributions</h3>
        <p className="text-sm text-muted-foreground">
          Org owners and admins only.
        </p>
      </div>
      <PointValuesSettings orgId={orgId} access={access} />
      <section className="flex flex-col gap-3" data-testid="manual-award">
        <h4 className="font-semibold">Manual award</h4>
        <ManualAwardForm
          orgId={orgId}
          access={access}
          timeZone={timeZone}
          events={events}
        />
      </section>
      <LedgerTable
        orgId={orgId}
        access={access}
        timeZone={timeZone}
        events={events}
      />
    </section>
  );
}
