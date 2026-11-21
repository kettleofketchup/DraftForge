import type { TrackDetailProps } from '~/features/standing/panels';
import { MemberConductHistory } from './MemberConductHistory';

export type ConductDetailProps = Pick<
  TrackDetailProps,
  'orgId' | 'orgUserPk' | 'timeZone' | 'access' | 'onClose'
>;

export function ConductDetail({
  orgId,
  orgUserPk,
  timeZone,
  access,
  onClose,
}: ConductDetailProps) {
  return (
    <MemberConductHistory
      orgId={orgId}
      access={access}
      orgUserPk={orgUserPk}
      timeZone={timeZone}
      onClose={onClose}
    />
  );
}
