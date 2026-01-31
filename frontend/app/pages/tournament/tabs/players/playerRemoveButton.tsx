import type { FormEvent } from 'react';
import React, { useCallback } from 'react';
import { toast } from 'sonner';
import { useShallow } from 'zustand/react/shallow';
import { updateTournament } from '~/components/api/api';
import { TrashIconButton } from '~/components/ui/buttons';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';

const log = getLogger('playerRemoveButton');

import type { UserType } from '~/components/user/types';

interface Props {
  users: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
}

interface Props {
  users: UserType[];

  addedUsers?: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  addPlayerCallback?: (user: UserType) => Promise<void>;
  removePlayerCallback?: (e: FormEvent, user: UserType) => Promise<void>;
}
interface PropsRemoveButton {
  user: UserType;
  disabled?: boolean;
}
interface DeleteTooltipProps {
  tooltipText?: string;
}

export const PlayerRemoveButton: React.FC<PropsRemoveButton> = ({
  user,
  disabled,
}) => {
  const tournament = useUserStore(useShallow((state) => state.tournament));
  const setAddUserQuery = useUserStore(
    useShallow((state) => state.setAddUserQuery),
  );
  const setDiscordUserQuery = useUserStore(
    useShallow((state) => state.setDiscordUserQuery),
  );
  const setTournament = useUserStore(
    useShallow((state) => state.setTournament),
  );

  const removeUser = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      e.stopPropagation();
      // Implement the logic to remove the user from the tournament
      log.debug(`Removing user: ${user.username}`);
      const updatedUsers = tournament.users
        ?.filter((u) => u.username !== user.username)
        .map((u) => u.pk)
        .filter((pk): pk is number => pk !== undefined);

      log.debug('Updated users:', updatedUsers);

      const updatedTournament = {
        user_ids: updatedUsers ?? [],
      };
      if (tournament.pk === undefined) {
        log.error('Tournament primary key is missing');
        return;
      }

      toast.promise(updateTournament(tournament.pk!, updatedTournament), {
        loading: `Creating User ${user.username}.`,
        success: (data) => {
          tournament.users = tournament.users?.filter(
            (u) => u.username !== user.username,
          ) ?? null;
          //Trigger rerender of tournament users
          setTournament(data);
          return `${user.username} has been removed`;
        },
        error: (err: any) => {
          log.error('Failed to update tournament', err);
          return `${user.username} has been removed`;
        },
      });

      setAddUserQuery(''); // Reset query after adding user
      setDiscordUserQuery(''); // Reset Discord query after adding user
    },
    [tournament],
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
