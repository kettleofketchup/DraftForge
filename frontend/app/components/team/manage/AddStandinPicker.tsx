import type {
  OtherTeamSummary,
  RosterUser,
} from '~/components/api/teamManagementAPI';
import type { OrganizationType } from '~/components/organization/schemas';
import { UserCandidatePicker } from './UserCandidatePicker';

export interface AddStandinPickerProps {
  organization: OrganizationType | null | undefined;
  leaguePk: number | null | undefined;
  excludePks: number[];
  /** Rostered on another live team in this tournament; the server refuses them. */
  otherTeamPks?: number[];
  otherTeams?: OtherTeamSummary[];
  disabled?: boolean;
  onPick: (user: RosterUser) => void;
}

export function AddStandinPicker(props: AddStandinPickerProps) {
  return (
    <UserCandidatePicker
      {...props}
      mode="standin"
      testIdPrefix="team-standin"
    />
  );
}
