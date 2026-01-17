import { useEffect } from 'react';
import { PlayerPopover } from '~/components/player';
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
import { AvatarUrl } from '~/components/user/avatar';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import { UpdateCaptainButton } from './UpdateCaptainButton';
interface TournamentUsersTable {}
export const CaptainTable: React.FC<TournamentUsersTable> = () => {
  const tournament = useUserStore((state) => state.tournament);

  useEffect(() => {}, [tournament.users]);
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
  const members = () => {
    if (!tournament.users) return [];
    const sortedUsers = [...tournament.users].sort((a, b) => {
      if (!a.mmr && !b.mmr) return 0;
      if (!a.mmr) return 1; // Treat undefined MMR as lower
      if (!b.mmr) return -1; // Treat undefined MMR as lower
      if (a.mmr > b.mmr) return -1;
      if (a.mmr < b.mmr) return 1;
      return 0;
    });
    return sortedUsers;
  };

  return (
    <Table>
      <TableCaption>Tournament Users</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead>Member</TableHead>
          <TableHead>MMR</TableHead>
          <TableHead>Positions</TableHead>
          <TableHead>Captain</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members().map((user: UserType, idx: number) => (
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
                  <span>{user.nickname || user.username}</span>
                </div>
              </PlayerPopover>
            </TableCell>
            <TableCell>{user.mmr ?? 'N/A'}</TableCell>
            <TableCell>
              <RolePositions user={user as UserType} />
            </TableCell>

            <TableCell>
              <UpdateCaptainButton user={user} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
