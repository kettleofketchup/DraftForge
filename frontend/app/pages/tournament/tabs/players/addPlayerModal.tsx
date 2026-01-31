import type { FormEvent } from 'react';
import React, { useState, useEffect } from 'react';
import type { UserType } from '~/components/user/types';

import { PlusIconButton } from '~/components/ui/buttons';
import { FormDialog } from '~/components/ui/dialogs';
import UserCreateModal from '~/components/user/userCard/createModal';
import { useUserStore } from '~/store/userStore';
import { AddPlayerDropdown } from './addPlayerDropdown';

import { AdminOnlyButton } from '~/components/reusable/adminButton';
import { getLogger } from '~/lib/logger';

const log = getLogger('addPlayerModal');

interface Props {
  users: UserType[];
  addedUsers?: UserType[];
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  addPlayerCallback?: (user: UserType) => Promise<void>;
  removePlayerCallback?: (e: FormEvent, user: UserType) => Promise<void>;
}

export const AddPlayerModal: React.FC<Props> = ({
  addedUsers,
  addPlayerCallback,
  removePlayerCallback,
  query,
  setQuery,
}) => {
  const [open, setOpen] = useState(false);
  const currentUser = useUserStore((state) => state.currentUser);
  const isStaff = useUserStore((state) => state.isStaff);
  const users = useUserStore((state) => state.users);
  const getUsers = useUserStore((state) => state.getUsers);

  // Lazy load users when modal opens (only if not already loaded)
  useEffect(() => {
    if (open && users.length === 0) {
      getUsers();
    }
  }, [open, users.length, getUsers]);

  if (!isStaff()) {
    return (
      <AdminOnlyButton
        buttonTxt=""
        tooltipTxt={'Only Admins can add users to the tournament'}
      />
    );
  }

  return (
    <>
      <PlusIconButton
        tooltip="Add users to the tournament"
        data-testid="tournamentAddPlayerBtn"
        onClick={() => setOpen(true)}
      />

      <FormDialog
        open={open}
        onOpenChange={setOpen}
        title="Add Users to Tournament"
        description="Search for a user to add to the tournament. You can search by name or username."
        submitLabel="Done"
        isSubmitting={false}
        onSubmit={() => {
          setOpen(false);
        }}
        size="md"
        showFooter={false}
      >
        <div className="flex flex-col justify-start align-start items-start content-start w-full gap-4 mb-4">
          <div className="justify-self-start self-start w-full">
            <AddPlayerDropdown
              query={query}
              setQuery={setQuery}
              addPlayerCallback={addPlayerCallback}
              removePlayerCallback={removePlayerCallback}
              addedUsers={addedUsers}
            />
          </div>
        </div>
        <div className="flex flex-row gap-x-4 sm:gap-x-8 justify-center align-center items-center w-full">
          <UserCreateModal query={query} setQuery={setQuery} />
        </div>
      </FormDialog>
    </>
  );
};
