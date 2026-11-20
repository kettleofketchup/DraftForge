import { Trophy, Users } from 'lucide-react';
import { useMemo, useState } from 'react';
import { PlayerPopover } from '~/components/player';
import {
  LeadershipProblemBadge,
  leadershipProblemSentence,
} from '~/components/team/manage/LeadershipProblemBadge';
import { RosterStatusBadge } from '~/components/team/manage/RosterStatusBadge';
import { TeamManageDialog } from '~/components/team/manage/TeamManageDialog';
import {
  rosterSignature,
  useInvalidateOnRosterChange,
  useManagedTeam,
} from '~/components/team/manage/useTeamManagement';
import { TeamPositionCoverageRow } from '~/components/teamdraft/TeamPositionCoverage';
import type { TeamType } from '~/components/tournament/types';
import { SecondaryButton } from '~/components/ui/buttons';
import { InfoDialog } from '~/components/ui/dialogs';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';
import { DisplayName } from '~/components/user/avatar';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { UserAvatar } from '~/components/user/UserAvatar';
import { useUserStore } from '~/store/userStore';

const DEPUTY_CODES = new Set(['deputy_not_member', 'deputy_is_captain']);

interface TeamModalProps {
  team: TeamType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const TeamModal: React.FC<TeamModalProps> = ({
  team,
  open,
  onOpenChange,
}) => {
  const captain = team.captain ?? null;
  const deputy = team.deputy_captain ?? null;
  const teamName =
    team.name || (captain ? `${DisplayName(captain)}'s Team` : 'Team');
  const hasMembers = team.members && team.members.length > 0;

  const avgMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    const total = team.members.reduce(
      (sum: number, m: UserType) => sum + (m.mmr || 0),
      0,
    );
    return Math.round(total / team.members.length);
  }, [team.members]);

  const totalMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    return team.members.reduce(
      (sum: number, m: UserType) => sum + (m.mmr || 0),
      0,
    );
  }, [team.members]);

  const currentUser = useUserStore((s) => s.currentUser);
  const managed = useManagedTeam(team.pk, {
    enabled: open && !!currentUser?.pk,
  });
  const canManage = managed.data?.can_manage_team === true;
  const [manageOpen, setManageOpen] = useState(false);
  useInvalidateOnRosterChange(team.pk, rosterSignature(team));

  const tournamentPk = managed.data?.tournament?.pk;
  const organizationPk = managed.data?.organization_pk ?? null;
  const leaguePk = managed.data?.league_pk ?? null;

  const problems = canManage ? (managed.data?.leadership_problems ?? []) : [];
  const captainProblems = problems.filter(
    (p) => p.code === 'captain_not_member',
  );
  const deputyProblems = problems.filter((p) => DEPUTY_CODES.has(p.code));

  const sortedMembers = useMemo(() => {
    if (!team.members) return [];
    return [...team.members].sort((a: UserType, b: UserType) => {
      if (!a.mmr && !b.mmr) return 0;
      if (!a.mmr) return 1;
      if (!b.mmr) return -1;
      return b.mmr - a.mmr;
    });
  }, [team.members]);

  return (
    <InfoDialog
      open={open}
      onOpenChange={onOpenChange}
      title={teamName}
      size="lg"
      showClose={false}
      data-testid="team-modal"
    >
      {canManage && team.pk != null && (
        <div className="flex justify-end mb-3">
          <SecondaryButton
            size="sm"
            data-testid="team-manage-button"
            onClick={() => setManageOpen(true)}
          >
            Manage team
          </SecondaryButton>
        </div>
      )}

      {problems.length > 0 && managed.data && (
        <p
          className="text-sm text-destructive mb-3"
          data-testid="team-modal-leadership-problems"
        >
          {problems
            .map((p) => leadershipProblemSentence(p, managed.data))
            .join(' ')}
        </p>
      )}

      {/* Team Stats */}
      {hasMembers && (
        <div className="flex items-center gap-4 text-sm text-muted-foreground mb-4">
          <span className="flex items-center gap-1.5">
            <Users className="h-4 w-4" />
            {team.members?.length} players
          </span>
          <span className="flex items-center gap-1.5">
            <Trophy className="h-4 w-4 text-yellow-500" />
            {avgMMR.toLocaleString()} avg MMR
          </span>
          <span className="text-muted-foreground/70">
            ({totalMMR.toLocaleString()} total)
          </span>
        </div>
      )}

      {/* Position Coverage */}
      <div className="p-3 bg-muted/30 rounded-lg mb-4">
        <h5 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
          Position Coverage
        </h5>
        <TeamPositionCoverageRow team={team} teamName={teamName} />
      </div>

      {/* Captain Section */}
      {captain && (
        <div
          className="flex items-center gap-4 p-3 bg-muted/50 rounded-lg"
          data-testid="team-modal-captain"
        >
          <UserAvatar user={captain} size="xl" border="primary" />
          <div className="flex-1">
            <div className="font-semibold">
              {DisplayName(captain)}
              <span className="ml-2 text-xs text-primary">(Captain)</span>
              {managed.data && captainProblems.length > 0 && (
                <span className="ml-2">
                  <LeadershipProblemBadge
                    problems={captainProblems}
                    team={managed.data}
                  />
                </span>
              )}
            </div>
            <div className="text-sm text-muted-foreground">
              {captain.mmr?.toLocaleString() || 'N/A'} MMR
            </div>
          </div>
          <RolePositions user={captain} />
        </div>
      )}

      {deputy && (
        <div
          className="flex items-center gap-3 px-3 py-2 mt-2"
          data-testid="team-modal-deputy"
        >
          <UserAvatar user={deputy} size="md" />
          <span className="font-medium">{DisplayName(deputy)}</span>
          <RosterStatusBadge status="deputy" />
          {managed.data && deputyProblems.length > 0 && (
            <LeadershipProblemBadge
              problems={deputyProblems}
              team={managed.data}
            />
          )}
        </div>
      )}

      {/* Team Members Table */}
      {hasMembers ? (
        <div className="max-h-[400px] overflow-y-auto mt-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[50px]">#</TableHead>
                <TableHead>Player</TableHead>
                <TableHead className="text-right">MMR</TableHead>
                <TableHead>Positions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedMembers.map((member: UserType, idx: number) => (
                <TableRow key={`team-modal-member-${member.pk}`}>
                  <TableCell className="font-medium text-muted-foreground">
                    {idx + 1}
                  </TableCell>
                  <TableCell>
                    <PlayerPopover player={member}>
                      <div className="flex items-center gap-3 cursor-pointer hover:text-primary transition-colors">
                        <UserAvatar
                          user={member}
                          size="md"
                          className="hover:ring-2 hover:ring-primary transition-all"
                        />
                        <span className="font-medium">
                          {DisplayName(member)}
                        </span>
                        {member.pk === captain?.pk && (
                          <span className="text-xs text-primary">(C)</span>
                        )}
                      </div>
                    </PlayerPopover>
                  </TableCell>
                  <TableCell className="text-right">
                    {member.mmr?.toLocaleString() || 'N/A'}
                  </TableCell>
                  <TableCell>
                    <RolePositions user={member} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ) : (
        <div className="p-8 text-center text-muted-foreground">
          No players drafted yet
        </div>
      )}

      <RosterSection
        title="Stand-ins"
        users={team.dropin_members}
        status="standin"
      />
      <RosterSection
        title="Dropouts"
        users={team.left_members}
        status="dropout"
      />
      {canManage && team.pk != null && (
        <TeamManageDialog
          open={manageOpen}
          onOpenChange={setManageOpen}
          teamId={team.pk}
          tournamentPk={tournamentPk}
          organizationPk={organizationPk}
          leaguePk={leaguePk}
          onTeamGone={() => onOpenChange(false)}
        />
      )}
    </InfoDialog>
  );
};

function RosterSection({
  title,
  users,
  status,
}: {
  title: string;
  users: UserType[] | null | undefined;
  status: 'standin' | 'dropout';
}) {
  if (!users?.length) return null;
  return (
    <div className="mt-4">
      <h5 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
        {title}
      </h5>
      <ul className="flex flex-col gap-2">
        {users.map((u) => (
          <li
            key={`team-modal-${status}-${u.pk}`}
            data-testid={`team-modal-${status}-${u.pk}`}
            className={`flex items-center gap-3 px-3 ${status === 'dropout' ? 'text-muted-foreground' : ''}`}
          >
            <UserAvatar user={u} size="md" />
            <span className="font-medium">{DisplayName(u)}</span>
            <RosterStatusBadge status={status} />
          </li>
        ))}
      </ul>
    </div>
  );
}
