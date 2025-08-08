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
import { PositionEnum } from '~/components/user';
import type { UserType } from '~/components/user/types';
import { AvatarUrl } from '~/index';
interface TeamTableProps {
  team?: TeamType;
}
const positions = (user: UserType) => {
  if (!user.positions) return null;
  return (
    <div className="flex gap-1 flex-wrap">
      {Object.entries(user.positions)
        .filter(([_, value]) => value)
        .map(([pos]) => (
          <span key={pos} className="badge badge-info p-1">
            {PositionEnum[pos as keyof typeof PositionEnum]}
          </span>
        ))}
    </div>
  );
};

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
                <span>{user.nickname || user.username}</span>
              </div>
            </TableCell>
            <TableCell>{user.mmr ?? 'N/A'}</TableCell>
            <TableCell>{user.positions ? positions(user) : 'N/A'}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
