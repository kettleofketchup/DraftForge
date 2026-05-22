import { useMemo, useState } from 'react';
import { UserStrip } from '~/components/user/UserStrip';
import type { UserType } from '~/components/user/types';
import { useUserStore } from '~/store/userStore';
import type { TeamType } from '~/index';
import { DraftOrderButton } from './draftOrder';
import { UpdateCaptainButton } from './UpdateCaptainButton';

/**
 * Captain selection list — vertical UserStrip per tournament participant.
 *
 * Replaces the prior 4-column Table layout, which clipped the captain action
 * column at modal width on mobile. The strip puts:
 *   - actionSlot  → compact Crown / X icon button (toggle captain)
 *   - contextSlot → DraftOrderButton (only when the user is a captain)
 *
 * Component name kept as `CaptainTable` so the existing import site in
 * `captainSelectionModal.tsx` doesn't need to change.
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
    <div className="flex flex-col gap-2" data-testid="captain-list">
      {sortedUsers.map((user) => (
        <CaptainRow
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
  );
};

interface CaptainRowProps {
  user: UserType;
  isCaptain: boolean;
}

const CaptainRow: React.FC<CaptainRowProps> = ({ user, isCaptain }) => {
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
      data-testid={`captain-row-${user.pk}`}
      contextSlot={
        isCaptain ? (
          <DraftOrderButton
            id={`draft-order-${user.pk}`}
            user={user}
            draft_order={draftOrder}
            setDraftOrder={setDraftOrder}
          />
        ) : undefined
      }
      actionSlot={<UpdateCaptainButton user={user} compact hideDraftOrder />}
    />
  );
};
