import { Suspense, useEffect, useMemo } from 'react';
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
import { AvatarUrl, type TeamType } from '~/index';
import { cn } from '~/lib/utils';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { RolePositions } from '../../user/positions';
import { ChoosePlayerButton } from '../buttons/choosePlayerButtons';
import type { DraftRoundType } from '../types';
const log = getLogger('draftTable');

interface ProjectedData {
  newTeamMmr: number;
  newPickOrder: number;
  isDoublePick: boolean;
}

const getOrdinal = (n: number): string => {
  const s = ['th', 'st', 'nd', 'rd'];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};
interface DraftTableProps {}
export const DraftTable: React.FC<DraftTableProps> = ({}) => {
  const tournament = useUserStore((state) => state.tournament);
  const curRound: DraftRoundType = useUserStore((state) => state.curDraftRound);
  const draft = useUserStore((state) => state.draft);
  useEffect(() => {
    log.debug('rerender: Cur round choice changed');
  }, [curRound?.choice]);
  useEffect(() => {
    log.debug('rerender: draft users_remaining changed changed');
  }, [draft.users_remaining?.length]);

  const isShuffle = draft?.draft_style === 'shuffle';

  const getTeamMmr = (team: TeamType): number => {
    let total = team.captain?.mmr || 0;
    team.members?.forEach((member) => {
      if (member.pk !== team.captain?.pk) {
        total += member.mmr || 0;
      }
    });
    return total;
  };

  const getCurrentTeam = (): TeamType | undefined => {
    return tournament?.teams?.find(
      (t) => t.captain?.pk === curRound?.captain?.pk
    );
  };

  const teamMmrs = useMemo(() => {
    if (!isShuffle) return new Map<number, number>();
    const map = new Map<number, number>();
    tournament?.teams?.forEach((team) => {
      if (team.pk) {
        map.set(team.pk, getTeamMmr(team));
      }
    });
    return map;
  }, [tournament?.teams, isShuffle]);

  const getProjectedData = (userMmr: number): ProjectedData | null => {
    if (!isShuffle) return null;

    const currentTeam = getCurrentTeam();
    if (!currentTeam) return null;

    const currentTeamMmr = getTeamMmr(currentTeam);
    const newTeamMmr = currentTeamMmr + userMmr;

    // Calculate new pick order
    const otherTeamMmrs = Array.from(teamMmrs.entries())
      .filter(([pk]) => pk !== currentTeam.pk)
      .map(([, mmr]) => mmr);

    const allMmrs = [...otherTeamMmrs, newTeamMmr].sort((a, b) => a - b);
    const newPickOrder = allMmrs.indexOf(newTeamMmr) + 1;

    // Check if this would result in a double pick
    const lowestOtherMmr = Math.min(...otherTeamMmrs);
    const isDoublePick = newTeamMmr < lowestOtherMmr;

    return { newTeamMmr, newPickOrder, isDoublePick };
  };

  const members = () => {
    const a = tournament?.draft?.users_remaining?.sort(
      (a: UserType, b: UserType) => {
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
      },
    );
    return a || [];
  };

  return (
    <Suspense>
      <Table>
        <TableCaption>Tournament Users</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>Member</TableHead>
            <TableHead>MMR</TableHead>
            <TableHead className="hidden md:table-cell">Positions</TableHead>
            {isShuffle && <TableHead>Projected</TableHead>}
            <TableHead>Choose?</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {members().map((user: UserType, idx: number) => {
            const projected = getProjectedData(user.mmr || 0);
            return (
              <TableRow
                key={`TeamTableRow-${user.pk}`}
                className={cn(projected?.isDoublePick && 'bg-green-950/30')}
              >
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
                <TableCell className="hidden md:table-cell">
                  <RolePositions user={user} />
                </TableCell>
                {isShuffle && projected && (
                  <TableCell>
                    <div className="flex flex-col gap-0.5 text-sm">
                      <span className="text-muted-foreground">
                        {projected.newTeamMmr.toLocaleString()} MMR
                      </span>
                      <span
                        className={cn(
                          projected.isDoublePick
                            ? 'text-green-400 font-medium'
                            : 'text-muted-foreground'
                        )}
                      >
                        {getOrdinal(projected.newPickOrder)} pick
                        {projected.isDoublePick && ' (double!)'}
                      </span>
                    </div>
                  </TableCell>
                )}
                {isShuffle && !projected && <TableCell>-</TableCell>}
                <TableCell>
                  <ChoosePlayerButton user={user} />
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Suspense>
  );
};
