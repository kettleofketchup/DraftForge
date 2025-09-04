import { Suspense, useEffect } from 'react';
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '~/components/ui/table';
import type { UserType } from '~/components/user/types';
import { AvatarUrl } from '~/index';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { RolePositions } from '../../user/positions';
import { ChoosePlayerButton } from '../buttons/choosePlayerButtons';
import type { DraftRoundType } from '../types';
import { Spinner } from '../helpers/spinner';
const log = getLogger('draftTable');
interface DraftTableProps {
  curRound: DraftRoundType;
}
export const DraftTable: React.FC<DraftTableProps> = ({ curRound }) => {
  const tournament = useUserStore((state) => state.tournament);
  const curDraft = useUserStore((state) => state.curDraft);
  useEffect(() => {}, [curRound?.choice, curDraft.users_remaining]);

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
    <Suspense fallback={<Spinner />}>
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
              <TableCell>
                <RolePositions user={user} />
              </TableCell>

              <TableCell>
                <ChoosePlayerButton user={user} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Suspense>
  );
};
