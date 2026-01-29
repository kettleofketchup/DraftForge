import type { FormEvent } from 'react';
import React, { useCallback } from 'react';
import { toast } from 'sonner';
import { updateTournament } from '~/components/api/api';
import { TrashIconButton } from '~/components/ui/buttons';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { useTournamentDataStore } from '~/store/tournamentDataStore';

const log = getLogger('playerRemoveButton');

import type { UserType } from '~/components/user/types';

interface PropsRemoveButton {
  user: UserType;
  disabled?: boolean;
}

export const PlayerRemoveButton: React.FC<PropsRemoveButton> = ({
  user,
  disabled,
}) => {
  // Tournament data from new store
  const tournamentId = useTournamentDataStore((state) => state.tournamentId);
  const tournamentUsers = useTournamentDataStore((state) => state.users);
  const loadAll = useTournamentDataStore((state) => state.loadAll);

  // Keep using useUserStore for query state (not tournament related)
  const setAddUserQuery = useUserStore((state) => state.setAddUserQuery);
  const setDiscordUserQuery = useUserStore((state) => state.setDiscordUserQuery);

  const removeUser = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      e.stopPropagation();
      // Implement the logic to remove the user from the tournament
      log.debug(`Removing user: ${user.username}`);
      const updatedUsers = tournamentUsers
        .filter((u) => u.username !== user.username)
        .map((u) => u.pk)
        .filter((pk): pk is number => pk !== undefined);

      log.debug('Updated users:', updatedUsers);

      const updatedTournament = {
        user_ids: updatedUsers,
      };
      if (tournamentId === null) {
        log.error('Tournament primary key is missing');
        return;
      }

      toast.promise(updateTournament(tournamentId, updatedTournament), {
        loading: `Removing User ${user.username}.`,
        success: () => {
          // Refresh tournament data from server
          loadAll();
          return `${user.username} has been removed`;
        },
        error: (err: any) => {
          log.error('Failed to update tournament', err);
          return `${user.username} could not be removed`;
        },
      });

      setAddUserQuery(''); // Reset query after removing user
      setDiscordUserQuery(''); // Reset Discord query after removing user
    },
    [tournamentId, tournamentUsers, loadAll, user.username, setAddUserQuery, setDiscordUserQuery],
  );
  // Find all users not already in the tournament
  return (
    <TrashIconButton
      size="sm"
      onClick={removeUser}
      disabled={disabled}
      tooltip="Remove User From Tournament"
      data-testid={`removePlayerBtn-${user.username}`}
    />
  );
};
