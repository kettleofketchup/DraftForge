import type { FormEvent } from 'react';
import React, { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useShallow } from 'zustand/react/shallow';
import { updateTournament } from '~/components/api/api';
import type { TournamentType } from '~/components/tournament/types';
import { TrashIconButton } from '~/components/ui/buttons';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

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
  const tournament = useUserStore(useShallow((state) => state.tournament));
  const queryClient = useQueryClient();

  const removeUser = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (tournament.pk === undefined) {
        log.error('Tournament primary key is missing');
        return;
      }

      log.debug(`Removing user: ${user.username}`);
      const updatedUserIds = tournament.users
        ?.filter((u) => u.username !== user.username)
        .map((u) => u.pk)
        .filter((pk): pk is number => pk !== undefined);

      // Optimistic update — remove user from React Query cache immediately
      queryClient.setQueryData<TournamentType>(
        ['tournament', tournament.pk],
        (old) =>
          old
            ? { ...old, users: old.users?.filter((u) => u.username !== user.username) ?? null }
            : old,
      );

      toast.promise(
        updateTournament(tournament.pk, { user_ids: updatedUserIds ?? [] }),
        {
          loading: `Removing ${user.username}...`,
          success: () => `${user.username} has been removed`,
          error: (err: unknown) => {
            log.error('Failed to remove user', err);
            // Revert optimistic update on failure
            queryClient.invalidateQueries({ queryKey: ['tournament', tournament.pk] });
            return `Failed to remove ${user.username}`;
          },
        },
      );
    },
    [tournament, user, queryClient],
  );

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
