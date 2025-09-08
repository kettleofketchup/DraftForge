import { useEffect } from 'react';
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

export const TeamTable: React.FC<TeamTableProps> = ({ team }) => {
  // Early return if team is undefined or has no members
  if (!team || !team.members || team.members.length === 0) {
    return (
      <div className="p-4 text-center text-gray-500">
        <p>No team members found</p>
      </div>
    );
  }

  const members = team.members.sort((a, b) => {
    if (!a.mmr && !b.mmr) return 0;
    if (!a.mmr) return 1; // Treat undefined MMR as lower
    if (!b.mmr) return -1; // Treat undefined MMR as lower
    if (a.mmr >= b.mmr) return -1;
    if (a.mmr < b.mmr) return 1;
    return 0; // Default case
  });

  useEffect(() => {
    if (team) {
      console.debug(`TeamTable: team updated ${team.name}`);
    }
  }, [team.pk, team.captain?.pk, team.members?.length, team.draft_order]);
  return (
    <Table>
      <TableCaption>Team Members</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead>Member</TableHead>
          <TableHead>MMR</TableHead>
          <TableHead>Positions</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members.map((user: UserType, idx: number) => (
          <TableRow key={`TeamTableRow-${user.pk}`}>
            <TableCell>
              <div className="flex items-center gap-2">
                <span className="avatar w-8 h-8">
                  <img
                    src={AvatarUrl(user)}
                    alt={user.username}
                    className="rounded-full"
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
            </TableCell>
            <TableCell>{user.mmr ?? 'N/A'}</TableCell>
            <TableCell>
              <RolePositions user={user} />{' '}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
