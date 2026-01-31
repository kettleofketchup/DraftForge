import { useMemo } from 'react';
import { Trophy, Users } from 'lucide-react';
import { InfoDialog } from '~/components/ui/dialogs';
import { RolePositions } from '~/components/user/positions';
import { TeamPositionCoverageRow } from '~/components/teamdraft/TeamPositionCoverage';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';
import { PlayerPopover } from '~/components/player';
import { UserAvatar } from '~/components/user/UserAvatar';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';

interface TeamModalProps {
  team: TeamType;
  captain: UserType;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const TeamModal: React.FC<TeamModalProps> = ({
  team,
  captain,
  open,
  onOpenChange,
}) => {
  const teamName = team.name || `${captain.nickname || captain.username}'s Team`;
  const hasMembers = team.members && team.members.length > 0;

  const avgMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    const total = team.members.reduce(
      (sum: number, m: UserType) => sum + (m.mmr || 0),
      0
    );
    return Math.round(total / team.members.length);
  }, [team.members]);

  const totalMMR = useMemo(() => {
    if (!team.members || team.members.length === 0) return 0;
    return team.members.reduce(
      (sum: number, m: UserType) => sum + (m.mmr || 0),
      0
    );
  }, [team.members]);

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
    >
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
      <div className="flex items-center gap-4 p-3 bg-muted/50 rounded-lg">
        <UserAvatar user={captain} size="xl" border="primary" />
        <div className="flex-1">
          <div className="font-semibold">
            {captain.nickname || captain.username}
            <span className="ml-2 text-xs text-primary">(Captain)</span>
          </div>
          <div className="text-sm text-muted-foreground">
            {captain.mmr?.toLocaleString() || 'N/A'} MMR
          </div>
        </div>
        <RolePositions user={captain} />
      </div>

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
                        <UserAvatar user={member} size="md" className="hover:ring-2 hover:ring-primary transition-all" />
                        <span className="font-medium">
                          {member.nickname || member.username}
                        </span>
                        {member.pk === captain.pk && (
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
    </InfoDialog>
  );
};
