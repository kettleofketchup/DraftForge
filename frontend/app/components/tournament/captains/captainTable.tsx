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
import { useUserStore } from '~/store/userStore';
import { UpdateCaptainButton } from './UpdateCaptainButton';
interface TournamentUsersTable {}

export const CaptainTable: React.FC<TournamentUsersTable> = () => {
  const tournament = useUserStore((state) => state.tournament);
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
  const members = () =>
    tournament.members?.sort((a, b) => {
      if (!a.mmr && !b.mmr) return 0;
      if (!a.mmr) return 1; // Treat undefined MMR as lower
      if (!b.mmr) return -1; // Treat undefined MMR as lower
      if (a.mmr >= b.mmr) return -1;

      if (a.mmr < b.mmr) return 1;
    });

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
        {tournament.members?.map((user: UserType, idx: number) => (
          <TableRow key={`TeamTableRow-${user.pk}`}>
            <TableCell>
              <div className="flex items-center gap-2">
                <span className="avatar w-8 h-8">
                  <img
                    src={user.avatarUrl}
                    alt={user.username}
                    className="rounded-full"
                  />
                </span>
                <span>{user.nickname || user.username}</span>
              </div>
            </TableCell>
            <TableCell>{user.mmr ?? 'N/A'}</TableCell>
            <TableCell>{user.positions ? positions(user) : 'N/A'}</TableCell>

            <TableCell>
              <UpdateCaptainButton user={user} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
