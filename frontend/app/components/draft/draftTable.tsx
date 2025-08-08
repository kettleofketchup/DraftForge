import { useEffect } from 'react';
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
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { ChoosePlayerButton } from './buttons/choosePlayerButtons';
import type { DraftRoundType } from './types';
const log = getLogger('draftTable');
interface DraftTableProps {
  curRound: DraftRoundType;
}
export const DraftTable: React.FC<DraftTableProps> = ({ curRound }) => {
  const tournament = useUserStore((state) => state.tournament);
  const curDraft = useUserStore((state) => state.curDraft);
  useEffect(() => {}, [tournament]);

  useEffect(() => {}, [curRound, curDraft]);

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
    const a = tournament?.draft?.users_remaining?.sort((a, b) => {
      if (!a.mmr && !b.mmr) return 0;
      if (!a.mmr) return 1; // Treat undefined MMR as lower
      if (!b.mmr) return -1; // Treat undefined MMR as lower
      if (a.mmr >= b.mmr) return -1;

      if (a.mmr < b.mmr) return 1;
    });
    return a || [];
  };

  return (
    <Table>
      <TableCaption>Tournament Users</TableCaption>
      <TableHeader>
        <TableRow>
          <TableHead>Member</TableHead>
          <TableHead>MMR</TableHead>
          <TableHead>Positions</TableHead>
          <TableHead>Choose?</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {members().map((user: UserType, idx: number) => (
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

            <TableCell>
              <ChoosePlayerButton user={user} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
};
