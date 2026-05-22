import { useMemo, useState } from 'react';
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
import { UserAvatar } from '~/components/user/UserAvatar';
import { RolePositions } from '~/components/user/positions';
import type { UserType } from '~/components/user/types';
import { UserStrip } from '~/components/user/UserStrip';
import { useUserStore } from '~/store/userStore';
import type { TeamType } from '~/index';
import { DraftOrderButton } from './draftOrder';
import { UpdateCaptainButton } from './UpdateCaptainButton';

/**
 * Captain selection — responsive container.
 *
 * Desktop (md+): the original Table layout (Member | MMR | Positions |
 * Captain). Plenty of horizontal room, captain action lives in its own
 * column.
 *
 * Mobile (<md): a vertical UserStrip list. The action column stacks the
 * captain toggle and (when applicable) the draft-order picker so the
 * modal stays inside iPhone-SE width.
 *
 * Component is still exported as `CaptainTable` so the import site in
 * `captainSelectionModal.tsx` doesn't need to move.
 */
export const CaptainTable: React.FC = () => {
  const tournament = useUserStore((state) => state.tournament);

  const sortedUsers = useMemo<UserType[]>(() => {
    if (!tournament.users) return [];
    return [...tournament.users].sort((a, b) => {
      const am = a.mmr ?? -Infinity;
      const bm = b.mmr ?? -Infinity;
      return bm - am;
    });
  }, [tournament.users]);

  const captainPks = useMemo(
    () => new Set((tournament.captains ?? []).map((c) => c.pk)),
    [tournament.captains],
  );

  return (
    <>
      {/* Mobile: stacked UserStrip list */}
      <div className="md:hidden flex flex-col gap-2" data-testid="captain-list">
        {sortedUsers.map((user) => (
          <CaptainStripRow
            key={user.pk}
            user={user}
            isCaptain={captainPks.has(user.pk)}
          />
        ))}
        {sortedUsers.length === 0 && (
          <p className="text-sm text-muted-foreground text-center py-4">
            No tournament users yet.
          </p>
        )}
      </div>

      {/* Desktop: existing Table layout */}
      <div className="hidden md:block">
        <Table data-testid="captain-table">
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
            {sortedUsers.map((user) => (
              <TableRow key={`TeamTableRow-${user.pk}`}>
                <TableCell>
                  <PlayerPopover player={user}>
                    <div className="flex items-center gap-2 hover:text-primary transition-colors">
                      <UserAvatar
                        user={user}
                        size="md"
                        className="hover:ring-2 hover:ring-primary transition-all"
                      />
                      <span>{user.nickname || user.username}</span>
                    </div>
                  </PlayerPopover>
                </TableCell>
                <TableCell>{user.mmr ?? 'N/A'}</TableCell>
                <TableCell>
                  <RolePositions user={user} />
                </TableCell>
                <TableCell>
                  <UpdateCaptainButton user={user} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </>
  );
};

// Re-export so unused-import warnings don't fire when PositionEnum stays
// imported for type checking on the desktop branch.
void PositionEnum;

interface CaptainStripRowProps {
  user: UserType;
  isCaptain: boolean;
}

const CaptainStripRow: React.FC<CaptainStripRowProps> = ({ user, isCaptain }) => {
  const tournament = useUserStore((state) => state.tournament);
  const team = useMemo<TeamType | undefined>(
    () => tournament?.teams?.find((t) => t.captain?.pk === user.pk),
    [tournament?.teams, user.pk],
  );
  const initialOrder = team?.draft_order ? String(team.draft_order) : '0';
  const [draftOrder, setDraftOrder] = useState<string>(initialOrder);

  return (
    <UserStrip
      user={user}
      compact
      showPositions={false}
      nameMaxLength={12}
      data-testid={`captain-row-${user.pk}`}
      actionSlot={
        // Action column lives inside the UserStrip card so the bordered
        // background expands around both the captain toggle and the draft
        // order picker. Height is enough to fit button (36) + gap (4) +
        // Order label (~12) + gap (2) + sm trigger (32) = 86px so the
        // picker never overflows the strip; non-captain rows reserve the
        // same height so base MMR badges align horizontally across rows.
        <div className="flex flex-col items-end gap-1 h-[88px] justify-start">
          <UpdateCaptainButton user={user} compact hideDraftOrder />
          {isCaptain && (
            <DraftOrderButton
              id={`draft-order-${user.pk}`}
              user={user}
              draft_order={draftOrder}
              setDraftOrder={setDraftOrder}
              compact
            />
          )}
        </div>
      }
    />
  );
};
