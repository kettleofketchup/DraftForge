// frontend/app/components/team/TeamPopoverContent.tsx
import { memo, useMemo } from 'react';
import { Trophy, Users } from 'lucide-react';
import { RolePositions } from '~/components/user/positions';
import { UserAvatar } from '~/components/user/UserAvatar';
import { TeamPositionCoverageRow } from '~/components/teamdraft/TeamPositionCoverage';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';
import type { TeamType } from '~/components/tournament/types';
import type { UserType } from '~/components/user/types';

// Memoized player row for team popover
const TeamMemberRow = memo(({
  member,
  isCaptain,
  onPlayerHover,
  onPlayerLeave,
  onPlayerClick,
}: {
  member: UserType;
  isCaptain: boolean;
  onPlayerHover: (player: UserType, el: HTMLElement) => void;
  onPlayerLeave: () => void;
  onPlayerClick: (player: UserType) => void;
}) => (
  <TableRow>
    <TableCell>
      <div
        className="flex items-center gap-2 cursor-pointer hover:text-primary transition-colors"
        onMouseEnter={(e) => onPlayerHover(member, e.currentTarget)}
        onMouseLeave={onPlayerLeave}
        onClick={() => onPlayerClick(member)}
      >
        <UserAvatar
          user={member}
          size="md"
          className="hover:ring-2 hover:ring-primary transition-all"
        />
        <span className="font-medium">
          {member.nickname || member.username}
        </span>
        {isCaptain && (
          <span className="text-xs text-primary">(C)</span>
        )}
      </div>
    </TableCell>
    <TableCell className="text-right">
      {member.mmr?.toLocaleString() || 'N/A'}
    </TableCell>
    <TableCell>
      <RolePositions user={member} />
    </TableCell>
  </TableRow>
));
TeamMemberRow.displayName = 'TeamMemberRow';

export interface TeamPopoverContentProps {
  team: TeamType;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
  onPlayerHover: (player: UserType, el: HTMLElement) => void;
  onPlayerLeave: () => void;
  onPlayerClick: (player: UserType) => void;
}

export const TeamPopoverContent: React.FC<TeamPopoverContentProps> = ({
  team,
  onMouseEnter,
  onMouseLeave,
  onPlayerHover,
  onPlayerLeave,
  onPlayerClick,
}) => {
  const captain = team.captain;
  const teamName = team.name || `${captain?.nickname || captain?.username || 'Unknown'}'s Team`;
  const hasMembers = team.members && team.members.length > 0;

  const avgMMR = useMemo(() => {
    if (!hasMembers) return 0;
    return Math.round(
      team.members!.reduce((sum: number, m: UserType) => sum + (m.mmr || 0), 0) /
        team.members!.length
    );
  }, [team.members, hasMembers]);

  const sortedMembers = useMemo(() => {
    if (!hasMembers) return [];
    return [...team.members!].sort((a, b) => {
      if (!a.mmr && !b.mmr) return 0;
      if (!a.mmr) return 1;
      if (!b.mmr) return -1;
      return b.mmr - a.mmr;
    });
  }, [team.members, hasMembers]);

  return (
    <div onMouseEnter={onMouseEnter} onMouseLeave={onMouseLeave}>
      {/* Header */}
      <div className="flex items-center justify-between p-3 border-b">
        <div className="flex items-center gap-3">
          <UserAvatar user={captain} size="lg" />
          <div>
            <span className="font-medium">{teamName}</span>
            {hasMembers && (
              <div className="flex items-center gap-3 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Users className="h-3.5 w-3.5" />
                  {team.members?.length} players
                </span>
                <span className="flex items-center gap-1">
                  <Trophy className="h-3.5 w-3.5 text-yellow-500" />
                  {avgMMR.toLocaleString()} avg
                </span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Position Coverage */}
      <div className="p-3 border-b bg-muted/30">
        <h5 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
          Position Coverage
        </h5>
        <TeamPositionCoverageRow team={team} teamName={teamName} />
      </div>

      {/* Team Table or Empty State */}
      <div className="max-h-64 overflow-y-auto">
        {hasMembers ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Player</TableHead>
                <TableHead className="text-right">MMR</TableHead>
                <TableHead>Positions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sortedMembers.map((member) => (
                <TeamMemberRow
                  key={member.pk}
                  member={member}
                  isCaptain={captain?.pk === member.pk}
                  onPlayerHover={onPlayerHover}
                  onPlayerLeave={onPlayerLeave}
                  onPlayerClick={onPlayerClick}
                />
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="p-4 text-center text-muted-foreground">
            No players drafted yet
          </div>
        )}
      </div>

      {/* Click hint */}
      <div className="p-2 border-t text-center text-xs text-muted-foreground">
        Click for full view
      </div>
    </div>
  );
};
