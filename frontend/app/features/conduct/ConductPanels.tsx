import type { OrgFeatureAccess } from '~/features/org-features';
import { MemberConductHistory } from './MemberConductHistory';

export interface ConductDetailProps {
  orgId: number;
  orgUserPk: number;
  timeZone: string | undefined;
  access: OrgFeatureAccess;
}

export function ConductDetail({
  orgId,
  orgUserPk,
  timeZone,
  access,
}: ConductDetailProps) {
  return (
    <MemberConductHistory
      orgId={orgId}
      access={access}
      orgUserPk={orgUserPk}
      timeZone={timeZone}
    />
  );
}
