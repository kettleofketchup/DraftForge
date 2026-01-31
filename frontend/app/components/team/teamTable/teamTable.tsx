import { memo, useMemo } from 'react';
import { PlayerPopover } from '~/components/player';
import type { TeamType } from '~/components/tournament/types';
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { UserStrip } from '~/components/user/UserStrip';
import { UserAvatar } from '~/components/user/UserAvatar';

interface TeamTableProps {
  team?: TeamType;
  /** Compact mode: shorter usernames, smaller positions */
  compact?: boolean;
  /** Use UserStrip layout instead of table rows */
  useStrips?: boolean;
}

// Custom comparison function for memo that properly detects team member changes
const teamTablePropsAreEqual = (
  prevProps: TeamTableProps,
  nextProps: TeamTableProps
): boolean => {
  // If compact or useStrips changed, re-render
  if (prevProps.compact !== nextProps.compact) return false;
  if (prevProps.useStrips !== nextProps.useStrips) return false;

  // If team reference is the same, no need to re-render
  if (prevProps.team === nextProps.team) return true;

  // If one is undefined and other is not, re-render
  if (!prevProps.team || !nextProps.team) return false;

  // Check if team pk changed
  if (prevProps.team.pk !== nextProps.team.pk) return false;

  // Check if members array length changed
  const prevMembers = prevProps.team.members || [];
  const nextMembers = nextProps.team.members || [];
  if (prevMembers.length !== nextMembers.length) return false;

  // Check if member pks are the same (order matters for team display)
  for (let i = 0; i < prevMembers.length; i++) {
    if (prevMembers[i]?.pk !== nextMembers[i]?.pk) return false;
  }

  return true;
};

export const TeamTable: React.FC<TeamTableProps> = memo(({ team, compact = false, useStrips = false }) => {
  // Memoize sorted members to avoid mutation and recalculation
  const members = useMemo(() => {
    if (!team?.members || team.members.length === 0) return [];

    // Use spread to avoid mutating original array
    return [...team.members].sort((a: UserType, b: UserType) => {
      if (!a.mmr && !b.mmr) return 0;
      if (!a.mmr) return 1; // Treat undefined MMR as lower
      if (!b.mmr) return -1; // Treat undefined MMR as lower
      if (a.mmr === b.mmr) {
        if (a.username && b.username) {
          return a.username.localeCompare(b.username);
        }
      }
      if (a.mmr >= b.mmr) return -1;
      if (a.mmr < b.mmr) return 1;
      return 0;
    });
  }, [team?.members]);

  // Early return if team is undefined or has no members
  if (!team || members.length === 0) {
    return (
      <div className="p-4 text-center text-gray-500">
        <p>No team members found</p>
      </div>
    );
  }

  // UserStrip layout - compact horizontal cards with responsive grid
  if (useStrips) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-1.5">
        {members.map((user: UserType) => (
          <UserStrip
            key={`TeamStrip-${user.pk}`}
            user={user}
            data-testid={`team-member-${user.pk}`}
          />
        ))}
      </div>
    );
  }

  // Default table layout
  return (
    <Table>
      <TableCaption>Team Members</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead>Member</TableHead>
          <TableHead>MMR</TableHead>
          <TableHead className="hidden md:table-cell">Positions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((user: UserType, idx: number) => (
          <TableRow key={`TeamTableRow-${user.pk}`}>
            <TableCell>
              <PlayerPopover player={user}>
                <div className="flex items-center gap-2 hover:text-primary transition-colors">
                  <UserAvatar
                    user={user}
                    size="md"
                    className="hover:ring-2 hover:ring-primary transition-all"
                  />
                  <span className={compact ? "hidden" : "hidden 3xl:inline"}>
                    {user.nickname || user.username}
                  </span>
                  <span
                    className={compact ? "inline" : "inline 3xl:hidden"}
                    title={user.nickname || user.username}
                  >
                    {compact
                      ? (user.nickname || user.username).length > 6
                        ? `${(user.nickname || user.username).substring(0, 6)}…`
                        : user.nickname || user.username
                      : (user.nickname || user.username).length > 10
                        ? `${(user.nickname || user.username).substring(0, 12)}...`
                        : user.nickname || user.username}
                  </span>
                </div>
              </PlayerPopover>
            </TableCell>
            <TableCell>{user.mmr ?? 'N/A'}</TableCell>
            <TableCell className="hidden md:table-cell">
              <RolePositions user={user} compact={compact} disableTooltips={compact} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}, teamTablePropsAreEqual);
