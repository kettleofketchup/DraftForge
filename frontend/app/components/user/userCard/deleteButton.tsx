import { Trash2 } from 'lucide-react';
import type { FormEvent } from 'react';
import React, { useCallback } from 'react';
import { toast } from 'sonner';
import { useShallow } from 'zustand/react/shallow';
import { Button } from '~/components/ui/button';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { User } from '../user';

const log = getLogger('deleteButton');

import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '~/components/ui/tooltip';

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

export const UserRemoveButton: React.FC<PropsRemoveButton> = ({
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
  const delUser = useUserStore(useShallow((state) => state.delUser));

  const removeUser = useCallback(
    async (e: FormEvent) => {
      let thisUser = new User(user as UserType);
      toast.promise(thisUser.dbDelete(), {
        loading: `Deleting User ${user.username}.`,
        success: (data) => {
          log.debug('User deleted successfully');
          delUser(thisUser);
          return `${user.username} has been deleted`;
        },
        error: (err) => {
          log.error('Failed to delete user', err);
          return `${user.username} could not be deleted`;
        },
      });

      setAddUserQuery(''); // Reset query after adding user
      setDiscordUserQuery(''); // Reset Discord query after adding user
    },
    [tournament],
  );
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="default"
          size="icon"
          onClick={removeUser}
          disabled={disabled}
          aria-label="Delete user"
          className="bg-red-950 hover:bg-red-600 text-white hover:shadow-sm hover:shadow-red-500/50"
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>
        <p>Delete user</p>
      </TooltipContent>
    </Tooltip>
  );
};
