import { useQueryClient } from '@tanstack/react-query';
import type { FormEvent } from 'react';
import React, { useCallback } from 'react';
import { toast } from 'sonner';
import { useShallow } from 'zustand/react/shallow';
import { removeTournamentMember } from '~/components/api/api';
import type { TournamentType } from '~/components/tournament/types';
import { TrashIconButton } from '~/components/ui/buttons';
import { DisplayName } from '~/components/user/avatar';
import type { UserType } from '~/components/user/types';
import { hydrateTournament } from '~/lib/hydrateTournament';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('playerRemoveButton');

interface PropsRemoveButton {
  user: UserType;
  disabled?: boolean;
}

export const PlayerRemoveButton: React.FC<PropsRemoveButton> = ({
  user,
  disabled,
}) => {
  const tournament = useUserStore(useShallow((state) => state.tournament));
  const setTournament = useUserStore((state) => state.setTournament);
  const queryClient = useQueryClient();

  const removeUser = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const tournamentPk = tournament.pk;
      const userPk = user.pk;
      if (tournamentPk == null || userPk == null) {
        log.error('Tournament or user primary key is missing');
        return;
      }

      log.debug(`Removing user: ${user.username}`);

      // Optimistic update — remove user from React Query cache immediately
      // Cache may hold PK-only users (numbers) from slim serializer
      queryClient.setQueryData<TournamentType>(
        ['tournament', tournamentPk],
        (old) =>
          old
            ? {
                ...old,
                users:
                  old.users?.filter((u) =>
                    typeof u === 'number'
                      ? u !== user.pk
                      : u.username !== user.username,
                  ) ?? null,
              }
            : old,
      );

      const removal = removeTournamentMember(tournamentPk, userPk).then(
        (raw) => {
          setTournament(
            hydrateTournament(
              raw as TournamentType & { _users?: Record<number, unknown> },
            ) as TournamentType,
          );
          queryClient.invalidateQueries({
            queryKey: ['tournament', tournamentPk],
          });
        },
      );

      toast.promise(removal, {
        loading: `Removing ${DisplayName(user)}...`,
        success: () => `${DisplayName(user)} has been removed`,
        error: (err: unknown) => {
          log.error('Failed to remove user', err);
          // Revert optimistic update on failure
          queryClient.invalidateQueries({
            queryKey: ['tournament', tournamentPk],
          });
          return `Failed to remove ${DisplayName(user)}`;
        },
      });
    },
    [tournament.pk, user, queryClient, setTournament],
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
