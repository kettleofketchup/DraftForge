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
import { AvatarUrl } from '~/index';

interface TeamTableProps {
  team?: TeamType;
}

export const TeamTable: React.FC<TeamTableProps> = memo(({ team }) => {
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
                  <span className="avatar w-8 h-8">
                    <img
                      src={AvatarUrl(user)}
                      alt={user.username}
                      className="rounded-full hover:ring-2 hover:ring-primary transition-all"
                    />
                  </span>
                  <span className="hidden 3xl:inline">
                    {user.nickname || user.username}
                  </span>
                  <span
                    className="inline 3xl:hidden"
                    title={user.nickname || user.username}
                  >
                    {(user.nickname || user.username).length > 10
                      ? `${(user.nickname || user.username).substring(0, 12)}...`
                      : user.nickname || user.username}
                  </span>
                </div>
              </PlayerPopover>
            </TableCell>
            <TableCell>{user.mmr ?? 'N/A'}</TableCell>
            <TableCell className="hidden md:table-cell">
              <RolePositions user={user} />{' '}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
});
