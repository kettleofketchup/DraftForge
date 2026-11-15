import React, { useCallback, useState } from 'react';
import { toast } from 'sonner';
import { useShallow } from 'zustand/react/shallow';
import { TrashIconButton } from '~/components/ui/buttons';
import { ConfirmDialog } from '~/components/ui/dialogs';
import { DisplayName } from '~/components/user/avatar';
import { getLogger } from '~/lib/logger';
import { useUserStore } from '~/store/userStore';
import { User } from '../user';

const log = getLogger('deleteButton');

import type { UserType } from '~/components/user/types';

interface PropsRemoveButton {
  user: UserType;
  disabled?: boolean;
}

export const UserRemoveButton: React.FC<PropsRemoveButton> = ({
  user,
  disabled,
}) => {
  const [open, setOpen] = useState(false);
  const delUser = useUserStore(useShallow((state) => state.delUser));
  const setAddUserQuery = useUserStore(
    useShallow((state) => state.setAddUserQuery),
  );
  const setDiscordUserQuery = useUserStore(
    useShallow((state) => state.setDiscordUserQuery),
  );

  const removeUser = useCallback(async () => {
    const thisUser = new User(user as UserType);
    toast.promise(thisUser.dbDelete(), {
      loading: `Deleting User ${DisplayName(user)}.`,
      success: (data) => {
        log.debug('User deleted successfully');
        delUser(thisUser);
        setOpen(false);
        return `${DisplayName(user)} has been deleted`;
      },
      error: (err) => {
        log.error('Failed to delete user', err);
        return `${DisplayName(user)} could not be deleted`;
      },
    });

    setAddUserQuery('');
    setDiscordUserQuery('');
  }, [user, delUser, setAddUserQuery, setDiscordUserQuery]);

  return (
    <>
      <TrashIconButton
        onClick={() => setOpen(true)}
        disabled={disabled}
        tooltip="Delete user"
      />
      <ConfirmDialog
        open={open}
        onOpenChange={setOpen}
        title="Delete User?"
        description={`Are you sure you want to delete ${DisplayName(user)}? This action cannot be undone.`}
        confirmLabel="Delete"
        variant="destructive"
        onConfirm={removeUser}
      />
    </>
  );
};
